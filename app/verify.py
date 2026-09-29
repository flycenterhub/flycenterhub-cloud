"""Verificare live a unui bilet, direct la companie (Wizz Air / Ryanair), în momentul cererii."""
import datetime as dt

from . import fx, net
from .db import now_str
from .sources import ryanair, wizzair
from .sources.common import Throttle


def _wizz(db, o, d, day):
    api = db.get_kv("wizz_api") or wizzair.api_base(db)
    date = dt.date.fromisoformat(day)
    try:
        data = wizzair.timetable(api, o, d, date, date)
    except net.HttpError as e:
        if e.status != 404:
            raise
        api = wizzair.api_base(db)  # versiunea site-ului s-a schimbat
        data = wizzair.timetable(api, o, d, date, date)
    return wizzair._rows(data.get("outboundFlights")).get(day)


def _ryan(db, o, d, day):
    month = dt.date.fromisoformat(day).replace(day=1)
    row = ryanair.daily(o, d, [month], "9999-12-31", Throttle(0)).get(day)
    if row and row["price_eur"] is None:
        row["price_eur"] = fx.to_eur(row["price_orig"], row["currency"])
    return row


FETCH = {"wizzair": _wizz, "ryanair": _ryan}

# ---------- locuri la acest preț și prețul pentru N persoane ----------
MAX_PAX = 9  # maximum de pasageri pe o rezervare la Wizz Air și Ryanair


def _price_for(db, src, o, d, day, n):
    """Prețul pe persoană (moneda biletului) pentru n pasageri, sau None dacă nu mai există zbor."""
    if src == "wizzair":
        api = db.get_kv("wizz_api") or wizzair.api_base(db)
        date = dt.date.fromisoformat(day)
        row = wizzair._rows(wizzair.timetable(api, o, d, date, date, adults=n).get("outboundFlights")).get(day)
        return (row["price_orig"], row["currency"]) if row else None
    url = (f"{ryanair.BASE}/oneWayFares?departureAirportIataCode={o}&arrivalAirportIataCode={d}"
           f"&outboundDepartureDateFrom={day}&outboundDepartureDateTo={day}&market=ro-ro&adultPaxCount={n}")
    fares = net.get_json(url, headers=ryanair.HEADERS, retries=2).get("fares") or []
    if not fares:
        return None
    price = fares[0]["outbound"]["price"]  # în moneda în care se plătește; Ryanair dă totalul pentru n
    return round(float(price["value"]) / n, 2), price.get("currencyCode") or "EUR"


def _same(a, b):
    return a is not None and b is not None and abs(a[0] - b[0]) < 0.011


def seats_at_price(db, src, o, d, day, base):
    """Câte locuri mai sunt la prețul de bază (1..9; 9 = „9 sau mai multe”), prin căutare binară după n."""
    if _same(_price_for(db, src, o, d, day, MAX_PAX), base):
        return MAX_PAX
    lo, hi = 1, MAX_PAX  # la lo prețul e același, la hi e mai mare
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _same(_price_for(db, src, o, d, day, mid), base):
            lo = mid
        else:
            hi = mid
    return lo


def group_info(db, leg, row, pax):
    """Locurile rămase la preț și (pentru grupuri) prețul pe persoană pentru `pax` pasageri."""
    base = (row["price_orig"], row["currency"])
    info = {}
    try:
        info["seats"] = seats_at_price(db, leg["source"], leg["origin"], leg["dest"], leg["date"], base)
        if pax > 1:
            p = base if pax <= info["seats"] else _price_for(db, leg["source"], leg["origin"], leg["dest"], leg["date"], pax)
            if p:
                eur = fx.to_eur(p[0], p[1])
                info.update(pax_price_eur=eur, pax_price_ron=fx.lei_of(eur, p[0], p[1]))
    except Exception:
        pass  # informația despre locuri e un bonus: verificarea prețului rămâne valabilă
    return info



def verify(db, legs, pax=1):
    """legs: [{source, origin, dest, date}] - 1 segment (dus) sau 2 (dus + întors); pax = nr. de persoane."""
    pax = max(1, min(int(pax or 1), MAX_PAX))
    fx.refresh()
    scan = db.q1("SELECT max(id) AS id FROM scans")
    scan_id = scan["id"] if scan else None
    results, fresh = [], []
    for leg in legs:
        src, o, d, day = leg["source"], leg["origin"], leg["dest"], leg["date"]
        if src not in FETCH:
            results.append({"ok": False, "reason": "unsupported"})
            continue
        old = db.q1("SELECT price_eur FROM fares WHERE source=? AND origin=? AND dest=? AND dep_date=? AND ret_date=''",
                    (src, o, d, day))
        row = FETCH[src](db, o, d, day)
        old_eur = old["price_eur"] if old else None
        if not row:
            db.x("DELETE FROM fares WHERE source=? AND origin=? AND dest=? AND dep_date=? AND ret_date=''",
                 (src, o, d, day))
            results.append({"ok": True, "available": False, "old_price_eur": old_eur})
            continue
        db.upsert_rows(scan_id, [row])
        fresh.append(row)
        extra = group_info(db, leg, row, pax)
        results.append({**extra,
            "ok": True, "available": True, "price_eur": row["price_eur"],
            "price_ron": fx.lei_of(row["price_eur"], row["price_orig"], row["currency"]),
            "lei_exact": row["currency"] == "RON", "old_price_eur": old_eur,
            "changed": old_eur is not None and abs(old_eur - row["price_eur"]) >= 0.01,
            "time": row.get("dep_time") or "",
        })

    out = {"legs": results, "checked_at": now_str()}
    if not all(r["ok"] for r in results):
        out.update(ok=False, reason="unsupported")
        return out
    out["ok"] = True
    out["available"] = all(r["available"] for r in results)
    if not out["available"]:
        # dacă un segment nu mai există, dispare și combinația dus-întors salvată
        if len(legs) == 2:
            a, b = legs
            db.x("DELETE FROM fares WHERE source=? AND origin=? AND dest=? AND dep_date=? AND ret_date=?",
                 (a["source"], a["origin"], a["dest"], a["date"], b["date"]))
        return out
    out["price_eur"] = round(sum(r["price_eur"] for r in results), 2)
    out["price_ron"] = round(sum(r["price_ron"] for r in results), 2)
    out["lei_exact"] = all(r["lei_exact"] for r in results)
    out["changed"] = any(r["changed"] for r in results)
    out["pax"] = pax
    if all("seats" in r for r in results):
        out["seats"] = min(r["seats"] for r in results)
        out["seats_max"] = MAX_PAX
    if pax > 1 and all("pax_price_eur" in r for r in results):
        out["pax_price_eur"] = round(sum(r["pax_price_eur"] for r in results), 2)   # pe persoană, dus + întors
        out["pax_total_eur"] = round(out["pax_price_eur"] * pax, 2)
        out["pax_total_ron"] = round(sum(r["pax_price_ron"] for r in results) * pax, 2)
    # actualizează și dus-întorsul salvat (aceeași companie la dus și la întors)
    if len(fresh) == 2 and fresh[0]["source"] == fresh[1]["source"]:
        a, b = fresh
        same = a["currency"] == b["currency"]
        link = (wizzair.booking_link if a["source"] == "wizzair" else ryanair.booking_link)(
            a["origin"], a["dest"], a["dep_date"], b["dep_date"])
        old_rt = db.q1("SELECT price_eur FROM fares WHERE source=? AND origin=? AND dest=? AND dep_date=? AND ret_date=?",
                       (a["source"], a["origin"], a["dest"], a["dep_date"], b["dep_date"]))
        db.upsert_rows(scan_id, [{
            "source": a["source"], "origin": a["origin"], "dest": a["dest"],
            "dep_date": a["dep_date"], "ret_date": b["dep_date"], "price_eur": out["price_eur"],
            "price_orig": round(a["price_orig"] + b["price_orig"], 2) if same else out["price_eur"],
            "currency": a["currency"] if same else "EUR", "dep_time": a.get("dep_time"), "ret_time": b.get("dep_time"),
            "airline": a.get("airline"), "link": link,
        }])
        if old_rt:
            out["old_price_eur"] = old_rt["price_eur"]
    if "old_price_eur" not in out and all(r["old_price_eur"] is not None for r in results):
        out["old_price_eur"] = round(sum(r["old_price_eur"] for r in results), 2)
    return out
