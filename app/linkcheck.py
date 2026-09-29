"""Verificarea zilnică a linkurilor „Rezervă”: fiecare link trebuie să ducă exact la zborul afișat.

1. Toate linkurile: se citește ce deschide linkul (ruta, datele) și se compară cu zborul. Dacă nu se
   potrivesc sau linkul e de un tip necunoscut, se înlocuiește cu un link corect.
2. Zborurile afișate ca oferte (Wizz Air / Ryanair): se confirmă la companie că zborul mai există
   în acea zi. Zborurile care nu mai există se scot din listă.
3. Rezervările exacte prin Google Flights: se verifică unde redirecționează. Dacă nu ajung la
   compania aeriană (link expirat), se înlocuiesc cu Google Flights pe exact ruta și datele zborului.
"""
import base64
import datetime as dt
import html
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .db import now_str
from .sources import ryanair, wizzair
from .sources.common import google_flights_link
from .sources.serpapi import CITY_AIRPORTS

log = logging.getLogger("linkcheck")


def _airports(code):
    return set((CITY_AIRPORTS.get(code, code)).split(",")) | {code}


COUNTRY = {}  # cod aeroport/oraș -> țară (din tabelul places), completat la fiecare verificare


def load_places(db):
    COUNTRY.clear()
    COUNTRY.update({r["code"]: r["cc"] for r in db.q("SELECT code, cc FROM places") if r["cc"]})


def _same_place(a, b):
    """Același aeroport, sau un aeroport al aceluiași oraș (ex. Paris -> Beauvais, Veneția -> Treviso)."""
    if _airports(a) & _airports(b):
        return True
    return bool(COUNTRY.get(a)) and COUNTRY.get(a) == COUNTRY.get(b)


# ---------- ce deschide un link (ruta și datele) ----------
def _pb_fields(b):
    """Câmpurile de pe primul nivel dintr-un mesaj protobuf: listă de (câmp, valoare)."""
    out, p = [], 0

    def varint():
        nonlocal p
        n, shift = 0, 0
        while True:
            x = b[p]
            p += 1
            n |= (x & 0x7F) << shift
            shift += 7
            if not x & 0x80:
                return n
    while p < len(b):
        key = varint()
        f, wt = key >> 3, key & 7
        if wt == 0:
            out.append((f, varint()))
        elif wt == 2:
            n = varint()
            out.append((f, b[p:p + n]))
            p += n
        else:
            raise ValueError("format necunoscut")
    return out


def _google_legs(url):
    """Zborurile dintr-un link Google Flights „tfs”: [(data, {aeroporturi plecare}, {aeroporturi sosire})]."""
    t = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("tfs", [""])[0]
    if not t:
        return None
    raw = base64.urlsafe_b64decode(t + "=" * (-len(t) % 4))
    legs = []
    for f, v in _pb_fields(raw):
        if f != 3:
            continue
        date, frm, to = "", set(), set()
        for g, w in _pb_fields(v):
            if g == 2:
                date = w.decode()
            elif g in (13, 14):
                code = dict(_pb_fields(w)).get(2, b"").decode()
                (frm if g == 13 else to).add(code)
        legs.append((date, frm, to))
    return legs


def describe(link):
    """(tip, plecare, sosire, dus, întors) pentru linkurile cunoscute; None dacă nu se poate citi."""
    if not link:
        return None
    u = urllib.parse.urlparse(link)
    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
    host = u.netloc.lower()
    if host.endswith("wizzair.com") and "/booking/select-flight/" in u.path:
        parts = u.path.split("/select-flight/", 1)[1].split("/")
        if len(parts) >= 4:
            return "wizzair", parts[0], parts[1], parts[2], "" if parts[3] == "null" else parts[3]
    if host.endswith("ryanair.com") and "/trip/flights/select" in u.path:
        return "ryanair", q.get("originIata"), q.get("destinationIata"), q.get("dateOut"), q.get("dateIn", "")
    if host.endswith("flypgs.com"):
        return "pegasus", q.get("departurePort"), q.get("arrivalPort"), q.get("departureDate"), q.get("returnDate", "")
    if host.endswith("google.com") and u.path.startswith("/travel/flights"):
        legs = _google_legs(link)
        if not legs:
            return None
        out = legs[0]
        back = legs[1] if len(legs) > 1 else None
        return "google", out[1], out[2], out[0], back[0] if back else "", back
    return None


def structure_ok(row, link):
    """Linkul deschide exact ruta și datele zborului din rând?"""
    if (link or "").startswith("gfpost:"):
        try:
            g = json.loads(link[7:])
        except ValueError:
            return False
        return bool(g.get("url")) and structure_ok(row, g.get("gf") or "")
    d = describe(link)
    if not d:
        return False
    kind, frm, to, dep, ret = d[:5]
    if dep != row["dep_date"] or (ret or "") != (row.get("ret_date") or ""):
        return False
    if kind == "google":
        back = d[5]
        places_ok = any(_same_place(a, row["origin"]) for a in frm) and any(_same_place(b, row["dest"]) for b in to)
        if back:
            places_ok = places_ok and any(_same_place(a, row["dest"]) for a in back[1]) and \
                any(_same_place(b, row["origin"]) for b in back[2])
        return places_ok
    return _same_place(frm or "", row["origin"]) and _same_place(to or "", row["dest"])


def correct_link(row):
    """Linkul corect pentru rând: la companie pentru Wizz Air / Ryanair, altfel Google Flights exact."""
    ret = row.get("ret_date") or ""
    if row["source"] == "wizzair":
        return wizzair.booking_link(row["origin"], row["dest"], row["dep_date"], ret)
    if row["source"] == "ryanair":
        return ryanair.booking_link(row["origin"], row["dest"], row["dep_date"], ret)
    return google_flights_link(row["origin"], row["dest"], row["dep_date"], ret)


# ---------- rezervarea exactă prin Google: unde duce acum ----------
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def gfpost_target(link):
    """Adresa la care duce acum formularul de rezervare Google (sau None dacă nu redirecționează)."""
    g = json.loads(link[7:])
    req = urllib.request.Request(g["url"], data=(g.get("post") or "").encode(), method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
        "Accept-Language": "ro-RO,ro;q=0.9"})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        body = opener.open(req, timeout=30).read(20000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            return e.headers.get("Location")
        return None
    # Google redirecționează printr-o pagină intermediară: <meta http-equiv="refresh" content="0;url='...'">
    m = re.search(r"""url=['"]?([^'">\s]+)""", body, re.I) if "refresh" in body.lower() else None
    return html.unescape(m.group(1)) if m else None


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def _next_hop(url):
    """Următoarea adresă dintr-un lanț de redirecționări (HTTP sau pagină intermediară), sau None."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ro-RO,ro;q=0.9"})
    try:
        body = urllib.request.build_opener(_NoRedirect).open(req, timeout=15).read(30000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location") if e.code in (301, 302, 303, 307, 308) else None
        return urllib.parse.urljoin(url, loc) if loc else None
    m = re.search(r"""url=['"]?([^'">\s]+)""", body, re.I) if "refresh" in body.lower() else None
    m = m or re.search(r"""location(?:\.href)?\s*=\s*['"]([^'"]+)""", body)
    return urllib.parse.urljoin(url, html.unescape(m.group(1))) if m else None


def _mentions_route(url, row):
    """Adresa conține codurile aeroporturilor zborului (ex. BUD-HAN, dep=BUD&dst=NQZ)?"""
    codes = set(re.findall(r"(?<![A-Za-z])([A-Z]{3})(?![A-Za-z])", urllib.parse.unquote(url)))
    return bool(codes & _airports(row["origin"])) and bool(codes & _airports(row["dest"]))


def gfpost_ok(link, row):
    """Rezervarea exactă prin Google duce (după toate redirecționările) la exact acest zbor?"""
    url = gfpost_target(link)
    for _ in range(5):
        if not url:
            return False
        host = urllib.parse.urlparse(url).netloc.lower()
        if not host.endswith("google.com") and _mentions_route(url, row):
            return True
        try:
            url = _next_hop(url)
        except Exception:
            return False  # site-ul final nu răspunde și adresa nu arată ruta: nu ne putem baza pe link
    return False


# ---------- verificarea completă ----------
def run(engine, live_limit=80):
    from .verify import FETCH
    db = engine.db
    load_places(db)
    t0 = time.time()
    rep = {"at": now_str(), "total": 0, "ok": 0, "fixed": 0, "removed": 0, "live_checked": 0, "problems": []}

    def note(kind, r, why):
        if len(rep["problems"]) < 30:
            rep["problems"].append({"kind": kind, "route": f"{r['origin']}-{r['dest']}", "dep": r["dep_date"],
                                    "ret": r.get("ret_date") or "", "source": r["source"], "why": why})

    # 1) toate linkurile salvate
    fixes = []
    for r in db.q("SELECT rowid, source, origin, dest, dep_date, ret_date, link FROM fares"):
        rep["total"] += 1
        link = r["link"] or ""
        if r["source"] in ("wizzair", "ryanair") and not link:
            link = correct_link(r)  # linkul se construiește din datele zborului
        if structure_ok(r, link):
            rep["ok"] += 1
            continue
        new = correct_link(r)
        fixes.append((new, r["rowid"]))
        note("link", r, f"linkul nu deschidea exact acest zbor ({(link or 'lipsă')[:70]})")
    with db.lock:
        db.conn.executemany("UPDATE fares SET link=? WHERE rowid=?", fixes)
        db.conn.commit()
    rep["fixed"] += len(fixes)

    # 2) rezervările exacte prin Google: ajung încă la compania aeriană?
    for r in db.q("SELECT rowid, source, origin, dest, dep_date, ret_date, link FROM fares WHERE link LIKE 'gfpost:%'"):
        try:
            ok = gfpost_ok(r["link"], r)
        except Exception as e:
            log.info("gfpost %s-%s: %s", r["origin"], r["dest"], e)
            ok = True  # eroare de rețea: nu schimbăm nimic acum
        if not ok:
            g = json.loads(r["link"][7:])
            db.x("UPDATE fares SET link=? WHERE rowid=?", (g.get("gf") or correct_link(r), r["rowid"]))
            rep["fixed"] += 1
            note("rezervare", r, "rezervarea exactă Google a expirat; acum se deschide Google Flights pe exact acest zbor")
        time.sleep(1)

    # 3) ofertele afișate (Wizz Air / Ryanair): zborul mai există la companie în acea zi?
    shown = db.q("""SELECT DISTINCT source, origin, dest, dep_date, ret_date FROM deals
                    WHERE source IN ('wizzair','ryanair') ORDER BY score DESC LIMIT ?""", (live_limit,))
    gone = []
    cache = {}
    for r in shown:
        legs = [(r["origin"], r["dest"], r["dep_date"])] + ([(r["dest"], r["origin"], r["ret_date"])] if r["ret_date"] else [])
        alive = True
        for leg in legs:
            k = (r["source"],) + leg
            if k not in cache:
                try:
                    cache[k] = FETCH[r["source"]](db, *leg) is not None
                except Exception as e:
                    log.info("verificare %s %s: %s", r["source"], leg, e)
                    cache[k] = True  # eroare: nu scoatem zborul
                time.sleep(1.5)
            alive = alive and cache[k]
        rep["live_checked"] += 1
        if not alive:
            gone.append(r)
            note("zbor", r, "zborul nu mai există la companie în această zi; l-am scos din listă")
    for r in gone:
        db.x("DELETE FROM fares WHERE source=? AND origin=? AND dest=? AND dep_date=? AND ret_date=?",
             (r["source"], r["origin"], r["dest"], r["dep_date"], r["ret_date"] or ""))
    rep["removed"] = len(gone)
    rep["seconds"] = round(time.time() - t0)
    db.set_kv("linkcheck", rep)
    log.info("Verificare linkuri: %s linkuri, %s corecte, %s reparate, %s zboruri scoase (%s verificate live)",
             rep["total"], rep["ok"], rep["fixed"], rep["removed"], rep["live_checked"])
    return rep
