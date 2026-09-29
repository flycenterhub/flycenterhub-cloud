"""Prețuri reale Google Flights prin SerpApi (cont gratuit: 250 de căutări pe lună).

Confirmă prețul real pentru zborurile altor companii (găsite în căutările altor călători). Un zbor
confirmat se salvează ca sursă „google” (preț real), cu linkul de rezervare pentru exact acel zbor.
Cheia API rămâne doar pe acest calculator: nu se publică niciodată pe site-ul public.
"""
import datetime as dt
import json
import logging
import urllib.parse

from .. import net
from ..airlines import pegasus_link
from .common import google_flights_link
from ..db import now_str

log = logging.getLogger("serpapi")

SOURCE = "google"
API = "https://serpapi.com/search.json"

# Codurile de oraș (folosite de unele surse) -> aeroporturile pe care le înțelege Google Flights
CITY_AIRPORTS = {
    "BJS": "PEK,PKX", "SHA": "PVG,SHA", "TYO": "NRT,HND", "OSA": "KIX,ITM", "SEL": "ICN,GMP", "BKK": "BKK,DMK",
    "NYC": "JFK,EWR,LGA", "WAS": "IAD,DCA,BWI", "CHI": "ORD,MDW", "LON": "LHR,LGW,STN,LTN", "PAR": "CDG,ORY",
    "ROM": "FCO,CIA", "MIL": "MXP,LIN,BGY", "MOW": "SVO,DME,VKO", "STO": "ARN,BMA", "BUH": "OTP", "IST": "IST,SAW",
    "DXB": "DXB,DWC", "TCI": "TFS,TFN", "RIO": "GIG,SDU", "SAO": "GRU,CGH,VCP", "BUE": "EZE,AEP", "YTO": "YYZ,YTZ",
    "YMQ": "YUL", "JKT": "CGK,HLP", "KUL": "KUL,SZB", "TPE": "TPE,TSA", "DEL": "DEL", "BOM": "BOM",
}


def enabled(cfg):
    s = cfg.get("serpapi") or {}
    return bool((s.get("api_key") or "").strip())


def _key(cfg):
    return (cfg.get("serpapi") or {}).get("api_key", "").strip()


def account(cfg):
    """Căutări rămase luna aceasta (din contul SerpApi)."""
    data = net.get_json("https://serpapi.com/account.json?api_key=" + urllib.parse.quote(_key(cfg)), timeout=20, retries=1)
    return {"left": data.get("total_searches_left", data.get("plan_searches_left")),
            "plan": data.get("plan_name"), "per_month": data.get("searches_per_month")}


def _search(cfg, db, params):
    """O căutare SerpApi (se numără la limita lunară)."""
    data = net.get_json(API + "?" + urllib.parse.urlencode(params), timeout=60, retries=1)
    used = db.get_kv("serpapi_used", {}) or {}   # orice căutare se numără (și cele fără rezultat)
    month = dt.date.today().strftime("%Y-%m")
    used[month] = used.get(month, 0) + 1
    db.set_kv("serpapi_used", used)
    return data


def _options(data):
    return [o for o in (data.get("best_flights") or []) + (data.get("other_flights") or []) if o.get("price")]


def _booking(cfg, db, params, best):
    """Linkul de rezervare pentru EXACT zborul găsit (ca la „Rezervă” pe Google Flights).
    Dus: booking_token. Dus-întors: întâi zborul de întoarcere (departure_token), apoi booking_token."""
    tok = best.get("booking_token")
    if not tok and best.get("departure_token"):
        back = _options(_search(cfg, db, {**params, "departure_token": best["departure_token"]}))
        if back:
            tok = min(back, key=lambda o: o["price"]).get("booking_token")
    if not tok:
        return None
    data = _search(cfg, db, {**params, "booking_token": tok})
    return best_offer(data)


def best_offer(data):
    """Vânzătorul cu cel mai mic preț (Google nu dă mereu prețul; atunci primul din listă, ca pe Google Flights)."""
    offers = []
    for i, b in enumerate(data.get("booking_options") or []):
        t = b.get("together") or {}
        req = t.get("booking_request") or {}
        if req.get("url") and t.get("airline"):
            price = float(t["price"]) if t.get("price") else None
            offers.append((price if price is not None else 1e9, not t.get("airline"), i, t.get("book_with") or "", req, price))
    if not offers:
        return None
    _, _, _, who, req, price = min(offers)
    return {"url": req["url"], "post": req.get("post_data") or "", "with": who, "price": price}


def check(cfg, db, origin, dest, dep, ret="", adults=1, children=0, infants=0):
    """Caută pe Google Flights cel mai mic preț real + linkul de rezervare pentru exact acel zbor."""
    params = {
        "engine": "google_flights", "api_key": _key(cfg),
        "departure_id": CITY_AIRPORTS.get(origin, origin), "arrival_id": CITY_AIRPORTS.get(dest, dest),
        "outbound_date": dep, "type": "1" if ret else "2", "currency": "EUR", "hl": "ro", "gl": "ro",
        "adults": str(adults), "children": str(children), "infants_on_lap": str(infants),
    }
    if ret:
        params["return_date"] = ret
    data = _search(cfg, db, params)
    if data.get("error"):
        return {"ok": False, "error": data["error"]}
    options = _options(data)
    url = (data.get("search_metadata") or {}).get("google_flights_url") or ""
    if not options:
        return {"ok": True, "found": False, "url": url}
    best = min(options, key=lambda o: o["price"])
    segs = best.get("flights") or []
    airlines = []
    for s in segs:
        if s.get("airline") and s["airline"] not in airlines:
            airlines.append(s["airline"])
    stops = max(len(segs) - 1, 0)
    pax = max(adults + children, 1)
    total = float(best["price"])
    booking = None
    try:
        booking = _booking(cfg, db, params, best)
    except Exception as e:
        log.warning("Link de rezervare Google Flights: %s", e)
    if booking and booking["price"]:
        total = booking["price"]  # prețul exact de la vânzător
    price_pp = round(total / pax, 2)  # Google Flights dă prețul total pentru toți pasagerii
    name = " + ".join(airlines) or "Google Flights"
    name += " · direct" if not stops else f" · {stops} {'escală' if stops == 1 else 'escale'}"
    first = segs[0] if segs else {}
    # „Rezervă” = formularul de rezervare Google pentru exact acest zbor (redirecționează la vânzător);
    # dacă nu există, căutarea Google Flights pe ruta și datele exacte
    if booking:
        link = "gfpost:" + json.dumps({"url": booking["url"], "post": booking["post"], "with": booking["with"], "gf": url},
                                      ensure_ascii=False)
    elif airlines == ["Pegasus"] and segs:
        # Google nu vinde bilete Pegasus: exact zborul pe site-ul Pegasus
        link = pegasus_link((segs[0].get("departure_airport") or {}).get("id") or origin,
                            (segs[-1].get("arrival_airport") or {}).get("id") or dest, dep, ret, adults, children, infants)
    else:
        link = url
    row = {
        "source": SOURCE, "origin": origin, "dest": dest, "dep_date": dep, "ret_date": ret,
        "price_eur": price_pp, "price_orig": price_pp, "currency": "EUR",
        "dep_time": ((first.get("departure_airport") or {}).get("time") or "")[11:16], "ret_time": "",
        "flight_no": first.get("flight_number") or "", "airline": name, "link": link,
    }
    scan = db.q1("SELECT max(id) AS id FROM scans")
    db.upsert_rows(scan["id"] if scan else None, [row])
    db.set_kv("prices_updated_at", now_str())
    insights = data.get("price_insights") or {}
    log.info("Google Flights %s-%s %s%s: %s € (%s)", origin, dest, dep, f"/{ret}" if ret else "", price_pp,
             booking["with"] if booking else "fără link de rezervare")
    return {"ok": True, "found": True, "price_eur": price_pp, "total_eur": total, "airline": name,
            "stops": stops, "url": url, "booking": booking, "link": link, "checked_at": now_str(),
            "price_level": insights.get("price_level"), "typical_range": insights.get("typical_price_range")}


# Regiunile (Google „Explore”): o căutare aduce zeci de destinații cu prețul real Google Flights
EXPLORE_AREAS = {
    "Asia": "/m/0j0k", "Orientul Mijlociu": "/m/04wsz", "Africa": "/m/0dg3n1", "America de Nord": "/m/059g4",
    "America de Sud": "/m/06n3y", "Caraibe": "/m/0261m", "Oceania": "/m/05nrg",
}


def explore(cfg, db, origin="BUD", areas=None):
    """Destinațiile exotice cu prețul real Google (dus-întors, ~2 săptămâni, oricând în următoarele 6 luni).
    O căutare pe regiune. Linkul deschide Google Flights pe exact ruta și datele găsite."""
    rows, info = [], {}
    for name, area in (areas or EXPLORE_AREAS).items():
        try:
            data = _search(cfg, db, {
                "engine": "google_travel_explore", "api_key": _key(cfg), "departure_id": origin,
                "arrival_area_id": area, "type": "1", "travel_duration": "3", "travel_mode": "1",
                "currency": "EUR", "hl": "ro", "gl": "ro",
            })
        except Exception as e:
            log.warning("Google Explore %s: %s", name, e)
            info[name] = 0
            continue
        n = 0
        for x in data.get("destinations") or []:
            code = (x.get("destination_airport") or {}).get("code")
            dep, ret, price = x.get("start_date"), x.get("end_date"), x.get("flight_price")
            if not (code and dep and ret and price):
                continue
            stops = int(x.get("number_of_stops") or 0)
            airline = (x.get("airline") or "Google Flights").replace(" și ", " + ").replace(" and ", " + ")
            airline += " · direct" if not stops else f" · {stops} {'escală' if stops == 1 else 'escale'}"
            rows.append({
                "source": SOURCE, "origin": origin, "dest": code, "dep_date": dep, "ret_date": ret,
                "price_eur": float(price), "price_orig": float(price), "currency": "EUR",
                "dep_time": "", "ret_time": "", "flight_no": x.get("airline_code") or "", "airline": airline,
                "link": google_flights_link(origin, code, dep, ret),
            })
            n += 1
        info[name] = n
    # aceeași destinație din două regiuni: păstrăm cel mai mic preț
    best = {}
    for r in rows:
        k = (r["dest"], r["dep_date"], r["ret_date"])
        if k not in best or r["price_eur"] < best[k]["price_eur"]:
            best[k] = r
    scan = db.q1("SELECT max(id) AS id FROM scans")
    db.upsert_rows(scan["id"] if scan else None, list(best.values()))
    db.set_kv("prices_updated_at", now_str())
    log.info("Google Explore din %s: %s destinații cu preț real (%s)", origin, len(best), info)
    return {"found": len(best), "areas": info}


def used_this_month(db):
    return (db.get_kv("serpapi_used", {}) or {}).get(dt.date.today().strftime("%Y-%m"), 0)
