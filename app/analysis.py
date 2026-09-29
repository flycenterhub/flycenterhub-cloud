"""Detectarea ofertelor: compară fiecare preț cu istoricul rutei.

Pentru fiecare rută (plecare, destinație, dus / dus-întors) se salvează zilnic minimul și
mediana prețurilor. "Prețul obișnuit" = mediana ultimelor `baseline_days` zile. În prima zi,
comparația se face cu prețurile aceleiași rute în celelalte zile din calendar.
"""
import datetime as dt
import statistics
from collections import defaultdict

from .db import now_str
from .regions import region_of

FLAG_LABELS = {
    "SUB_MEDIE": "Mult sub prețul obișnuit",
    "MINIM": "Cel mai mic preț văzut",
    "SCADERE": "Preț scăzut recent",
    "SUPER": "Super ieftin",
    "LAST_MINUTE": "Last minute",
}


DEAL_COLS = ["source", "origin", "dest", "trip", "dep_date", "ret_date", "price_eur", "typical_eur",
             "discount_pct", "min_prev_eur", "prev_price_eur", "history_days", "flags", "score",
             "days_to_dep", "dep_time", "ret_time", "airline", "flight_no", "link", "computed_at", "is_new"]


def _pct(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo), 2)


def trip_of(row):
    return "RT" if row.get("ret_date") else "OW"


def route_key(r):
    return f"{r['origin']}-{r['dest']}-{r['trip']}"


def run(cfg, db, final=True):
    today = dt.date.today()
    tiso = today.isoformat()
    origins = cfg["origins"]
    ph = ",".join("?" * len(origins))
    fares = db.q(f"SELECT * FROM fares WHERE origin IN ({ph})", origins)
    place_of = {r["code"]: (r.get("cc"), (r.get("country") or "").strip()) for r in db.q("SELECT code, cc, country FROM places")}

    groups = defaultdict(list)
    for r in fares:
        groups[(r["origin"], r["dest"], trip_of(r))].append(r)

    # 1) Statistica de azi pentru fiecare rută
    daily = []
    for (o, d, t), rs in groups.items():
        # prețul obișnuit al rutei se calculează din prețurile exacte (Wizz Air, Ryanair) când există
        prices = sorted(x["price_eur"] for x in ([x for x in rs if x["source"] != "aviasales"] or rs))
        daily.append((tiso, o, d, t, prices[0], _pct(prices, 25), round(statistics.median(prices), 2), len(prices)))
    with db.lock:
        db.conn.executemany(
            "INSERT INTO route_daily(day, origin, dest, trip, min_eur, p25_eur, p50_eur, n) VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(day, origin, dest, trip) DO UPDATE SET min_eur=excluded.min_eur, "
            "p25_eur=excluded.p25_eur, p50_eur=excluded.p50_eur, n=excluded.n", daily)
        db.conn.commit()

    # 2) Prețul obișnuit și minimul anterior
    start = (today - dt.timedelta(days=int(cfg["baseline_days"]))).isoformat()
    hist = defaultdict(list)
    for h in db.q("SELECT * FROM route_daily WHERE day >= ?", (start,)):
        hist[(h["origin"], h["dest"], h["trip"])].append(h)
    stats = {}
    for key in groups:
        hs = hist.get(key, [])
        prev = [h for h in hs if h["day"] < tiso]
        today_row = next((h for h in hs if h["day"] == tiso), None)
        stats[key] = {
            "typical": round(statistics.median([h["p50_eur"] for h in hs]), 2) if hs else None,
            "min_prev": min(h["min_eur"] for h in prev) if prev else None,
            "prev_days": len(prev),
            "history_days": len(hs),
            "n_today": today_row["n"] if today_row else 0,
        }
    with db.lock:
        db.conn.execute("DELETE FROM route_stats")
        db.conn.executemany(
            "INSERT INTO route_stats(origin, dest, trip, typical_eur, min_prev_eur, history_days, n_today) "
            "VALUES(?,?,?,?,?,?,?)",
            [(k[0], k[1], k[2], s["typical"], s["min_prev"], s["history_days"], s["n_today"])
             for k, s in stats.items()])
        db.conn.commit()

    # 3) Ofertele
    base_rules = cfg["deal_rules"]
    ex = cfg.get("exotic") or {}
    exotic_rules = {**base_rules, **{k: ex[k] for k in ("max_price_ow_eur", "max_price_rt_eur",
                                                          "super_cheap_ow_eur", "super_cheap_rt_eur") if k in ex}}
    lm = cfg["last_minute"]
    recent = (dt.datetime.now() - dt.timedelta(hours=36)).strftime("%Y-%m-%d %H:%M:%S")
    computed = now_str()
    deals = []
    for key, rs in groups.items():
        st = stats[key]
        typical = st["typical"]
        trip = key[2]
        ow = trip == "OW"
        rules = exotic_rules if region_of(key[1], *place_of.get(key[1], (None, None))) else base_rules
        # Zborurile lungi au puține prețuri (Aviasales): cerem istoric sau suficiente date
        reliable = st["n_today"] >= 5 or st["history_days"] >= 3
        for r in rs:
            price = r["price_eur"]
            days_to = (dt.date.fromisoformat(r["dep_date"]) - today).days
            disc = round((typical - price) / typical * 100, 1) if typical else 0.0
            flags = []
            if reliable and disc >= rules["min_discount_pct"]:
                flags.append("SUB_MEDIE")
            if st["min_prev"] is not None and st["prev_days"] >= 2 and price < st["min_prev"] - 0.5 and disc >= 15:
                flags.append("MINIM")
            prev = r.get("prev_price_eur")
            drop = 0.0
            if prev and r.get("price_changed_at") and r["price_changed_at"] >= recent and prev > price:
                drop = round((prev - price) / prev * 100, 1)
                if drop >= rules["drop_pct"] and prev - price >= 5:
                    flags.append("SCADERE")
            if price <= (rules["super_cheap_ow_eur"] if ow else rules["super_cheap_rt_eur"]):
                flags.append("SUPER")
            if days_to <= lm["days"] and price <= (lm["max_ow_eur"] if ow else lm["max_rt_eur"]):
                flags.append("LAST_MINUTE")
            if not flags or price > (rules["max_price_ow_eur"] if ow else rules["max_price_rt_eur"]):
                continue
            score = max(disc, 0)
            score += 20 if "MINIM" in flags else 0
            score += min(drop, 60) * 0.5 if "SCADERE" in flags else 0
            score += 15 if "SUPER" in flags else 0
            score += 10 if "LAST_MINUTE" in flags else 0
            score += max(0, (30 if ow else 70) - price) * 0.5
            deals.append({
                "source": r["source"], "origin": r["origin"], "dest": r["dest"], "trip": trip,
                "dep_date": r["dep_date"], "ret_date": r["ret_date"], "price_eur": price,
                "typical_eur": typical, "discount_pct": disc, "min_prev_eur": st["min_prev"],
                "prev_price_eur": prev if "SCADERE" in flags else None,
                "history_days": st["history_days"], "flags": ",".join(flags), "score": round(score, 1),
                "days_to_dep": days_to, "dep_time": r.get("dep_time"), "ret_time": r.get("ret_time"),
                "airline": r.get("airline"), "flight_no": r.get("flight_no"), "link": r.get("link"),
                "computed_at": computed, "is_new": 0,
                # doar pentru afișarea prețului în lei (nu se salvează în tabelul deals)
                "price_orig": r.get("price_orig"), "currency": r.get("currency"),
            })

    # 4) Care sunt noi față de analiza anterioară (cel mai bun preț pe rută)
    best = best_per_route(deals)
    prev_best = db.get_kv("prev_best", {})
    new_keys = set()
    for b in best:
        k = route_key(b)
        old = prev_best.get(k)
        if prev_best and (old is None or b["price_eur"] <= old * 0.95):
            new_keys.add(k)
    for d in deals:
        if route_key(d) in new_keys:
            d["is_new"] = 1
    if final:
        db.set_kv("prev_best", {route_key(b): b["price_eur"] for b in best})

    cols = DEAL_COLS
    with db.lock:
        db.conn.execute("DELETE FROM deals")
        if deals:
            db.conn.executemany(
                f"INSERT OR REPLACE INTO deals({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})",
                [tuple(d[c] for c in cols) for d in deals])
        db.conn.commit()
    return deals


def best_per_route(deals):
    """Cea mai bună ofertă pe fiecare rută (copii), cu numărul de alte date bune."""
    best = {}
    counts = defaultdict(int)
    for d in deals:
        k = route_key(d)
        counts[k] += 1
        cur = best.get(k)
        if cur is None or (d["score"], -d["price_eur"]) > (cur["score"], -cur["price_eur"]):
            best[k] = d
    out = []
    for k, d in best.items():
        d = dict(d)
        d["other_dates"] = counts[k] - 1
        out.append(d)
    return sorted(out, key=lambda x: (-x["score"], x["price_eur"]))


def select_alerts(cfg, db, deals):
    """Rutele care merită trimise pe Telegram acum. Returnează (listă, prima_rulare)."""
    tg = cfg["telegram"]
    best = best_per_route(deals)
    notified = {r["route_key"]: r for r in db.q("SELECT * FROM notified")}
    first = not db.get_kv("alerts_initialized", False)
    if first:
        return best, True
    limit = (dt.datetime.now() - dt.timedelta(days=int(tg["renotify_after_days"]))).strftime("%Y-%m-%d %H:%M:%S")
    out = []
    for b in best:
        n = notified.get(route_key(b))
        if n:
            improved = b["price_eur"] <= n["price_eur"] * (1 - tg["renotify_improvement_pct"] / 100)
            expired = n["notified_at"] < limit
            if not (improved or expired):
                continue
        out.append(b)
    return out, False


def mark_notified(db, items):
    ts = now_str()
    with db.lock:
        db.conn.executemany(
            "INSERT INTO notified(route_key, price_eur, notified_at) VALUES(?,?,?) "
            "ON CONFLICT(route_key) DO UPDATE SET price_eur=excluded.price_eur, notified_at=excluded.notified_at",
            [(route_key(i), i["price_eur"], ts) for i in items])
        db.conn.commit()
    db.set_kv("alerts_initialized", True)
