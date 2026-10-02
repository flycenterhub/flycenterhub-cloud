"""Notificări Telegram (Bot API)."""
import html
import json
import logging
import time

from . import net
from .fmt import date_ro, eur, nights, place_name, ron
from .regions import region_of
from .sources.common import google_flights_link


def web_link(link):
    """Linkul de deschis dintr-un mesaj (rezervarea Google Flights e un formular, deci trimitem căutarea exactă)."""
    if (link or "").startswith("gfpost:"):
        try:
            return json.loads(link[7:]).get("gf") or ""
        except ValueError:
            return ""
    return link or ""

log = logging.getLogger("telegram")

FLAG_ICONS = {"SUB_MEDIE": "📉", "MINIM": "🏆", "SCADERE": "⬇️", "SUPER": "🔥", "LAST_MINUTE": "⏰"}


def _call(token, method, **params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    raw = net.request(url, method="POST", data=params, timeout=30, retries=2, backoff=5)
    res = json.loads(raw.decode("utf-8"))
    if not res.get("ok"):
        raise RuntimeError(res.get("description") or "Eroare Telegram")
    return res["result"]


def enabled(cfg):
    tg = cfg.get("telegram") or {}
    return bool(tg.get("enabled") and tg.get("bot_token") and tg.get("chat_id"))


def send(cfg, text):
    tg = cfg["telegram"]
    for chunk in _chunks(text, 3800):
        _call(tg["bot_token"], "sendMessage", chat_id=tg["chat_id"], text=chunk,
              parse_mode="HTML", disable_web_page_preview="true")
        time.sleep(0.5)


def _chunks(text, size):
    parts, cur = [], ""
    for block in text.split("\n\n"):
        if len(cur) + len(block) + 2 > size and cur:
            parts.append(cur)
            cur = ""
        cur = f"{cur}\n\n{block}" if cur else block
    if cur:
        parts.append(cur)
    return parts


def format_deal(d, places):
    e = html.escape
    o, dst = place_name(d["origin"], places), place_name(d["dest"], places)
    country = (places.get(d["dest"]) or {}).get("country") or ""
    icons = "".join(FLAG_ICONS[f] for f in d["flags"].split(",") if f in FLAG_ICONS)
    p = places.get(d["dest"]) or {}
    if region_of(d["dest"], p.get("cc"), p.get("country_en")):
        icons = "🌴" + icons
    if d["trip"] == "RT":
        when = f"{date_ro(d['dep_date'])} → {date_ro(d['ret_date'])} ({nights(d['dep_date'], d['ret_date'])} nopți)"
        kind = "dus-întors"
    else:
        when = f"{date_ro(d['dep_date'])}" + (f" {d['dep_time']}" if d.get("dep_time") else "")
        kind = "dus"
    lines = [f"{icons} <b>{e(o)} → {e(dst)}</b>" + (f" ({e(country)})" if country else "") + f" · {kind}",
             f"💶 <b>{eur(d['price_eur'])}</b> · <b>{ron(d['price_eur'], d.get('price_orig'), d.get('currency'))}</b>"
             f" · {when} · {e(d.get('airline') or '')}"]
    why = []
    if d.get("typical_eur") and d["discount_pct"] > 0:
        why.append(f"-{round(d['discount_pct'])}% față de prețul obișnuit ({eur(d['typical_eur'])})")
    if "MINIM" in d["flags"]:
        why.append(f"cel mai mic din ultimele {d['history_days']} zile")
    if d.get("prev_price_eur"):
        why.append(f"scăzut de la {eur(d['prev_price_eur'])}")
    if "LAST_MINUTE" in d["flags"]:
        n = d["days_to_dep"]
        why.append("pleacă azi" if n < 1 else "pleacă mâine" if n == 1 else f"pleacă în {n} zile")
    if d.get("other_dates"):
        why.append(f"+{d['other_dates']} alte date bune")
    if why:
        lines.append("ℹ️ " + " · ".join(why))
    gf = google_flights_link(d["origin"], d["dest"], d["dep_date"], d["ret_date"])
    sky = (f"https://www.skyscanner.ro/transport/zboruri/{d['origin'].lower()}/{d['dest'].lower()}/"
           f"{d['dep_date'][2:].replace('-', '')}/" + (f"{d['ret_date'][2:].replace('-', '')}/" if d.get("ret_date") else "")
           + "?adults=1&currency=EUR")
    if d.get("source") == "aviasales":
        lines.append("ℹ️ preț găsit recent · Rezervă duce pe site-ul companiei care operează zborul")
    if d.get("source") == "wizzair" or (d.get("airline") or "").startswith("Wizz Air"):
        n = 2 if d.get("ret_date") else 1
        lines.append(f"ℹ️ + taxa de administrare Wizz Air la plată: {8 * n}–{13 * n} € de persoană")
    link = web_link(d.get("link")) or gf
    who = "Wizz Air" if "wizzair.com" in link else "Ryanair" if "ryanair.com" in link else \
        (d.get("airline") or "").split(" · ")[0].strip()
    lines.append(f"🔗 <a href=\"{e(link)}\">Rezervă{' la ' + e(who) if who and 'google.com' not in link else ''}</a>"
                 f" · Compară: <a href=\"{e(gf)}\">Google Flights</a>"
                 f" · <a href=\"{e(sky)}\">Skyscanner</a>")
    return "\n".join(lines)


def format_deals(sections, places, first_time, dashboard_url):
    """sections: listă de (titlu, oferte) - ex. Oferte, Last minute, Exotice."""
    total = sum(len(items) for _, items in sections)
    if first_time:
        head = f"✈️ <b>Monitorizarea a pornit!</b> Cele mai bune {total} oferte găsite acum:"
    else:
        head = f"✈️ <b>{total} oferte noi de zbor</b>"
    parts = [head]
    for title, items in sections:
        if items:
            parts.append(f"<b>━━ {title} ━━</b>")
            parts += [format_deal(d, places) for d in items]
    parts.append(f"📊 Toate ofertele: {dashboard_url}")
    return "\n\n".join(parts)


def _short(d, places):
    """O linie scurtă pentru rezumatul zilnic."""
    e = html.escape
    when = f"{date_ro(d['dep_date'])}" + (f"→{date_ro(d['ret_date'], False)}" if d.get("ret_date") else "")
    disc = f" (-{round(d['discount_pct'])}%)" if d.get("discount_pct") and d["discount_pct"] > 0 else ""
    kind = "dus-întors" if d.get("ret_date") else "dus"
    link = web_link(d.get("link")) or google_flights_link(d["origin"], d["dest"], d["dep_date"], d.get("ret_date") or "")
    return (f"• <b>{eur(d['price_eur'])}</b>{disc} {e(place_name(d['origin'], places))} → "
            f"<a href=\"{e(link)}\">{e(place_name(d['dest'], places))}</a> · {kind} · {when}")


def format_daily(summary, places, dashboard_url):
    s = summary
    lines = [f"☀️ <b>Rezumatul zilei</b>: platforma funcționează ✅",
             f"Ultima scanare: {s['last_scan']} · {s['fares']:,} prețuri pe {s['routes']} rute · {s['deals']} oferte active".replace(",", ".")]
    for title, key in (("🔥 Top oferte", "top"), ("⏰ Last minute", "lm"), ("🌴 Exotice", "exotic")):
        if s.get(key):
            lines.append(f"\n<b>{title}</b>")
            lines += [_short(d, places) for d in s[key]]
    lk = s.get("links")
    if lk:
        extra = []
        if lk.get("fixed"):
            extra.append(f"{lk['fixed']} reparate")
        if lk.get("removed"):
            extra.append(f"{lk['removed']} zboruri epuizate scoase")
        lines.append(f"\n🔗 Linkuri „Rezervă” verificate azi la {lk['at'][11:16]}: {lk['total']:,} ".replace(",", ".")
                     + (f"({', '.join(extra)})" if extra else "— toate duc exact la zborul lor ✅"))
    if s.get("warnings"):
        lines.append("\n⚠️ " + " · ".join(html.escape(w) for w in s["warnings"]))
    lines.append(f"\n📊 Toate ofertele: {dashboard_url}")
    return "\n".join(lines)


def format_posts(posts, places):
    e = html.escape
    blocks = []
    for p in posts:
        cities = ", ".join(place_name(c, places) for c in p["cities"].split(",") if c)
        blocks.append(f"📰 <b>{e(p['feed'])}</b> · {e(cities)}\n{e(p['title'])}\n🔗 <a href=\"{e(p['url'])}\">Deschide oferta</a>")
    return "\n\n".join(blocks)


def discover_chat_id(token, wait_seconds=180):
    """Așteaptă un mesaj trimis botului și întoarce chat_id-ul expeditorului."""
    me = _call(token, "getMe")
    deadline = time.time() + wait_seconds
    offset = 0
    while time.time() < deadline:
        updates = _call(token, "getUpdates", timeout=20, offset=offset)
        for u in updates:
            offset = u["update_id"] + 1
            msg = u.get("message") or u.get("channel_post") or {}
            chat = msg.get("chat")
            if chat:
                return chat["id"], me
        time.sleep(1)
    return None, me
