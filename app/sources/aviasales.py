"""Aviasales / Travelpayouts Data API (opțional, token gratuit).

Prețuri găsite recent de utilizatorii Aviasales, pentru toate companiile (TAROM, HiSky,
Lufthansa, Turkish, Qatar, Emirates etc.), inclusiv zboruri cu escală. Completează Ryanair și
Wizz Air și e sursa principală pentru destinațiile exotice (Asia, Africa, America...).
"""
import datetime as dt
import logging
import time

from .. import net
from ..airlines import RYANAIR_CODES, WIZZ_CODES, PEGASUS_CODES, pegasus_link
from ..regions import region_of
from . import ryanair, wizzair
from .common import date_range_end, google_flights_link, month_starts

log = logging.getLogger("aviasales")

SOURCE = "aviasales"
API = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


def _load_names(db):
    """Nume de orașe/țări și companii aeriene (fișiere publice, descărcate o dată)."""
    if db.get_kv("tp_names_loaded_v2"):
        return db.get_kv("tp_airlines", {})
    airlines = {}
    try:
        cities = net.get_json("https://api.travelpayouts.com/data/en/cities.json", timeout=60)
        countries = {c["code"]: c.get("name") for c in
                     net.get_json("https://api.travelpayouts.com/data/en/countries.json", timeout=60)}
        known = {r["code"] for r in db.q("SELECT code FROM places")}
        db.save_places([(c["code"], c.get("name"), countries.get(c.get("country_code")), c.get("country_code"))
                        for c in cities if c.get("code") and c["code"] not in known])
        with db.lock:
            db.conn.executemany("UPDATE places SET cc=? WHERE code=? AND cc IS NULL",
                                [(c.get("country_code"), c["code"]) for c in cities
                                 if c.get("code") in known and c.get("country_code")])
            db.conn.commit()
        airlines = {a["code"]: a.get("name") for a in
                    net.get_json("https://api.travelpayouts.com/data/en/airlines.json", timeout=60) if a.get("code")}
        db.set_kv("tp_airlines", airlines)
        db.set_kv("tp_names_loaded_v2", True)
    except Exception as e:
        log.warning("Nu am putut descărca numele orașelor: %s", e)
    return airlines


def _query(token, origin, month, one_way, unique):
    params = (f"?origin={origin}&departure_at={month:%Y-%m}&one_way={'true' if one_way else 'false'}"
              f"&sorting=price&direct=false&limit=1000&page=1&currency=eur&market=ro"
              f"{'&unique=true' if unique else ''}")
    return net.get_json(API + params, headers={"X-Access-Token": token}, retries=2).get("data") or []


def scan(cfg, db, scan_id, progress, stop):
    token = (cfg["sources"].get("aviasales") or {}).get("token", "").strip()
    info = {"routes_ok": 0, "routes_failed": 0, "fares": 0, "errors": []}
    if not token:
        info["errors"].append("Lipsește tokenul Travelpayouts")
        return info
    airlines = _load_names(db)
    cc_of = {r["code"]: (r.get("cc"), (r.get("country") or "").strip()) for r in db.q("SELECT code, cc, country FROM places")}
    rt = cfg["round_trip"]
    ex = cfg.get("exotic") or {}
    delay = float(cfg["request_delay_seconds"])

    ex_origins = set(ex.get("origins") or [ex.get("origin")])
    total = sum(len(month_starts(max(cfg["months_ahead"], ex.get("months_ahead", 0)) if o in ex_origins
                                  else cfg["months_ahead"])) * (4 if o in ex_origins else 2)
                for o in cfg["origins"])
    done = 0
    for origin in cfg["origins"]:
        if stop.is_set():
            break
        exotic_origin = origin in ex_origins
        months_ahead = max(cfg["months_ahead"], ex.get("months_ahead", 0)) if exotic_origin else cfg["months_ahead"]
        end = date_range_end(months_ahead).isoformat()
        rows, ok = [], True
        for m in month_starts(months_ahead):
            # Pentru destinațiile exotice: și o cerere cu câte un preț pe destinație (acoperă și rutele scumpe)
            for one_way in (True, False):
                for unique in ((False, True) if exotic_origin else (False,)):
                    if stop.is_set():
                        break
                    progress(f"Aviasales {origin} {m:%Y-%m} {'dus' if one_way else 'dus-întors'}", done, total)
                    done += 1
                    try:
                        items = _query(token, origin, m, one_way, unique)
                    except Exception as e:
                        ok = False
                        if len(info["errors"]) < 10:
                            info["errors"].append(f"{origin} {m:%Y-%m}: {e}")
                        continue
                    finally:
                        time.sleep(delay)
                    for it in items:
                        row = _row(it, origin, one_way, end, rt, ex, cc_of, airlines)
                        if row:
                            rows.append(row)
        # Același zbor poate apărea de mai multe ori: păstrăm cel mai mic preț
        best = {}
        for r in rows:
            k = (r["dest"], r["dep_date"], r["ret_date"])
            if k not in best or r["price_eur"] < best[k]["price_eur"]:
                best[k] = r
        if ok:
            db.replace_origin(SOURCE, scan_id, origin, list(best.values()))
            info["routes_ok"] += 1
        else:
            db.upsert_rows(scan_id, list(best.values()))
            info["routes_failed"] += 1
        info["fares"] += len(best)
    return info


def _row(it, origin, one_way, end, rt, ex, cc_of, airlines):
    dest = it.get("destination")
    dep = (it.get("departure_at") or "")[:10]
    ret = (it.get("return_at") or "")[:10] if not one_way else ""
    if not dest or not dep or dep > end or (not one_way and not ret):
        return None
    # Prețurile Aviasales sunt găsite de alți utilizatori; cele care pleacă foarte curând sunt de obicei deja vândute
    if dep < (dt.date.today() + dt.timedelta(days=2)).isoformat():
        return None
    if ret:
        nights = (dt.date.fromisoformat(ret) - dt.date.fromisoformat(dep)).days
        if region_of(dest, *cc_of.get(dest, (None, None))):
            lo, hi = ex.get("min_nights", 5), ex.get("max_nights", 28)
        else:
            lo, hi = rt["min_nights"], max(rt["max_nights"], 14)
        if nights < lo or nights > hi:
            return None
    code = it.get("airline") or ""
    transfers = int(it.get("transfers") or 0) + int(it.get("return_transfers") or 0 if ret else 0)
    name = airlines.get(code, code)
    # Codul biletului (?t=XX...) începe cu compania care vinde biletul; dacă diferă, zborul combină companii
    ticket = (it.get("link") or "").split("t=", 1)[1][:2] if "t=" in (it.get("link") or "") else ""
    if transfers and ticket and ticket != code:
        name = f"{name} + {airlines.get(ticket, ticket)}"
    if transfers:
        name = f"{name} · {transfers} {'escală' if transfers == 1 else 'escale'}"
    else:
        name = f"{name} · direct"
    return {
        "source": SOURCE, "origin": origin, "dest": dest, "dep_date": dep, "ret_date": ret,
        "price_eur": float(it["price"]), "price_orig": float(it["price"]), "currency": "EUR",
        "dep_time": (it.get("departure_at") or "")[11:16],
        "ret_time": (it.get("return_at") or "")[11:16] if ret else "",
        "flight_no": f"{code}{it.get('flight_number') or ''}", "airline": name,
        "link": booking_link(code, transfers, it.get("origin_airport") or origin,
                             it.get("destination_airport") or dest, origin, dest, dep, ret,
                             ticket_link=("https://www.aviasales.com" + it["link"]) if (it.get("link") or "").startswith("/") else "",
                             ticket=ticket),
    }


def booking_link(code, transfers, from_airport, to_airport, origin, dest, dep, ret, ticket_link="", ticket=""):
    """Linkul de rezervare pentru EXACT acest zbor:
    - direct Wizz Air / Ryanair -> zborul pe site-ul companiei, cu data completată;
    - altă companie sau zbor cu escale -> exact ruta și datele în Google Flights (sursă de încredere, cu
      rezervare la companie sau la agenții cunoscute); pe site apar și Skyscanner, Kayak, Kiwi, Momondo."""
    if not transfers and code in WIZZ_CODES:
        return wizzair.booking_link(from_airport, to_airport, dep, ret)
    if not transfers and code in RYANAIR_CODES:
        return ryanair.booking_link(from_airport, to_airport, dep, ret)
    if code in PEGASUS_CODES and (not ticket or ticket in PEGASUS_CODES):
        return pegasus_link(from_airport, to_airport, dep, ret)  # și cu escală la Istanbul, tot bilet Pegasus
    return google_flights_link(origin, dest, dep, ret)
