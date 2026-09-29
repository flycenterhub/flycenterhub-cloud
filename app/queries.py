"""Interogări pentru dashboard."""
import datetime as dt

from . import fx, telegram
from .analysis import best_per_route
from .fmt import ORIGIN_NAMES, country_ro, nights
from .regions import REGION_LABELS, is_exotic_text, region_of
from .sources import ryanair, wizzair
from .sources.common import google_flights_link


def _places(db):
    return {r["code"]: {**r, "name": (r["name"] or "").strip() or None, "country": country_ro((r["country"] or "").strip()),
                        "country_en": (r["country"] or "").strip()}
            for r in db.q("SELECT * FROM places")}


def _enrich(rows, places):
    for r in rows:
        trip = r.get("trip") or ("RT" if r.get("ret_date") else "OW")
        r["trip"] = trip
        r["origin_name"] = ORIGIN_NAMES.get(r["origin"]) or (places.get(r["origin"]) or {}).get("name") or r["origin"]
        p = places.get(r["dest"]) or {}
        r["dest_name"] = ORIGIN_NAMES.get(r["dest"]) or p.get("name") or r["dest"]
        r["country"] = p.get("country") or ""
        r["nights"] = nights(r["dep_date"], r.get("ret_date"))
        if r.get("price_ron") is None:
            r["price_ron"] = fx.lei_of(r["price_eur"], r.get("price_orig"), r.get("currency"))
            r["lei_exact"] = (r.get("currency") or "").upper() == "RON"
        r["gf_link"] = google_flights_link(r["origin"], r["dest"], r["dep_date"], r.get("ret_date"))
    return rows


def deals(db, origins=None, exact=False):
    """Cea mai bună ofertă pe rută din orașele active (exact=True: doar Wizz Air și Ryanair)."""
    rows = db.q("""SELECT d.*, f.price_orig, f.currency, f.last_seen, f.first_seen FROM deals d LEFT JOIN fares f
                  ON f.source = d.source AND f.origin = d.origin AND f.dest = d.dest
                 AND f.dep_date = d.dep_date AND f.ret_date = d.ret_date""")
    if exact:
        rows = [r for r in rows if r["source"] != "aviasales"]
    if origins:
        rows = [r for r in rows if r["origin"] in origins]
    best = best_per_route(rows)
    new_keys = {f"{r['origin']}-{r['dest']}-{r['trip']}" for r in rows if r.get("is_new")}
    for b in best:
        b["is_new"] = 1 if f"{b['origin']}-{b['dest']}-{b['trip']}" in new_keys else 0
    return _enrich(best, _places(db))


def route_deals(db, origin, dest, trip):
    rows = db.q("""SELECT d.*, f.price_orig, f.currency, f.last_seen, f.first_seen FROM deals d LEFT JOIN fares f
                  ON f.source = d.source AND f.origin = d.origin AND f.dest = d.dest
                 AND f.dep_date = d.dep_date AND f.ret_date = d.ret_date
                   WHERE d.origin=? AND d.dest=? AND d.trip=? ORDER BY d.price_eur, d.dep_date""",
                (origin, dest, trip))
    return _enrich(rows, _places(db))


def last_minute(db, cfg, days, exact=False):
    origins = cfg["origins"]
    today = dt.date.today()
    until = (today + dt.timedelta(days=days)).isoformat()
    ph = ",".join("?" * len(origins))
    rows = db.q(
        f"""SELECT f.source, f.origin, f.dest, f.dep_date, f.ret_date, f.price_eur, f.dep_time, f.ret_time,
                   f.airline, f.link, f.price_orig, f.currency, f.last_seen, f.first_seen, s.typical_eur,
                   CASE WHEN f.ret_date = '' THEN 'OW' ELSE 'RT' END AS trip
            FROM fares f LEFT JOIN route_stats s
              ON s.origin = f.origin AND s.dest = f.dest AND s.trip = CASE WHEN f.ret_date = '' THEN 'OW' ELSE 'RT' END
            WHERE f.origin IN ({ph}) AND f.dep_date >= ? AND f.dep_date <= ? {"AND f.source != 'aviasales'" if exact else ""}
            ORDER BY f.price_eur LIMIT 600""", (*origins, today.isoformat(), until))
    for r in rows:
        t = r.get("typical_eur")
        r["discount_pct"] = round((t - r["price_eur"]) / t * 100, 1) if t else None
        r["days_to_dep"] = (dt.date.fromisoformat(r["dep_date"]) - today).days
    return _enrich(rows, _places(db))


def destinations(db, cfg, exact=False):
    """Pentru fiecare destinație: cel mai mic preț din fiecare oraș de plecare (dus și dus-întors)."""
    origins = cfg["origins"]
    ph = ",".join("?" * len(origins))
    fares = db.q(f"""SELECT origin, dest, dep_date, ret_date, price_eur, price_orig, currency, link, source, first_seen
                      FROM fares WHERE origin IN ({ph}) {"AND source != 'aviasales'" if exact else ""}""", origins)
    grouped = {}
    for f in fares:
        k = (f["origin"], f["dest"], "RT" if f["ret_date"] else "OW")
        g = grouped.get(k)
        if g is None:
            grouped[k] = g = {"best": f, "n": 0, "newest": ""}
        g["n"] += 1
        g["newest"] = max(g["newest"], f["first_seen"] or "")
        if f["price_eur"] < g["best"]["price_eur"]:
            g["best"] = f
    rows = [{"origin": k[0], "dest": k[1], "trip": k[2], "min_eur": g["best"]["price_eur"], "n": g["n"],
             "newest": g["newest"], "best": g["best"]} for k, g in grouped.items()]
    stats = {(s["origin"], s["dest"], s["trip"]): s for s in db.q("SELECT * FROM route_stats")}
    places = _places(db)
    out = {}
    for r in rows:
        d = out.setdefault(r["dest"], {"dest": r["dest"], "dest_name": (places.get(r["dest"]) or {}).get("name") or r["dest"],
                                       "country": (places.get(r["dest"]) or {}).get("country") or "",
                                       "OW": {}, "RT": {}, "min_ow": None, "min_rt": None, "newest": ""})
        d["newest"] = max(d["newest"], r["newest"] or "")
        st = stats.get((r["origin"], r["dest"], r["trip"])) or {}
        b = r["best"]
        d[r["trip"]][r["origin"]] = {"min_eur": r["min_eur"], "typical_eur": st.get("typical_eur"), "n": r["n"],
                                     "date": b["dep_date"], "ret": b["ret_date"], "link": b["link"], "source": b["source"],
                                     "price_ron": fx.lei_of(b["price_eur"], b["price_orig"], b["currency"])}
        k = "min_ow" if r["trip"] == "OW" else "min_rt"
        if d[k] is None or r["min_eur"] < d[k]:
            d[k] = r["min_eur"]
    return sorted(out.values(), key=lambda x: (x["min_ow"] if x["min_ow"] is not None else 9999))


def route(db, origin, dest, exact=False):
    places = _places(db)
    p = places.get(dest) or {}
    # La destinațiile obișnuite doar prețuri exacte; la cele exotice și Aviasales (singura sursă pentru ele)
    src = "AND source != 'aviasales'" if exact and not region_of(dest, p.get("cc"), p.get("country_en")) else ""
    cal = db.q(f"""SELECT dep_date, MIN(price_eur) AS price_eur FROM fares
                  WHERE origin=? AND dest=? AND ret_date='' {src} GROUP BY dep_date ORDER BY dep_date""", (origin, dest))
    cal_rt = db.q(f"""SELECT dep_date, MIN(price_eur) AS price_eur FROM fares
                     WHERE origin=? AND dest=? AND ret_date!='' {src} GROUP BY dep_date ORDER BY dep_date""", (origin, dest))
    hist = db.q("SELECT day, trip, min_eur, p50_eur FROM route_daily WHERE origin=? AND dest=? ORDER BY day",
                (origin, dest))
    fares = db.q(f"""SELECT * FROM fares WHERE origin=? AND dest=? {src} ORDER BY price_eur LIMIT 60""", (origin, dest))
    stats = db.q("SELECT * FROM route_stats WHERE origin=? AND dest=?", (origin, dest))
    return {
        "origin": origin, "dest": dest,
        "origin_name": ORIGIN_NAMES.get(origin, origin),
        "dest_name": (places.get(dest) or {}).get("name") or dest,
        "country": (places.get(dest) or {}).get("country") or "",
        "calendar_ow": cal, "calendar_rt": cal_rt, "history": hist,
        "cheapest": _enrich(fares, places), "stats": {s["trip"]: s for s in stats},
    }


def _lei(r):
    return fx.lei_of(r["price_eur"], r.get("price_orig"), r.get("currency"))


def _leg(r):
    return {"date": r["dep_date"], "time": r.get("dep_time") or "", "airline": r.get("airline") or "",
            "price_eur": r["price_eur"], "price_ron": _lei(r), "link": r.get("link") or "", "source": r["source"],
            "last_seen": r.get("last_seen")}


def _rt_item(r):
    return {"origin": r["origin"], "dest": r["dest"], "trip": "RT", "dep_date": r["dep_date"],
            "ret_date": r["ret_date"], "price_eur": r["price_eur"],
            "out": {"date": r["dep_date"], "time": r.get("dep_time") or "", "airline": r.get("airline") or "",
                    "price_eur": None, "link": "", "source": r["source"]},
            "back": {"date": r["ret_date"], "time": r.get("ret_time") or "", "airline": r.get("airline") or "",
                     "price_eur": None, "link": "", "source": r["source"]},
            "link": r.get("link") or "", "airline": r.get("airline") or "",
            "price_ron": _lei(r), "lei_exact": (r.get("currency") or "") == "RON",
            "source": r["source"], "last_seen": r.get("last_seen"), "first_seen": r.get("first_seen")}


def search(db, cfg, dep_from="", dep_to="", ret_from="", ret_to="", origin="", trip="ALL", exact=False):
    """Cel mai ieftin zbor spre fiecare destinație, din fiecare oraș de plecare.

    Fără date: toate zborurile (dus și/sau dus-întors, după `trip`). Cu dată de plecare: doar dus pe
    acele zile. Cu dată de întoarcere: combină cel mai ieftin dus cu cel mai ieftin întors (pot fi
    companii diferite) + dus-întors Aviasales.
    """
    origins = [origin] if origin in cfg["origins"] else list(cfg["origins"])
    ph = ",".join("?" * len(origins))
    stats = {(s["origin"], s["dest"], s["trip"]): s for s in db.q("SELECT * FROM route_stats")}
    no_dates = not dep_from
    if no_dates:
        dep_from, dep_to = dt.date.today().isoformat(), "9999-12-31"
    only_exact = exact
    exact = "AND source != 'aviasales'" if only_exact else ""  # exact=True: doar Wizz Air și Ryanair
    outs = db.q(f"SELECT * FROM fares WHERE origin IN ({ph}) AND ret_date='' AND dep_date BETWEEN ? AND ? {exact}",
                (*origins, dep_from, dep_to))
    best = {}
    if not ret_from and (not no_dates or trip in ("ALL", "OW")):
        for r in outs:
            k = (r["origin"], r["dest"], "OW")
            if k not in best or r["price_eur"] < best[k]["price_eur"]:
                best[k] = {"origin": r["origin"], "dest": r["dest"], "trip": "OW", "dep_date": r["dep_date"],
                           "ret_date": "", "price_eur": r["price_eur"], "out": _leg(r), "back": None,
                           "link": r.get("link") or "", "airline": r.get("airline") or "",
                           "price_ron": _lei(r), "lei_exact": (r.get("currency") or "") == "RON",
                           "source": r["source"], "last_seen": r.get("last_seen"), "first_seen": r.get("first_seen")}
    if no_dates and trip in ("ALL", "RT"):
        # Dus-întors deja calculate (retur cel mai ieftin între min_nights și max_nights nopți)
        rts = db.q(f"SELECT * FROM fares WHERE origin IN ({ph}) AND ret_date != '' AND dep_date >= ? {exact}",
                   (*origins, dep_from))
        backs = {(r["source"], r["origin"], r["dest"], r["dep_date"]): r for r in
                 db.q(f"SELECT * FROM fares WHERE dest IN ({ph}) AND ret_date = ''", origins)}
        out_idx = {(r["source"], r["origin"], r["dest"], r["dep_date"]): r for r in outs}
        for r in rts:
            k = (r["origin"], r["dest"], "RT")
            if k not in best or r["price_eur"] < best[k]["price_eur"]:
                item = _rt_item(r)
                o = out_idx.get((r["source"], r["origin"], r["dest"], r["dep_date"]))
                b = backs.get((r["source"], r["dest"], r["origin"], r["ret_date"]))
                if o and b and r["source"] != "aviasales":
                    item["out"], item["back"] = _leg(o), _leg(b)
                best[k] = item
    elif ret_from:
        backs = db.q(f"SELECT * FROM fares WHERE dest IN ({ph}) AND ret_date='' AND dep_date BETWEEN ? AND ? {exact}",
                     (*origins, ret_from, ret_to))
        by_out, by_back = {}, {}
        for r in outs:
            by_out.setdefault((r["origin"], r["dest"]), []).append(r)
        for r in backs:
            by_back.setdefault((r["dest"], r["origin"]), []).append(r)
        for k2, os_ in by_out.items():
            k = (*k2, "RT")
            for o in os_:
                for b in by_back.get(k2, []):
                    if b["dep_date"] <= o["dep_date"]:
                        continue
                    total = round(o["price_eur"] + b["price_eur"], 2)
                    if k in best and total >= best[k]["price_eur"]:
                        continue
                    same = o["source"] == b["source"]
                    link = ""
                    if same and o["source"] == "wizzair":
                        link = wizzair.booking_link(k[0], k[1], o["dep_date"], b["dep_date"])
                    elif same and o["source"] == "ryanair":
                        link = ryanair.booking_link(k[0], k[1], o["dep_date"], b["dep_date"])
                    airline = o.get("airline") if same else f"{o.get('airline')} + {b.get('airline')}"
                    best[k] = {"origin": k[0], "dest": k[1], "trip": "RT", "dep_date": o["dep_date"],
                               "ret_date": b["dep_date"], "price_eur": total, "out": _leg(o), "back": _leg(b),
                               "link": link, "airline": airline or "",
                               "price_ron": round(_lei(o) + _lei(b), 2),
                               "lei_exact": o.get("currency") == "RON" and b.get("currency") == "RON",
                               "source": o["source"] if o["source"] == b["source"] else "mixed",
                               "last_seen": min(o.get("last_seen") or "", b.get("last_seen") or ""),
                               "first_seen": max(o.get("first_seen") or "", b.get("first_seen") or "")}
    if ret_from and not only_exact:
        for r in db.q(f"""SELECT * FROM fares WHERE origin IN ({ph}) AND ret_date != '' AND source='aviasales'
                          AND dep_date BETWEEN ? AND ? AND ret_date BETWEEN ? AND ?""",
                      (*origins, dep_from, dep_to, ret_from, ret_to)):
            k = (r["origin"], r["dest"], "RT")
            if k not in best or r["price_eur"] < best[k]["price_eur"]:
                best[k] = _rt_item(r)
    rows = list(best.values())
    min_disc = cfg["deal_rules"]["min_discount_pct"]
    for r in rows:
        st = stats.get((r["origin"], r["dest"], r["trip"])) or {}
        t = st.get("typical_eur")
        r["typical_eur"] = t
        r["discount_pct"] = round((t - r["price_eur"]) / t * 100, 1) if t else None
        r["is_deal"] = bool(r["discount_pct"] is not None and r["discount_pct"] >= min_disc)
        r["days_to_dep"] = (dt.date.fromisoformat(r["dep_date"]) - dt.date.today()).days
    rows.sort(key=lambda x: x["price_eur"])
    return _enrich(rows, _places(db))


def exotic_origins(cfg):
    ex = cfg.get("exotic") or {}
    return [o for o in (ex.get("origins") or [ex.get("origin", "BUD")]) if o in cfg["origins"]] or [ex.get("origin", "BUD")]


def exotic(db, cfg, aviasales_on, dep_from="", dep_to="", ret_from="", ret_to="", exact=False):
    """Destinații din afara Europei din orașele configurate (Budapesta, București), orice companie, cu escală."""
    ex = cfg["exotic"]
    origins = exotic_origins(cfg)
    origin = origins[0]
    places = _places(db)
    marks = ",".join("?" * len(origins))
    stats = {(s["origin"], s["dest"], s["trip"]): s
             for s in db.q(f"SELECT * FROM route_stats WHERE origin IN ({marks})", origins)}
    today = dt.date.today()
    best, counts = {}, {}
    for r in db.q(f"SELECT * FROM fares WHERE origin IN ({marks}) AND dep_date >= ?", (*origins, today.isoformat())):
        if exact and r["source"] == "aviasales":
            continue
        p = places.get(r["dest"]) or {}
        reg = region_of(r["dest"], p.get("cc"), p.get("country_en"))
        if not reg:
            continue
        trip = "RT" if r["ret_date"] else "OW"
        if trip == "RT":
            n = nights(r["dep_date"], r["ret_date"])
            if n < ex["min_nights"] or n > ex["max_nights"]:
                continue
        if dep_from and not (dep_from <= r["dep_date"] <= dep_to):
            continue
        if ret_from and (trip != "RT" or not (ret_from <= r["ret_date"] <= ret_to)):
            continue
        k = (r["origin"], r["dest"], trip)
        counts[k] = counts.get(k, 0) + 1
        if k not in best or r["price_eur"] < best[k]["price_eur"]:
            best[k] = dict(r, trip=trip, region=reg)
    items = []
    for k, r in best.items():
        st = stats.get(k) or {}
        t = st.get("typical_eur")
        r["typical_eur"] = t
        r["discount_pct"] = round((t - r["price_eur"]) / t * 100, 1) if t else None
        r["region_label"] = REGION_LABELS[r["region"]]
        r["other_dates"] = counts[k] - 1
        r["days_to_dep"] = (dt.date.fromisoformat(r["dep_date"]) - today).days
        items.append(r)
    items.sort(key=lambda x: x["price_eur"])
    posts_ex = [p for p in db.q("SELECT * FROM posts ORDER BY coalesce(nullif(published, ''), first_seen) DESC")
                if set((p["cities"] or "").split(",")) & set(origins) and is_exotic_text(f"{p['title']} {p['summary']}")]
    names = [ORIGIN_NAMES.get(o, o) for o in origins]
    return {"origin": origin, "origins": origins, "origin_name": " și ".join(names), "aviasales": aviasales_on,
            "regions": REGION_LABELS, "fares": _enrich(items, places), "posts": posts_ex[:60]}


def favorites(db, keys, exact=False):
    """Prețul de acum pentru fiecare zbor favorit („origine|destinație|dus|întors”).
    Dus-întors fără bilet comun: cel mai ieftin dus + cel mai ieftin întors, pe exact acele date."""
    places = _places(db)
    out = {}
    for k in keys[:100]:
        parts = k.split("|")
        if len(parts) != 4:
            continue
        o, d, dep, ret = parts

        def best(a, b, day, back=""):
            rows = db.q("SELECT * FROM fares WHERE origin=? AND dest=? AND dep_date=? AND ret_date=? ORDER BY price_eur",
                        (a, b, day, back))
            rows = [r for r in rows if not (exact and r["source"] == "aviasales")]
            return dict(rows[0]) if rows else None
        r = best(o, d, dep, ret)
        if r:
            out[k] = _enrich([r], places)[0]
            continue
        if ret:
            a, b = best(o, d, dep), best(d, o, ret)
            if a and b:
                row = {"origin": o, "dest": d, "dep_date": dep, "ret_date": ret, "trip": "RT",
                       "price_eur": round(a["price_eur"] + b["price_eur"], 2), "source": "mixed",
                       "out": {"date": dep, "time": a["dep_time"], "airline": a["airline"], "price_eur": a["price_eur"],
                               "link": a["link"], "source": a["source"], "last_seen": a["last_seen"]},
                       "back": {"date": ret, "time": b["dep_time"], "airline": b["airline"], "price_eur": b["price_eur"],
                                "link": b["link"], "source": b["source"], "last_seen": b["last_seen"]}}
                out[k] = _enrich([row], places)[0]
    return out


def posts(db, days=45):
    since = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    return db.q("SELECT * FROM posts WHERE first_seen >= ? ORDER BY coalesce(nullif(published, ''), first_seen) DESC",
                (since,))


def status(engine):
    db, cfg = engine.db, engine.cfg
    last = db.last_scan("full")
    # ultima actualizare a prețurilor: orice scanare terminată (completă sau rapidă) sau prețurile Google
    any_scan = db.q1("SELECT max(finished_at) AS t FROM scans WHERE finished_at IS NOT NULL "
                     "AND status IN ('ok', 'partial')") or {}
    updated_at = max(filter(None, [any_scan.get("t"), db.get_kv("prices_updated_at")]), default=None)
    counts = db.q1("""SELECT (SELECT COUNT(*) FROM fares) AS fares,
                             (SELECT COUNT(DISTINCT origin || dest) FROM fares) AS routes,
                             (SELECT COUNT(*) FROM deals) AS deals,
                             (SELECT COUNT(*) FROM posts) AS posts,
                             (SELECT COUNT(DISTINCT day) FROM route_daily) AS history_days""")
    pct, eta = engine.progress_info()
    return {
        "running": engine.running,
        "progress": list(engine.progress.values()),
        "progress_pct": pct,
        "eta_min": eta,
        "scan_kind": engine.scan_kind,
        "data_version": engine.data_version,
        "last_scan": last,
        "updated_at": updated_at,
        "next_scan_at": engine.next_full_scan_at().strftime("%Y-%m-%d %H:%M:%S"),
        "next_check_at": min(x for x in (engine.next_full_scan_at(), engine.next_quick_scan_at()) if x)
                         .strftime("%Y-%m-%d %H:%M:%S"),
        "feeds_last": db.get_kv("feeds_last"),
        "counts": counts,
        "telegram": telegram.enabled(cfg),
        "origins": [{"code": c, "name": ORIGIN_NAMES.get(c, c)} for c in cfg["origins"]],
        "settings": {
            "scan_interval_hours": cfg["scan_interval_hours"],
            "feeds_interval_minutes": cfg["feeds_interval_minutes"],
            "months_ahead": cfg["months_ahead"],
            "last_minute_days": cfg["last_minute"]["days"],
            "round_trip": cfg["round_trip"],
            "aviasales": engine.source_enabled(cfg, "aviasales"),
            "rules": cfg["deal_rules"],
            "exotic": cfg["exotic"],
        },
        "eur_ron": fx.eur_ron(),
        "fx": fx.info(),
        "serpapi": {"enabled": bool(((cfg.get("serpapi") or {}).get("api_key") or "").strip()),
                    "used": (db.get_kv("serpapi_used", {}) or {}).get(dt.date.today().strftime("%Y-%m"), 0),
                    "limit": int((cfg.get("serpapi") or {}).get("monthly_limit", 100))},
        "public_site": {k: v for k, v in (db.get_kv("public_site") or {}).items() if k in ("url", "last_publish", "error")},
    }
