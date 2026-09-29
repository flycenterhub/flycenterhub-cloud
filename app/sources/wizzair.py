"""Wizz Air: harta rutelor + orarul cu prețuri pe zi (ambele direcții într-o singură cerere)."""
import logging
import re

from .. import fx, net
from .common import Throttle, combine_round_trips, scan_routes, windows

log = logging.getLogger("wizzair")

SOURCE = "wizzair"
HOME = "https://www.wizzair.com/en-gb"


def _headers():
    return {
        "Origin": "https://www.wizzair.com",
        "Referer": "https://www.wizzair.com/en-gb",
        "Accept": "application/json, text/plain, */*",
    }


def booking_link(o, d, dep, ret=""):
    return f"https://www.wizzair.com/ro-ro/booking/select-flight/{o}/{d}/{dep}/{ret or 'null'}/1/0/0/null"


def api_base(db):
    """Adresa API-ului se schimbă la fiecare versiune a site-ului; o citim din pagina principală."""
    try:
        html = net.get_text(HOME, timeout=40, retries=2)
        m = re.search(r'apiUrl:"(https://be\.wizzair\.com/[\d.]+/Api)"', html) or \
            re.search(r'(https://be\.wizzair\.com/[\d.]+/Api)', html)
        if m:
            db.set_kv("wizz_api", m.group(1))
            return m.group(1)
    except Exception as e:
        log.warning("Nu am putut citi versiunea Wizz Air: %s", e)
    return db.get_kv("wizz_api")


def route_map(api):
    data = net.get_json(f"{api}/asset/map?languageCode=en-gb", headers=_headers())
    cities = data.get("cities") or []
    real = {c["iata"] for c in cities if not c.get("isFakeStation")}
    places = [(c["iata"], c.get("shortName"), c.get("countryName"), c.get("countryCode")) for c in cities]
    conns = {}
    for c in cities:
        conns[c["iata"]] = sorted({x["iata"] for x in c.get("connections") or []
                                   if x["iata"] in real and not x.get("isConnected")})
    return conns, places


def timetable(api, o, d, start, stop, on_retry=None, adults=1):
    payload = {
        "flightList": [
            {"departureStation": o, "arrivalStation": d, "from": start.isoformat(), "to": stop.isoformat()},
            {"departureStation": d, "arrivalStation": o, "from": start.isoformat(), "to": stop.isoformat()},
        ],
        "priceType": "regular", "adultCount": adults, "childCount": 0, "infantCount": 0,
    }
    return net.post_json(f"{api}/search/timetable", payload, headers=_headers(), retries=3, backoff=30,
                         on_retry=on_retry)


def _rows(flights):
    out = {}
    for f in flights or []:
        price = f.get("price") or {}
        amount = float(price.get("amount") or 0)
        if amount <= 0 or f.get("priceType") == "checkPrice":
            continue
        cur = price.get("currencyCode") or "EUR"
        eur = fx.to_eur(amount, cur)
        if eur is None:
            continue
        day = f["departureDate"][:10]
        times = f.get("departureDates") or []
        o, d = f["departureStation"], f["arrivalStation"]
        out[day] = {
            "source": SOURCE, "origin": o, "dest": d, "dep_date": day, "ret_date": "",
            "price_eur": eur, "price_orig": amount, "currency": cur,
            "dep_time": times[0][11:16] if times else "", "airline": "Wizz Air",
            "link": booking_link(o, d, day),
        }
    return out


def scan(cfg, db, scan_id, progress, stop):
    delay = float(cfg["request_delay_seconds"])
    rt = cfg["round_trip"]
    info = {"routes_ok": 0, "routes_failed": 0, "fares": 0, "errors": []}
    api = api_base(db)
    if not api:
        info["errors"].append("Nu am găsit adresa API Wizz Air")
        return info
    try:
        conns, places = route_map(api)
        db.save_places(places)
    except Exception as e:
        info["errors"].append(f"Harta rutelor: {e}")
        return info

    wins = windows(cfg["months_ahead"], days=30)
    # Wizz Air limitează cererile dese: pornim mai lent decât la Ryanair și ne adaptăm
    throttle = Throttle(max(delay, 1.2))

    def mk(o, b):
        same = o["currency"] == b["currency"]
        return {
            "source": SOURCE, "origin": o["origin"], "dest": o["dest"],
            "dep_date": o["dep_date"], "ret_date": b["dep_date"],
            "price_eur": round(o["price_eur"] + b["price_eur"], 2),
            "price_orig": round(o["price_orig"] + b["price_orig"], 2) if same else round(o["price_eur"] + b["price_eur"], 2),
            "currency": o["currency"] if same else "EUR",
            "dep_time": o["dep_time"], "ret_time": b["dep_time"], "airline": "Wizz Air",
            "link": booking_link(o["origin"], o["dest"], o["dep_date"], b["dep_date"]),
        }

    def fetch_route(origin, dest):
        out, back = {}, {}
        for start, stop_d in wins:
            data = timetable(api, origin, dest, start, stop_d, throttle.hit)
            out.update(_rows(data.get("outboundFlights")))
            back.update(_rows(data.get("returnFlights")))
            throttle.sleep()
        rts = combine_round_trips(out, back, rt["min_nights"], rt["max_nights"], mk)
        rows = list(out.values()) + list(back.values()) + rts
        db.replace_route(SOURCE, scan_id, origin, dest, rows)
        return len(rows)

    pairs = [(o, d) for o in cfg["origins"] for d in conns.get(o) or []]
    scan_routes("Wizz Air", pairs, fetch_route, info, progress, stop, throttle)
    return info
