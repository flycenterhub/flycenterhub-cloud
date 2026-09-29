"""Ryanair: prețuri pe zi (cheapestPerDay) pentru fiecare rută, în ambele direcții."""
import datetime as dt
import logging
import time

from .. import net
from .common import Throttle, combine_round_trips, date_range_end, month_starts, scan_routes

log = logging.getLogger("ryanair")

BASE = "https://www.ryanair.com/api/farfnd/v4"
HEADERS = {"Accept": "application/json"}
SOURCE = "ryanair"


def booking_link(o, d, dep, ret=""):
    is_ret = "true" if ret else "false"
    return ("https://www.ryanair.com/ro/ro/trip/flights/select?adults=1&teens=0&children=0&infants=0"
            f"&dateOut={dep}&dateIn={ret}&isConnectedFlight=false&discount=0&isReturn={is_ret}"
            f"&originIata={o}&destinationIata={d}")


def discover(origin, months_ahead):
    """Destinațiile cu bilete disponibile din `origin` în intervalul căutat."""
    today = dt.date.today()
    end = date_range_end(months_ahead)
    url = (f"{BASE}/oneWayFares?departureAirportIataCode={origin}"
           f"&outboundDepartureDateFrom={today}&outboundDepartureDateTo={end}"
           "&currency=EUR&market=ro-ro&adultPaxCount=1")
    data = net.get_json(url, headers=HEADERS)
    dests, places = [], []
    for f in data.get("fares") or []:
        ob = f["outbound"]
        a, p = ob["arrivalAirport"], ob["departureAirport"]
        dests.append(a["iataCode"])
        places.append((a["iataCode"], a.get("name"), a.get("countryName"), (a.get("city") or {}).get("countryCode")))
        places.append((p["iataCode"], p.get("name"), p.get("countryName"), (p.get("city") or {}).get("countryCode")))
    return sorted(set(dests)), places


def daily(o, d, months, end, throttle):
    """{data: rând} cu cel mai mic preț pe zi pentru o -> d."""
    today = dt.date.today().isoformat()
    out = {}
    for m in months:
        # fără „currency”: Ryanair dă prețul în moneda în care se plătește (HUF din Budapesta, EUR din România);
        # conversia lor în euro iese cu ~4% sub suma reală, de aceea convertim noi la cursul BNR
        url = f"{BASE}/oneWayFares/{o}/{d}/cheapestPerDay?outboundMonthOfDate={m.isoformat()}"
        data = net.get_json(url, headers=HEADERS, retries=3, backoff=20, on_retry=throttle.hit)
        for f in (data.get("outbound") or {}).get("fares") or []:
            price = f.get("price")
            if not price or f.get("unavailable") or f.get("soldOut"):
                continue
            day = f["day"]
            if day < today or day > end:
                continue
            val = float(price["value"])
            cur = price.get("currencyCode") or "EUR"
            out[day] = {
                "source": SOURCE, "origin": o, "dest": d, "dep_date": day, "ret_date": "",
                "price_eur": val if cur == "EUR" else None, "price_orig": val, "currency": cur,
                "dep_time": (f.get("departureDate") or "")[11:16], "airline": "Ryanair",
                "link": booking_link(o, d, day),
            }
        throttle.sleep()
    return out


def quick(cfg, db, scan_id, progress, stop):
    """Verificare rapidă: cel mai mic preț spre fiecare destinație, pe săptămâni (puține cereri)."""
    from .. import fx
    info = {"routes_ok": 0, "routes_failed": 0, "fares": 0, "errors": []}
    delay = float(cfg["request_delay_seconds"])
    today = dt.date.today()
    end = date_range_end(cfg["months_ahead"])
    weeks = int((end - today).days / 7) + 1
    for n_origin, origin in enumerate(cfg["origins"]):
        rows = []
        start = today
        while start <= end and not stop.is_set():
            stop_d = min(start + dt.timedelta(days=6), end)
            progress(f"Ryanair rapid {origin} {start:%d.%m}",
                     n_origin * weeks + (start - today).days // 7, weeks * len(cfg["origins"]))
            url = (f"{BASE}/oneWayFares?departureAirportIataCode={origin}"
                   f"&outboundDepartureDateFrom={start}&outboundDepartureDateTo={stop_d}"
                   "&market=ro-ro&adultPaxCount=1")  # moneda în care se plătește (vezi daily)
            try:
                data = net.get_json(url, headers=HEADERS, retries=2)
            except Exception as e:
                info["routes_failed"] += 1
                if len(info["errors"]) < 5:
                    info["errors"].append(f"{origin}: {e}")
                break
            fares = data.get("fares") or []
            for f in fares:
                ob = f["outbound"]
                price = ob.get("price") or {}
                cur = price.get("currencyCode") or "EUR"
                eur = fx.to_eur(price["value"], cur) if price.get("value") else None
                if eur is None:
                    continue
                day, dest = ob["departureDate"][:10], ob["arrivalAirport"]["iataCode"]
                rows.append({
                    "source": SOURCE, "origin": origin, "dest": dest, "dep_date": day, "ret_date": "",
                    "price_eur": eur, "price_orig": float(price["value"]), "currency": cur,
                    "dep_time": ob["departureDate"][11:16], "airline": "Ryanair",
                    "link": booking_link(origin, dest, day),
                })
            time.sleep(delay)
            if not fares and start == today:
                break  # Ryanair nu zboară din acest oraș
            start = stop_d + dt.timedelta(days=1)
        if rows:
            db.upsert_rows(scan_id, rows)
            info["routes_ok"] += 1
            info["fares"] += len(rows)
    return info


def scan(cfg, db, scan_id, progress, stop):
    from .. import fx
    months_ahead = cfg["months_ahead"]
    delay = float(cfg["request_delay_seconds"])
    rt = cfg["round_trip"]
    months = month_starts(months_ahead)
    end = date_range_end(months_ahead).isoformat()
    info = {"routes_ok": 0, "routes_failed": 0, "fares": 0, "errors": []}
    throttle = Throttle(delay)

    pairs = []
    for origin in cfg["origins"]:
        if stop.is_set():
            break
        try:
            dests, places = discover(origin, months_ahead)
            db.save_places(places)
        except Exception as e:
            info["errors"].append(f"{origin}: {e}")
            log.warning("Ryanair %s: %s", origin, e)
            continue
        time.sleep(delay)
        if not dests:
            log.info("Ryanair nu are zboruri din %s", origin)
        pairs += [(origin, d) for d in dests]

    def mk(o, b):
        return {
            "source": SOURCE, "origin": o["origin"], "dest": o["dest"],
            "dep_date": o["dep_date"], "ret_date": b["dep_date"],
            "price_eur": round(o["price_eur"] + b["price_eur"], 2),
            "price_orig": round(o["price_eur"] + b["price_eur"], 2), "currency": "EUR",
            "dep_time": o["dep_time"], "ret_time": b["dep_time"], "airline": "Ryanair",
            "link": booking_link(o["origin"], o["dest"], o["dep_date"], b["dep_date"]),
        }

    def fetch_route(origin, dest):
        out = daily(origin, dest, months, end, throttle)
        back = daily(dest, origin, months, end, throttle)
        for r in list(out.values()) + list(back.values()):
            if r["price_eur"] is None:
                r["price_eur"] = fx.to_eur(r["price_orig"], r["currency"])
        out = {k: v for k, v in out.items() if v["price_eur"] is not None}
        back = {k: v for k, v in back.items() if v["price_eur"] is not None}
        rts = combine_round_trips(out, back, rt["min_nights"], rt["max_nights"], mk)
        rows = list(out.values()) + list(back.values()) + rts
        db.replace_route(SOURCE, scan_id, origin, dest, rows)
        return len(rows)

    scan_routes("Ryanair", pairs, fetch_route, info, progress, stop, throttle)
    return info
