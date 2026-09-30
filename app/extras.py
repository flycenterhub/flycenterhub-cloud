"""Vremea medie la destinație și escalele făcute de tine (două bilete low-cost separate).

Vremea: medii lunare 2001–2020 de la NASA POWER (date publice, fără cheie), pe coordonatele aeroportului.
Escale: zborurile Ryanair din aeroporturile mari (Bergamo, Charleroi, Barcelona…) spre restul Europei,
combinate cu zborurile noastre spre acele aeroporturi, în aceeași zi (cu timp de escală sigur) sau a doua zi.
"""
import datetime as dt
import logging
import math
import os
import time

from . import fx, net
from .db import now_str

log = logging.getLogger("extras")

# ---------- vremea ----------
POWER = ("https://power.larc.nasa.gov/api/temporal/climatology/point?parameters=T2M,PRECTOTCORR"
         "&community=RE&longitude={lon:.3f}&latitude={lat:.3f}&format=JSON")
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
DAYS = [31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def refresh_climate(db, limit=None):
    """kv „climate” = {cod: [[temp. medie °C, ploaie mm/lună] × 12 luni]}. Se aduc doar destinațiile noi."""
    have = db.get_kv("climate") or {}
    if os.environ.get("FCH_CLOUD") and len(have) < 100:
        try:  # în cloud: preluăm ce a adus deja laptopul
            data = net.get_json("https://flycenterhub.github.io/data/climate.json", timeout=30)
            if isinstance(data, dict):
                have.update(data)
                db.set_kv("climate", have)
        except Exception as e:
            log.warning("Vremea de pe site: %s", e)
    coords = db.get_kv("coords") or {}
    missing = [c for c in sorted(coords) if c not in have]
    if limit:
        missing = missing[:limit]
    got = 0
    for n, code in enumerate(missing):
        lon, lat = coords[code]
        try:
            p = net.get_json(POWER.format(lon=lon, lat=lat), timeout=60, retries=2, backoff=10)["properties"]["parameter"]
            t, r = p["T2M"], p["PRECTOTCORR"]
            if any(t[m] <= -900 or r[m] < 0 for m in MON):
                continue
            have[code] = [[round(t[m], 1), round(r[m] * DAYS[i])] for i, m in enumerate(MON)]
            got += 1
        except Exception as e:
            log.warning("Vremea %s: %s", code, e)
            time.sleep(5)
        if n % 25 == 24:
            db.set_kv("climate", have)
        time.sleep(0.4)
    db.set_kv("climate", have)
    if got:
        log.info("Vremea medie: %s destinații noi (%s în total)", got, len(have))
    return got


def public_climate(db):
    return db.get_kv("climate") or {}


# ---------- escale făcute de tine ----------
RYANAIR = "https://www.ryanair.com/api/farfnd/v4"
# Bazele mari Ryanair din Europa (au cele mai multe rute mai departe)
HUB_CANDIDATES = ["BGY", "CIA", "BVA", "CRL", "STN", "BCN", "MAD", "MLA", "DUB", "BLQ", "NAP", "PMO", "CTA",
                  "VIE", "WMI", "KRK", "BRI", "TSF", "PSA", "EIN", "NRN", "MXP", "FCO", "LTN", "AGP", "ALC",
                  "PMI", "LIS", "OPO", "VLC", "SVQ", "TPS", "CAG", "TRN", "VCE", "BER", "HHN", "KTW", "POZ",
                  "GDN", "BTS", "ZAD", "PFO", "ATH", "SKG", "MRS", "BOD", "TLS", "MAN", "EDI", "BHX"]
MAX_HUBS = 20
MIN_TRANSFER = 180        # minute între aterizare și decolare, minim (bilete separate)
MAX_WAIT = 30 * 60        # escala cea mai lungă acceptată (cu o noapte acolo)
SKIP_CC = {"ro", "hu"}    # „escale” spre România / Ungaria n-au rost


def _km(a, b):
    (lo1, la1), (lo2, la2) = a, b
    p = math.pi / 180
    h = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def _flight_min(km):
    """Durata zborului, cu rezervă: 30 min (rulare, urcare) + 750 km/h. Se folosește doar ca prag de siguranță."""
    return 30 + km / 12.5


def pick_hubs(db, cfg):
    """Aeroporturile-hub la care ajungem direct, ordonate după câte zile avem zboruri ieftine spre ele."""
    origins = cfg["origins"]
    ph = ",".join("?" * len(origins))
    rows = db.q(f"""SELECT dest, COUNT(DISTINCT dep_date) n FROM fares
                    WHERE origin IN ({ph}) AND ret_date='' AND source IN ('ryanair','wizzair') AND dep_time<>''
                    GROUP BY dest""", tuple(origins))
    n = {r["dest"]: r["n"] for r in rows}
    return sorted([h for h in HUB_CANDIDATES if h in n], key=lambda h: -n[h])[:MAX_HUBS]


def scan_hubs(cfg, db, progress, stop):
    """Cele mai ieftine zboruri Ryanair din fiecare hub, pe săptămâni -> kv „hub_fares”."""
    hubs = pick_hubs(db, cfg)
    today = dt.date.today()
    end = today + dt.timedelta(days=int(cfg.get("months_ahead", 6)) * 30)
    weeks = []
    s = today
    while s <= end:
        weeks.append((s, min(s + dt.timedelta(days=6), end)))
        s += dt.timedelta(days=7)
    delay = max(1.5, float(cfg.get("request_delay_seconds", 0.8)))
    rows, places, fails = [], [], 0
    total = len(hubs) * len(weeks)
    for i, hub in enumerate(hubs):
        for j, (a, b) in enumerate(weeks):
            if stop.is_set():
                return {"hubs": len(hubs), "fares": len(rows), "stopped": True}
            progress(f"Escale {hub} {a:%d.%m}", i * len(weeks) + j, total)
            url = (f"{RYANAIR}/oneWayFares?departureAirportIataCode={hub}&outboundDepartureDateFrom={a}"
                   f"&outboundDepartureDateTo={b}&market=ro-ro&adultPaxCount=1")
            try:
                data = net.get_json(url, headers={"Accept": "application/json"}, retries=2, backoff=20)
            except Exception as e:
                fails += 1
                log.warning("Escale %s: %s", hub, e)
                time.sleep(delay * 4)
                if fails > 15:
                    break
                continue
            for f in data.get("fares") or []:
                ob = f["outbound"]
                price = ob.get("price") or {}
                cur = price.get("currencyCode") or "EUR"
                eur = fx.to_eur(price["value"], cur) if price.get("value") else None
                arr = ob["arrivalAirport"]
                cc = ((arr.get("city") or {}).get("countryCode") or "").lower()
                if eur is None or cc in SKIP_CC:
                    continue
                places.append((arr["iataCode"], arr.get("name"), arr.get("countryName"), cc))
                rows.append([hub, arr["iataCode"], ob["departureDate"][:10], ob["departureDate"][11:16],
                             (ob.get("arrivalDate") or "")[11:16], round(eur, 2)])
            time.sleep(delay)
    if rows:
        db.save_places(places)
        db.set_kv("hub_fares", {"at": now_str(), "hubs": hubs, "rows": rows})
    return {"hubs": len(hubs), "fares": len(rows)}


def connections(db, cfg, per_route=4, cap=2500):
    """Combinațiile oraș -> hub -> destinație mai ieftine decât zborul direct (sau fără zbor direct)."""
    from .sources.ryanair import booking_link
    hf = db.get_kv("hub_fares") or {}
    legs2 = hf.get("rows") or []
    if not legs2:
        return []
    origins = cfg["origins"]
    coords = db.get_kv("coords") or {}
    today = dt.date.today().isoformat()
    hubs = sorted({r[0] for r in legs2})
    ph, hh = ",".join("?" * len(origins)), ",".join("?" * len(hubs))
    first = {}
    for f in db.q(f"""SELECT source, origin, dest, dep_date, dep_time, price_eur, airline, link FROM fares
                      WHERE origin IN ({ph}) AND dest IN ({hh}) AND ret_date='' AND dep_time<>''
                        AND source IN ('ryanair','wizzair') AND dep_date>=? AND price_eur>0""",
                  (*origins, *hubs, today)):
        first.setdefault((f["dest"], f["dep_date"]), []).append(f)
    direct = {}
    for f in db.q(f"SELECT origin, dest, MIN(price_eur) p FROM fares WHERE origin IN ({ph}) AND ret_date='' GROUP BY origin, dest",
                  tuple(origins)):
        direct[(f["origin"], f["dest"])] = f["p"]
    best = {}
    for hub, dest, day, t2, arr2, p2 in legs2:
        if dest in origins or day < today or not t2:
            continue
        d2 = dt.datetime.strptime(f"{day} {t2}", "%Y-%m-%d %H:%M")
        prev = (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()
        for leg_day in (day, prev):
            for f in first.get((hub, leg_day), []):
                o = f["origin"]
                if o == dest:
                    continue
                d1 = dt.datetime.strptime(f"{f['dep_date']} {f['dep_time']}", "%Y-%m-%d %H:%M")
                # orele sunt locale: hub-urile sunt la vest sau în același fus, deci timpul real e mai lung (în siguranță)
                fly = _flight_min(_km(coords[o], coords[hub])) if o in coords and hub in coords else 240
                wait = (d2 - d1).total_seconds() / 60
                if wait < fly + MIN_TRANSFER or wait > MAX_WAIT:
                    continue
                total = round(f["price_eur"] + p2, 2)
                dp = direct.get((o, dest))
                if dp is not None and total > dp - 10:
                    continue
                key = (o, dest)
                cand = {"origin": o, "hub": hub, "dest": dest, "dep_date": f["dep_date"], "price_eur": total,
                        "direct_eur": dp, "overnight": leg_day != day, "wait_min": round(wait - fly),
                        "l1": [f["source"], f["dep_date"], f["dep_time"], round(f["price_eur"], 2),
                               (f["airline"] or "").split(" · ")[0], f["link"]],
                        "l2": [day, t2, arr2, p2, booking_link(hub, dest, day)]}
                best.setdefault(key, []).append(cand)
    out = []
    for key, cands in best.items():
        cands.sort(key=lambda c: (c["price_eur"], c["overnight"]))
        seen = set()
        for c in cands:
            if c["dep_date"] in seen:
                continue
            seen.add(c["dep_date"])
            out.append(c)
            if len(seen) >= per_route:
                break
    out.sort(key=lambda c: c["price_eur"])
    return out[:cap]


def public_connections(db, cfg):
    """Pentru site: combinațiile + numele locurilor."""
    from .fmt import ORIGIN_NAMES, country_ro
    rows = connections(db, cfg)
    codes = {c for r in rows for c in (r["origin"], r["hub"], r["dest"])}
    names = {}
    for p in db.q("SELECT code, name, country FROM places"):
        if p["code"] in codes:
            names[p["code"]] = [ORIGIN_NAMES.get(p["code"], (p["name"] or p["code"]).strip()), country_ro((p["country"] or "").strip())]
    return {"at": (db.get_kv("hub_fares") or {}).get("at"), "rows": rows, "places": names}
