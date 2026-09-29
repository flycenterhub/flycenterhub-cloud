"""Scanarea din cloud (GitHub Actions), la fiecare 3 ore.

Dacă laptopul a publicat site-ul în ultimele ore, laptopul e pornit și se ocupă el: cloud-ul nu face nimic
(așa nu primești alertele de două ori). Altfel: site-uri de oferte + scanare completă + alerte Telegram +
actualizarea site-ului. Setările (config.json) vin criptat din „Secrets” pe GitHub, nu stau în cod.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["FCH_CLOUD"] = "1"

SITE = "https://flycenterhub.github.io/data/status.json"
LAPTOP_HOURS = 4  # laptopul publică cel puțin o dată la 3 ore cât e pornit


def laptop_last():
    try:
        req = urllib.request.Request(f"{SITE}?t={int(time.time())}", headers={"User-Agent": "FlyCenterHub"})
        with urllib.request.urlopen(req, timeout=30) as r:
            s = json.load(r)
    except Exception as e:
        print("Nu am putut citi site-ul:", e)
        return ""
    if s.get("publisher") == "cloud":
        return s.get("laptop_last") or ""
    return s.get("laptop_last") or s.get("generated_at") or ""


def main():
    last = laptop_last()
    os.environ["FCH_LAPTOP_LAST"] = last
    force = os.environ.get("FCH_FORCE") == "true"
    if last and not force:
        age = dt.datetime.now() - dt.datetime.strptime(last[:16], "%Y-%m-%d %H:%M")
        if age < dt.timedelta(hours=LAPTOP_HOURS):
            print(f"Laptopul e pornit (a publicat la {last}), nu fac nimic.")
            return
        print(f"Laptopul nu a mai publicat din {last}: scanez din cloud.")

    from main import setup_logging
    setup_logging()
    from app import fx
    from app.engine import Engine
    fx.refresh()
    e = Engine()
    if not (e.db.get_kv("public_site") or {}).get("url"):
        e.db.set_kv("public_site", {"url": "https://flycenterhub.github.io/"})
    new = e.poll_feeds()
    print(f"Site-uri de oferte: {len(new)} articole noi")
    e.full_scan()
    s = e.db.last_scan("full")
    print("Scanare:", s["status"] if s else None)
    time.sleep(3)
    with e.publish_lock:  # așteaptă publicarea pornită de scanare, apoi publică sigur ultima variantă
        pass
    print("Publicare:", e.publish_site(True))


if __name__ == "__main__":
    main()
