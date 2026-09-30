"""Site public (doar vizualizare) pe GitHub Pages.

Căutarea prețurilor rămâne pe acest calculator. După fiecare verificare, aplicația publică o
copie statică a dashboard-ului (HTML + date JSON) în depozitul GitHub al utilizatorului; GitHub
Pages o servește la https://<utilizator>.github.io/<depozit>/. Se publică DOAR interfața și
prețurile, niciodată config.json sau tokenurile.
"""
import base64
import datetime as dt
import json
import logging
import os

from . import config, extras, fx, net, photos, queries, visitors
from .db import now_str
from .fmt import ORIGIN_NAMES, country_ro
from .regions import region_of

log = logging.getLogger("publish")

API = "https://api.github.com"
SRC = ["ryanair", "wizzair", "aviasales", "google"]
WEB_FILES = ["style.css", "app.js", "static-api.js", "logo.svg"]
# Autorul commit-urilor (ca să nu apară numele personal în depozit)
BOT = {"name": "FlyCenterHub", "email": "noreply@flycenterhub.github.io"}


def _j(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")


# ---------- exportul datelor ----------
def build(engine):
    """Fișierele site-ului static: {cale: bytes}."""
    db, cfg = engine.db, engine.cfg
    origins = cfg["origins"]
    ph = ",".join("?" * len(origins))

    fares = db.q(f"""SELECT source, origin, dest, dep_date, ret_date, price_eur, price_orig, currency,
                            dep_time, ret_time, airline, link, last_seen, first_seen
                     FROM fares WHERE origin IN ({ph}) OR dest IN ({ph})""", (*origins, *origins))
    airlines, air_idx = [], {}
    compact = []
    for f in fares:
        a = f["airline"] or ""
        if a not in air_idx:
            air_idx[a] = len(airlines)
            airlines.append(a)
        compact.append([
            SRC.index(f["source"]) if f["source"] in SRC else 0, f["origin"], f["dest"], f["dep_date"], f["ret_date"],
            f["price_eur"], fx.lei_of(f["price_eur"], f["price_orig"], f["currency"]),
            1 if (f["currency"] or "") == "RON" else 0, f["dep_time"] or "", f["ret_time"] or "", air_idx[a],
            f["link"] if f["source"] in ("aviasales", "google") else 0, (f["last_seen"] or "")[:16], (f["first_seen"] or "")[:16],
        ])

    codes = {c for f in fares for c in (f["origin"], f["dest"])}
    places = {}
    for p in db.q("SELECT * FROM places"):
        if p["code"] in codes:
            name = (p["name"] or "").strip() or p["code"]
            country = (p["country"] or "").strip()
            places[p["code"]] = [ORIGIN_NAMES.get(p["code"], name), country_ro(country),
                                 region_of(p["code"], p.get("cc"), country)]

    stats = {f"{s['origin']}|{s['dest']}|{s['trip']}": [s["typical_eur"], s["min_prev_eur"], s["history_days"]]
             for s in db.q("SELECT * FROM route_stats")}
    hist = {}
    for h in db.q("SELECT * FROM route_daily WHERE trip='OW' ORDER BY day"):
        hist.setdefault(f"{h['origin']}|{h['dest']}", []).append([h["day"], h["min_eur"], h["p50_eur"]])
    deals_all = [[SRC.index(d["source"]) if d["source"] in SRC else 0, d["origin"], d["dest"], d["trip"], d["dep_date"],
                  d["ret_date"], d["flags"], d["score"]] for d in db.q("SELECT * FROM deals")]

    status = queries.status(engine)
    status.update(running=False, progress=[], progress_pct=None, eta_min=None, telegram=False, serpapi={"enabled": False},
                  static=True, generated_at=now_str())
    # cine a publicat: laptopul sau GitHub (cloud-ul scanează doar cât laptopul e oprit, vezi cloud_run.py)
    if os.environ.get("FCH_CLOUD"):
        status.update(publisher="cloud", laptop_last=os.environ.get("FCH_LAPTOP_LAST", ""))
    else:
        status.update(publisher="laptop", laptop_last=now_str())
    exotic = queries.exotic(db, cfg, engine.source_enabled(cfg, "aviasales"))

    files = {
        "data/status.json": _j(status),
        "data/deals.json": _j(queries.deals(db, origins)),
        "data/deals_exact.json": _j(queries.deals(db, origins, exact=True)),
        "data/deals_all.json": _j(deals_all),
        "data/destinations.json": _j(queries.destinations(db, cfg)),
        "data/destinations_exact.json": _j(queries.destinations(db, cfg, exact=True)),
        "data/posts.json": _j(queries.posts(db)),
        "data/fares.json": _j({"airlines": airlines, "rows": compact}),
        "data/places.json": _j(places),
        "data/photos.json": _j(photos.public(db)),
        "data/coords.json": _j(photos.public_coords(db)),
        "data/climate.json": _j(extras.public_climate(db)),
        "data/escale.json": _j(extras.public_connections(db, cfg)),
        "data/stats.json": _j(stats),
        "data/hist.json": _j(hist),
        "data/exotic_posts.json": _j(exotic["posts"]),
        ".nojekyll": b"",
    }
    version = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    with open(os.path.join(config.WEB_DIR, "index.html"), encoding="utf-8") as f:
        html = f.read()
    # GitHub Pages lasă browserele să păstreze pagina ~10 minute; la fiecare deschidere verificăm
    # versiunea publicată (version.json, mereu proaspăt) și, dacă pagina din memorie e mai veche,
    # o reîncărcăm printr-o adresă nouă (apoi adresa se curăță înapoi la „/”).
    html = html.replace("<head>", f"""<head>
<script>
(function () {{
  var mine = "{version}", u = new URL(location.href);
  if (u.searchParams.has("v")) {{ u.searchParams.delete("v"); history.replaceState(null, "", u.pathname + u.search + u.hash); }}
  fetch("version.json?t=" + Date.now(), {{ cache: "no-store" }}).then(function (r) {{ return r.json(); }}).then(function (j) {{
    if (j.version && j.version > mine && new URL(location.href).searchParams.get("v") !== j.version) {{
      var n = new URL(location.href); n.searchParams.set("v", j.version); location.replace(n.toString());
    }}
  }}).catch(function () {{}});
}})();
</script>""", 1)
    files["version.json"] = _j({"version": version})
    html = html.replace('<script src="app.js"></script>',
                        f'<script>window.STATIC_SITE = true; window.DATA_VERSION = "{version}";</script>\n'
                        f'{visitors.COUNT_TAG}\n'
                        f'<script src="static-api.js?v={version}"></script>\n<script src="app.js?v={version}"></script>')
    html = html.replace('href="style.css"', f'href="style.css?v={version}"')
    html = html.replace('src="logo.svg"', f'src="logo.svg?v={version}"').replace('href="logo.svg"', f'href="logo.svg?v={version}"')
    files["index.html"] = html.encode("utf-8")
    for name in WEB_FILES:
        with open(os.path.join(config.WEB_DIR, name), "rb") as f:
            files[name] = f.read()
    files.update(photos.local_files(db))  # pozele încărcate de tine de pe laptop
    return files


# ---------- GitHub ----------
def _gh(token, method, path, payload=None, ok404=False):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    try:
        raw = net.request(API + path, method=method, headers=headers, json_body=payload, timeout=60, retries=2, backoff=10)
        return json.loads(raw.decode("utf-8")) if raw else {}
    except net.HttpError as e:
        if ok404 and e.status == 404:
            return None
        raise


def publish(engine):
    """Publică site-ul. Returnează {'ok', 'url', 'error'} și salvează starea în kv."""
    cfg = config.load()
    ps = cfg.get("public_site") or {}
    token = (ps.get("github_token") or "").strip()
    state = engine.db.get_kv("public_site", {}) or {}
    if not ps.get("enabled", True) or not token:
        return {"ok": False, "error": "no_token"}
    org = (ps.get("organization") or "").strip()
    try:
        if org:
            # Organizație (ex. flycenterhub): site-ul e la https://flycenterhub.github.io, fără numele personal
            owner = org
            repo = (ps.get("repo") or "").strip()
            if not repo or repo == "flycenterhub":
                repo = f"{org.lower()}.github.io"
            create_path = f"/orgs/{org}/repos"
        else:
            owner = _gh(token, "GET", "/user")["login"]
            repo = (ps.get("repo") or "flycenterhub").strip()
            create_path = "/user/repos"
        root = repo.lower() == f"{owner.lower()}.github.io"
        url = f"https://{owner.lower()}.github.io/" + ("" if root else f"{repo}/")
        if _gh(token, "GET", f"/repos/{owner}/{repo}", ok404=True) is None:
            _gh(token, "POST", create_path, {
                "name": repo, "description": "FlyCenterHub S.R. – bilete de avion ieftine din Timișoara, Budapesta, Oradea, Cluj și București",
                "homepage": url, "private": False, "auto_init": True, "has_issues": False, "has_wiki": False,
            })
        files = build(engine)
        tree = []
        for path, content in files.items():
            blob = _gh(token, "POST", f"/repos/{owner}/{repo}/git/blobs",
                       {"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"})
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        t = _gh(token, "POST", f"/repos/{owner}/{repo}/git/trees", {"tree": tree})
        # Un singur commit, fără istoric: depozitul rămâne mic oricât de des se publică
        c = _gh(token, "POST", f"/repos/{owner}/{repo}/git/commits",
                {"message": f"Actualizare prețuri {now_str()}", "tree": t["sha"], "parents": [],
                 "author": BOT, "committer": BOT})
        if _gh(token, "GET", f"/repos/{owner}/{repo}/git/ref/heads/main", ok404=True) is None:
            _gh(token, "POST", f"/repos/{owner}/{repo}/git/refs", {"ref": "refs/heads/main", "sha": c["sha"]})
        else:
            _gh(token, "PATCH", f"/repos/{owner}/{repo}/git/refs/heads/main", {"sha": c["sha"], "force": True})
        pages_error = None
        if _gh(token, "GET", f"/repos/{owner}/{repo}/pages", ok404=True) is None:
            try:
                _gh(token, "POST", f"/repos/{owner}/{repo}/pages",
                    {"build_type": "legacy", "source": {"branch": "main", "path": "/"}})
            except net.HttpError as e:
                pages_error = f"GitHub Pages nu s-a putut activa automat ({e.status})"
        state = {"url": url, "owner": owner, "repo": repo, "last_publish": now_str(), "error": pages_error}
        engine.db.set_kv("public_site", state)
        log.info("Site public actualizat: %s", url)
        return {"ok": True, "url": url, "error": pages_error}
    except Exception as e:
        msg = str(e)
        if isinstance(e, net.HttpError) and e.status == 401:
            msg = "Tokenul GitHub nu e valid"
        elif isinstance(e, net.HttpError) and e.status == 403:
            msg = "Tokenul GitHub nu are dreptul „public_repo”"
        state = dict(state, error=msg, last_error_at=now_str())
        engine.db.set_kv("public_site", state)
        log.error("Publicare site: %s", msg)
        return {"ok": False, "error": msg}
