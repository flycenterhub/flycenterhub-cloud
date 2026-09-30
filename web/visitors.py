"""Statistici de vizitatori pentru site-ul public (GoatCounter), afișate doar în back-end-ul de pe laptop.

Numărarea o face scriptul GoatCounter pus pe site la publicare (fără cookie-uri). Cheia API (doar
„Read statistics”) o lipește userul în pagina Vizitatori; stă numai în baza locală, nu se publică
și nu se trimite nicăieri în afară de GoatCounter.
"""
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request

SITE = "flycenterhub"  # flycenterhub.goatcounter.com
COUNT_TAG = (f'<script data-goatcounter="https://{SITE}.goatcounter.com/count" '
             'async src="https://gc.zgo.at/count.js"></script>')
KEY = "goatcounter_token"
_cache = {}  # zile -> (moment, rezultat): GoatCounter limitează cererile, deci nu-l întrebăm des


def has_token(db):
    return bool(db.get_kv(KEY))


def set_token(db, token):
    db.set_kv(KEY, (token or "").strip())


def _get(token, path, **params):
    url = f"https://{SITE}.goatcounter.com/api/v0/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                               "Content-Type": "application/json",
                                               "User-Agent": "FlyCenterHub"})
    for attempt in range(4):
        time.sleep(0.7)  # GoatCounter răspunde cu 429 dacă primește cereri prea repede
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def stats(db, days=30):
    token = db.get_kv(KEY)
    if not token:
        return {"ok": False, "no_token": True}
    days = max(1, min(int(days or 30), 365))
    hit = _cache.get(days)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    end = dt.datetime.utcnow().replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
    start = (end - dt.timedelta(days=days)).replace(hour=0)
    rng = {"start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        total = _get(token, "stats/total", **rng)
        hits = _get(token, "stats/hits", limit=100, **rng)
        lists = {}
        for name in ("toprefs", "locations", "systems", "sizes"):
            try:
                lists[name] = [[s.get("name") or "(direct)", s.get("count", 0)]
                               for s in _get(token, f"stats/{name}", limit=10, **rng).get("stats", [])]
            except Exception:
                lists[name] = []
    except urllib.error.HTTPError as e:
        msg = "Cheia nu e bună sau nu are permisiunea „Read statistics”." if e.code in (401, 403) \
            else f"GoatCounter a răspuns cu eroarea {e.code}."
        return {"ok": False, "message": msg}
    except Exception as e:
        return {"ok": False, "message": f"Nu am putut contacta GoatCounter: {e}"}
    daily = [[s["day"], s.get("daily", 0)] for s in total.get("stats", [])]
    pages, events = [], []
    for h in hits.get("hits", []):
        (events if h.get("event") else pages).append([h.get("path"), h.get("count", 0)])
    res = {"ok": True, "days": days, "total": total.get("total", 0), "daily": daily,
            "pages": pages[:15], "events": sorted(events, key=lambda x: -x[1])[:30], **lists}
    _cache[days] = (time.time(), res)
    return res
