"""Server web local pentru dashboard (doar pe acest calculator: 127.0.0.1)."""
import json
import logging
import mimetypes
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, queries, telegram

log = logging.getLogger("server")


def make_handler(engine):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ZboruriIeftine/1.0"

        def log_message(self, fmt, *args):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _static(self, path):
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            full = os.path.normpath(os.path.join(config.WEB_DIR, rel))
            if not full.startswith(os.path.normpath(config.WEB_DIR)) or not os.path.isfile(full):
                self.send_error(404)
                return
            with open(full, "rb") as f:
                body = f.read()
            self.send_response(200)
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            qs = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            db, cfg = engine.db, engine.cfg
            exact = qs.get("exact") == "1"
            try:
                if u.path == "/api/status":
                    return self._json(queries.status(engine))
                if u.path == "/api/photos":
                    from . import photos
                    return self._json(photos.public(db))
                if u.path == "/api/deals":
                    return self._json(queries.deals(db, cfg["origins"], exact))
                if u.path == "/api/route-deals":
                    return self._json(queries.route_deals(db, qs["origin"], qs["dest"], qs.get("trip", "OW")))
                if u.path == "/api/lastminute":
                    return self._json(queries.last_minute(db, cfg, int(qs.get("days", cfg["last_minute"]["days"])), exact))
                if u.path == "/api/destinations":
                    return self._json(queries.destinations(db, cfg, exact))
                if u.path == "/api/route":
                    return self._json(queries.route(db, qs["origin"], qs["dest"], exact))
                if u.path in ("/api/search", "/api/exotic"):
                    dep_from = qs.get("dep_from", "")
                    ret_from = qs.get("ret_from", "")
                    args = (dep_from, qs.get("dep_to") or dep_from, ret_from, qs.get("ret_to") or ret_from)
                    if u.path == "/api/exotic":
                        return self._json(queries.exotic(db, cfg, engine.source_enabled(cfg, "aviasales"), *args, exact=exact))
                    return self._json(queries.search(db, cfg, *args, qs.get("origin", ""), qs.get("trip", "ALL"), exact))
                if u.path == "/api/favorites":
                    return self._json(queries.favorites(db, [k for k in qs.get("k", "").split(",") if k], exact))
                if u.path == "/api/posts":
                    return self._json(queries.posts(db))
                if u.path.startswith("/api/"):
                    return self._json({"error": "necunoscut"}, 404)
                return self._static(u.path)
            except Exception as e:
                log.exception("GET %s", self.path)
                return self._json({"error": str(e)}, 500)

        def do_POST(self):
            # Antet obligatoriu: împiedică alte site-uri să declanșeze acțiuni pe serverul local
            if self.headers.get("X-Zboruri") != "1":
                return self._json({"error": "interzis"}, 403)
            u = urllib.parse.urlparse(self.path)
            try:
                if u.path == "/api/scan":
                    if engine.running:
                        return self._json({"ok": False, "message": "O scanare e deja în curs"})
                    q = urllib.parse.parse_qs(u.query)
                    only = q.get("only", [""])[0]
                    if q.get("quick"):
                        threading.Thread(target=engine.quick_scan, args=(True,), daemon=True).start()
                    else:
                        threading.Thread(target=engine.full_scan, args=(only.split(",") if only else None,),
                                         kwargs={"manual": True}, daemon=True).start()
                    return self._json({"ok": True})
                if u.path == "/api/verify":
                    from . import verify
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                    res = verify.verify(engine.db, body.get("legs") or [], body.get("pax") or 1)
                    if res.get("ok") and not engine.running:
                        # ofertele se recalculează în fundal cu prețul proaspăt
                        threading.Thread(target=engine.reanalyze, daemon=True).start()
                    return self._json(res)
                if u.path == "/api/gfcheck":
                    from .sources import serpapi
                    cfg = config.load()
                    if not serpapi.enabled(cfg):
                        return self._json({"ok": False, "error": "no_key"})
                    n = int(self.headers.get("Content-Length") or 0)
                    b = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                    res = serpapi.check(cfg, engine.db, b["origin"], b["dest"], b["dep"], b.get("ret") or "",
                                        int(b.get("adults") or 1), int(b.get("children") or 0), int(b.get("infants") or 0))
                    res["used"] = serpapi.used_this_month(engine.db)
                    res["limit"] = int((cfg.get("serpapi") or {}).get("monthly_limit", 100))
                    if res.get("ok") and res.get("found"):
                        def refresh():
                            if not engine.running:
                                engine.reanalyze()
                            engine.publish_site(True)
                        threading.Thread(target=refresh, daemon=True).start()
                    return self._json(res)
                if u.path == "/api/linkcheck":
                    return self._json(engine.check_links() or {"ok": False})
                if u.path == "/api/feeds":
                    new = engine.poll_feeds()
                    return self._json({"ok": True, "new": len(new)})
                if u.path == "/api/telegram-test":
                    cfg = config.load()
                    if not telegram.enabled(cfg):
                        return self._json({"ok": False, "message": "Telegram nu este configurat"})
                    telegram.send(cfg, "✅ Test reușit! Aici vei primi ofertele de zbor.")
                    return self._json({"ok": True})
                return self._json({"error": "necunoscut"}, 404)
            except Exception as e:
                log.exception("POST %s", self.path)
                return self._json({"ok": False, "message": str(e)}, 500)

    return Handler


def serve_redirect(port, target):
    """Server mic pe o adresă veche (ex. localhost:8765) care trimite spre adresa nouă."""
    class Redirect(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            self.send_response(301)
            self.send_header("Location", target.rstrip("/") + self.path)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_HEAD = do_GET

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Redirect)
    httpd.daemon_threads = True
    return httpd


def serve(engine, port):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(engine))
    httpd.daemon_threads = True
    return httpd
