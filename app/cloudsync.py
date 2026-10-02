"""Urcă automat în depozitul cloud (flycenterhub-cloud) codul schimbat pe laptop.

Folosește tokenul GitHub deja salvat pentru publicarea site-ului (config.json, nu se publică).
Urcă doar codul: app/**/*.py (fără cloud_setup.py), web/* (fără web/photos), cloud_run.py, main.py. Nu atinge
.github/ (workflow-ul), datele sau secretele. Șterge fișierele puse greșit (care nu există pe laptop)
din app/, web/ și .js/.html din rădăcină.
"""
import base64
import hashlib
import os

from . import config, publish
from .db import now_str

OWNER, REPO = "flycenterhub", "flycenterhub-cloud"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {"app/cloud_setup.py"}
CRLF, LF = bytes([13, 10]), bytes([10])


def _local_files():
    out = {}
    for base in ("app", "web"):
        for d, dirs, files in os.walk(os.path.join(ROOT, base)):
            dirs[:] = [x for x in dirs if x not in ("__pycache__", "photos")]
            for f in files:
                rel = os.path.relpath(os.path.join(d, f), ROOT).replace("\\", "/")
                if rel in SKIP or (base == "app" and not f.endswith(".py")):
                    continue
                out[rel] = os.path.join(d, f)
    for f in ("cloud_run.py", "main.py"):
        if os.path.exists(os.path.join(ROOT, f)):
            out[f] = os.path.join(ROOT, f)
    return out


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _stray(path, local):
    if path in local or path.startswith((".github/", "data/")):
        return False
    if path.startswith(("app/", "web/")):
        return True
    return "/" not in path and path.endswith((".js", ".html"))


def sync(dry_run=False):
    """Returnează {'ok', 'uploaded': [...], 'deleted': [...], 'message'}."""
    token = ((config.load().get("public_site") or {}).get("github_token") or "").strip()
    if not token:
        return {"ok": False, "message": "Lipsește tokenul GitHub din configurare"}
    gh = lambda m, p, body=None: publish._gh(token, m, f"/repos/{OWNER}/{REPO}{p}", body)
    try:
        head = gh("GET", "/git/ref/heads/main")["object"]["sha"]
        base_tree = gh("GET", f"/git/commits/{head}")["tree"]["sha"]
        remote = {t["path"]: t["sha"] for t in gh("GET", f"/git/trees/{base_tree}?recursive=1")["tree"]
                  if t["type"] == "blob"}
        local = _local_files()
        changes, uploaded = [], []
        for rel, path in sorted(local.items()):
            data = _read(path)
            # fișierele urcate manual pot avea alt capăt de rând (CRLF); nu le urcăm doar pentru asta
            lf = data.replace(CRLF, LF)
            if remote.get(rel) in (_blob_sha(data), _blob_sha(lf), _blob_sha(lf.replace(LF, CRLF))):
                continue
            uploaded.append(rel)
            if not dry_run:
                b = gh("POST", "/git/blobs", {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"})
                changes.append({"path": rel, "mode": "100644", "type": "blob", "sha": b["sha"]})
        deleted = sorted(p for p in remote if _stray(p, local))
        changes += [{"path": p, "mode": "100644", "type": "blob", "sha": None} for p in deleted]
        if dry_run or not (uploaded or deleted):
            return {"ok": True, "uploaded": uploaded, "deleted": deleted,
                    "message": "Cloud-ul e deja la zi" if not (uploaded or deleted) else "Simulare"}
        tree = gh("POST", "/git/trees", {"base_tree": base_tree, "tree": changes})
        c = gh("POST", "/git/commits", {"message": f"Actualizare cod de pe laptop {now_str()}", "tree": tree["sha"],
                                        "parents": [head], "author": publish.BOT, "committer": publish.BOT})
        gh("PATCH", "/git/refs/heads/main", {"sha": c["sha"]})
        return {"ok": True, "uploaded": uploaded, "deleted": deleted,
                "message": f"Urcate {len(uploaded)}, șterse {len(deleted)}"}
    except Exception as e:
        return {"ok": False, "message": f"Nu s-a putut urca în cloud: {e}"}
