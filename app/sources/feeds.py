"""Site-uri de oferte (RSS): păstrează doar articolele care pomenesc orașele urmărite."""
import html
import logging
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from .. import net
from ..db import now_str

log = logging.getLogger("feeds")

# Numele orașelor în RO / EN / HU / PL / DE (prefixele prind și formele declinate: Budapestről, Budapesztu)
CITY_NAMES = {
    "TSR": r"timi[sșş]oar|temesv[aá]r|temeschburg|temes[cz]?war",
    "BUD": r"budape[sš]",
    "OMR": r"oradea|nagyv[aá]rad|grosswardein|großwardein",
    "CLJ": r"cluj|kolo[zž]sv[aá]r|klausenburg",
    "OTP": r"bucure[sșş]t|bucharest|bucarest|bukarest|bukareszt|bukure[sš]|boekarest",
}
CITY_CODES = {c: re.compile(rf"\b{c}\b") for c in CITY_NAMES}
# Orașul trebuie să apară ca loc de PLECARE (nu destinație): "from Budapest", "din Cluj",
# "z Budapesztu", "ab Budapest", "Budapestről", "budapesti indulással"
_FROM = (r"(?:\bfrom\b|\bdeparting\b|\bdin\b|\bde la\b|\bplecare\b|\bplec[aă]ri\b|\bab\b|\bvon\b|\bz\b|\bze\b"
         r"|\bzo\b|\bodlet\b|\bda\b|\bpartenza\b|\bdepuis\b|\bd[ée]part\b|\bdesde\b|\bsalida\b|\bvanuit\b|\bvertrek\b)")
CITY_RX = {c: re.compile(rf"{_FROM}[^.!?|]{{0,80}}?(?:{p})|(?:{p})\w*(?:r[oő]l|i indul)"
                         rf"|(?:{p})[\w-]*\s*(?:-|–|—|→|->|>)\s*\w", re.I)
           for c, p in CITY_NAMES.items()}
PRICE_RX = re.compile(r"\d[\d.,  ]*\s?(ft|forint|€|eur|lei|ron|pln|zł)\b|€\s?\d", re.I)
TAG_RX = re.compile(r"<[^>]+>")


def _text(el, *names):
    for n in names:
        x = el.find(n)
        if x is not None:
            if x.text:
                return x.text.strip()
            href = x.get("href")
            if href:
                return href.strip()
    return ""


def _clean(s):
    return re.sub(r"\s+", " ", html.unescape(TAG_RX.sub(" ", s or ""))).strip()


def parse(xml_text):
    """Item-uri RSS 2.0 sau Atom -> listă de dict(title, link, summary, published)."""
    xml_text = xml_text.lstrip("﻿ \r\n\t")
    root = ET.fromstring(xml_text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for it in root.iter("item"):
        items.append({
            "title": _clean(_text(it, "title")),
            "link": _text(it, "link", "guid"),
            "summary": _clean(_text(it, "description", "{http://purl.org/rss/1.0/modules/content/}encoded"))[:600],
            "published": _text(it, "pubDate", "{http://purl.org/dc/elements/1.1/}date"),
        })
    for it in root.findall(".//a:entry", ns):
        link = it.find("a:link", ns)
        items.append({
            "title": _clean(_text(it, "{http://www.w3.org/2005/Atom}title")),
            "link": link.get("href") if link is not None else "",
            "summary": _clean(_text(it, "{http://www.w3.org/2005/Atom}summary",
                                    "{http://www.w3.org/2005/Atom}content"))[:600],
            "published": _text(it, "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"),
        })
    return items


def _iso(published):
    if not published:
        return ""
    try:
        return parsedate_to_datetime(published).astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return published[:16].replace("T", " ")


def match_cities(text, origins):
    found = []
    for c in origins:
        if c in CITY_RX and (CITY_RX[c].search(text) or CITY_CODES[c].search(text)):
            found.append(c)
    return found


def poll(cfg, db):
    """Returnează articolele noi relevante (și le salvează)."""
    origins = cfg["origins"]
    new, errors = [], []
    for feed in cfg.get("feeds") or []:
        try:
            items = parse(net.get_text(feed["url"], timeout=30, retries=1))
        except Exception as e:
            errors.append(f"{feed['name']}: {e}")
            log.warning("Feed %s: %s", feed["name"], e)
            continue
        for it in items:
            if not it["link"] or not it["title"]:
                continue
            text = f"{it['title']} {it['summary']}"
            cities = match_cities(text, origins)
            if not cities and feed.get("default_origin") in origins:
                cities = [feed["default_origin"]]
            if not cities:
                continue
            if feed.get("require_price") and not PRICE_RX.search(text):
                continue
            exists = db.q1("SELECT 1 AS x FROM posts WHERE url=?", (it["link"],))
            if exists:
                continue
            row = {
                "url": it["link"], "feed": feed["name"], "title": it["title"][:300],
                "summary": it["summary"][:600], "published": _iso(it["published"]),
                "cities": ",".join(cities), "first_seen": now_str(),
            }
            db.x("INSERT OR IGNORE INTO posts(url, feed, title, summary, published, cities, first_seen) "
                 "VALUES(:url, :feed, :title, :summary, :published, :cities, :first_seen)", row)
            new.append(row)
    return new, errors
