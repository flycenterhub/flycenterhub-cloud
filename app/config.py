"""Configurare: citește/scrie config.json (se creează automat cu valori implicite)."""
import copy
import json
import os
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
WEB_DIR = os.path.join(ROOT, "web")
CONFIG_PATH = os.path.join(ROOT, "config.json")

DEFAULTS = {
    # Aeroporturile de plecare urmărite
    "origins": ["TSR", "BUD", "OMR", "CLJ", "OTP"],
    # Câte luni înainte se caută
    "months_ahead": 6,
    # La câte ore se face scanarea completă a prețurilor (Ryanair, Wizz Air, Aviasales)
    "scan_interval_hours": 3,
    # Între scanările complete: verificare rapidă (Aviasales + minimele Ryanair) la fiecare X minute
    "quick_scan_interval_minutes": 60,
    # La câte minute se verifică site-urile de oferte (RSS)
    "feeds_interval_minutes": 15,
    # Pauză între cereri către aceeași companie (secunde) - nu micșora prea mult, riști blocarea
    "request_delay_seconds": 0.8,
    # Dus-întors: câte nopți la destinație
    "round_trip": {"min_nights": 2, "max_nights": 10},
    # Pe câte zile în urmă se calculează "prețul obișnuit" al unei rute
    "baseline_days": 60,
    "deal_rules": {
        # Ofertă dacă prețul e cu cel puțin X% sub prețul obișnuit al rutei
        "min_discount_pct": 40,
        # Ofertă dacă prețul unui zbor a scăzut cu cel puțin X% de la ultima verificare
        "drop_pct": 20,
        # Orice bilet sub acest preț e considerat ofertă
        "super_cheap_ow_eur": 20,
        "super_cheap_rt_eur": 50,
        # Nu se consideră ofertă nimic peste aceste prețuri
        "max_price_ow_eur": 150,
        "max_price_rt_eur": 300,
    },
    "last_minute": {"days": 10, "max_ow_eur": 40, "max_rt_eur": 90},
    # Tab-ul „Exotice”: destinații din afara Europei (Asia, Africa, America, insule...), cu escală
    "exotic": {
        "origins": ["BUD", "OTP"],
        "origin": "BUD",
        "months_ahead": 8,
        "min_nights": 5,
        "max_nights": 28,
        "max_price_ow_eur": 700,
        "max_price_rt_eur": 1400,
        "super_cheap_ow_eur": 180,
        "super_cheap_rt_eur": 400,
    },
    "telegram": {
        "enabled": False,
        "bot_token": "",
        "chat_id": "",
        "max_items_per_message": 12,
        # Aceeași rută se retrimite doar dacă prețul scade cu încă X% sau după Y zile
        "renotify_improvement_pct": 10,
        "renotify_after_days": 14,
        "send_feed_posts": True,
        # Rezumatul zilnic (top oferte + confirmarea că platforma funcționează); null = dezactivat
        "daily_summary_hour": 9,
    },
    "sources": {
        "ryanair": True,
        "wizzair": True,
        # Aviasales/Travelpayouts: acoperă și TAROM, HiSky, Lufthansa, Turkish etc.
        # Necesită un token gratuit de pe travelpayouts.com (vezi CITESTE-MA.md)
        "aviasales": {"enabled": True, "token": ""},
        "feeds": True,
    },
    "feeds": [
        {"name": "Fly4free", "url": "https://www.fly4free.com/feed/"},
        {"name": "TravelFree", "url": "https://www.travelfree.info/feed/"},
        {"name": "Utazómajom", "url": "https://utazomajom.hu/feed/", "default_origin": "BUD", "require_price": True},
        {"name": "Fly4free.pl", "url": "https://www.fly4free.pl/feed/"},
        {"name": "WakacyjniPiraci", "url": "https://www.wakacyjnipiraci.pl/feed"},
        {"name": "Urlaubspiraten", "url": "https://www.urlaubspiraten.de/feed"},
        {"name": "Travel-Dealz", "url": "https://www.travel-dealz.com/feed/"},
        {"name": "Travelator", "url": "https://travelator.ro/feed/"},
        {"name": "HolidayPirates", "url": "https://www.holidaypirates.com/feed"},
        {"name": "VoyagesPirates", "url": "https://www.voyagespirates.fr/feed"},
        {"name": "PiratinViaggio", "url": "https://www.piratinviaggio.it/feed"},
        {"name": "ViajerosPiratas", "url": "https://www.viajerospiratas.es/feed"},
        {"name": "Vakantiepiraten", "url": "https://www.vakantiepiraten.nl/feed"},
        {"name": "TravelPirates", "url": "https://www.travelpirates.com/feed"},
        {"name": "Letenky za babku", "url": "https://www.letenkyzababku.sk/feed/"},
        {"name": "Tanie-loty.com.pl", "url": "https://www.tanie-loty.com.pl/feed"},
        {"name": "Travel-Dealz.de", "url": "https://www.travel-dealz.de/feed/"},
        {"name": "Reisetopia", "url": "https://www.reisetopia.de/feed/"},
        {"name": "mydealz Reisen", "url": "https://www.mydealz.de/rss/gruppe/reisen"},
        {"name": "Pepper.pl Podróże", "url": "https://www.pepper.pl/rss/grupa/podroze"},
    ],
    # Prețuri reale Google Flights prin SerpApi (cont gratuit: 100 căutări/lună). Cheia rămâne doar pe calculator.
    "serpapi": {"api_key": "", "monthly_limit": 250, "auto_per_day": 0, "explore": True, "explore_hours": [10, 18]},
    # Site public (doar vizualizare) pe GitHub Pages, actualizat automat după fiecare verificare
    "public_site": {
        "enabled": True,
        "github_token": "",
        "repo": "flycenterhub",
        "min_minutes_between_publishes": 50,
    },
    # Adresa dashboard-ului: http://flycenterhub.localhost (orice nume *.localhost duce la acest calculator)
    "hostname": "flycenterhub.localhost",
    "port": 80,
    # Porturi vechi care redirecționează spre adresa nouă
    "legacy_ports": [8765],
}


def dashboard_url(cfg):
    host = cfg.get("hostname") or "localhost"
    port = int(cfg.get("port") or 80)
    return f"http://{host}" + ("" if port == 80 else f":{port}")

_lock = threading.Lock()


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    with _lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        user = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
        cfg = _merge(DEFAULTS, user)
        if not os.path.exists(CONFIG_PATH):
            _write(cfg)
        return cfg


def save(cfg):
    with _lock:
        _write(cfg)


def _write(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_PATH)
