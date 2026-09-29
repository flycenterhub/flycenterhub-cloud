"""Cereri HTTP cu reîncercări și pauze (doar biblioteca standard)."""
import gzip
import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

log = logging.getLogger("net")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

RETRY_STATUS = {429, 500, 502, 503, 504}


class HttpError(Exception):
    def __init__(self, status, body="", url=""):
        super().__init__(f"HTTP {status} {url} {body[:200]}")
        self.status = status
        self.body = body


def _decode(raw, encoding):
    if encoding == "gzip":
        return gzip.decompress(raw)
    if encoding == "deflate":
        return zlib.decompress(raw)
    return raw


def request(url, method="GET", headers=None, data=None, json_body=None,
            timeout=30, retries=3, backoff=15, on_retry=None):
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8"}
    h.update(headers or {})
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        h["Content-Type"] = "application/json"
    elif data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        h["Content-Type"] = "application/x-www-form-urlencoded"
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return _decode(r.read(), r.headers.get("Content-Encoding"))
        except urllib.error.HTTPError as e:
            txt = ""
            try:
                txt = _decode(e.read(), e.headers.get("Content-Encoding")).decode("utf-8", "replace")
            except Exception:
                pass
            last = HttpError(e.code, txt, url)
            if e.code in RETRY_STATUS and attempt < retries:
                wait = backoff * (attempt + 1)
                log.warning("HTTP %s la %s - reîncerc în %ss", e.code, url[:90], wait)
                if on_retry:
                    on_retry(e.code)
                time.sleep(wait)
                continue
            raise last
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            last = e
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    raise last


def get_json(url, **kw):
    return json.loads(request(url, **kw).decode("utf-8"))


def post_json(url, payload, **kw):
    return json.loads(request(url, method="POST", json_body=payload, **kw).decode("utf-8"))


def get_text(url, **kw):
    return request(url, **kw).decode("utf-8", "replace")
