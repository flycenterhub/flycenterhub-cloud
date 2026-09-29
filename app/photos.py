"""Poze cu orașele de destinație, de pe Wikimedia Commons (libere, gratuite, fără cont).

Aeroport (cod IATA) → orașul deservit (Wikidata P931) → poza orașului (P18) sau bannerul Wikivoyage (P948).
Se actualizează după scanări doar pentru destinațiile noi; rezultatul stă în kv „photos”: {cod: [fișier, sursă]}.
"""
import json
import logging
import re
import urllib.parse

from . import net

log = logging.getLogger("photos")

SPARQL = "https://query.wikidata.org/sparql"
UA = {"User-Agent": "FlyCenterHub/1.0 (https://flycenterhub.github.io/)", "Accept": "application/sparql-results+json"}
BAD = re.compile(r"map|karte|carte|satellite|landsat|nasa|locator|location|flag|coat.of.arms|wappen|logo|\.svg$|\.png$|\.gif$|\.tif", re.I)


def _query(codes):
    vals = " ".join(f'"{c}"' for c in codes)
    q = f"""SELECT ?iata ?img ?banner ?aimg WHERE {{
      VALUES ?iata {{ {vals} }}
      ?a wdt:P238 ?iata .
      OPTIONAL {{ ?a wdt:P931 ?city . OPTIONAL {{ ?city wdt:P18 ?img }} OPTIONAL {{ ?city wdt:P948 ?banner }} }}
    }}"""
    data = net.get_json(f"{SPARQL}?format=json&query={urllib.parse.quote(q)}", headers=UA, timeout=90)
    out = {}
    for b in data["results"]["bindings"]:
        code = b["iata"]["value"]
        for key in ("img", "banner"):
            if key in b:
                f = urllib.parse.unquote(b[key]["value"].rsplit("/", 1)[-1]).replace(" ", "_")
                if not BAD.search(f):
                    rank = ("img", "banner").index(key)
                    if code not in out or rank < out[code][1]:
                        out[code] = (f, rank)
    return {c: f for c, (f, _) in out.items()}


def _by_name(names):
    """Rezervă: numele orașului → articolul Wikipedia → Wikidata → poza (pentru coduri de oraș: NYC, ROM...)."""
    clean = {c: re.sub(r"\s*\(.*?\)|(airport|all airports|international)", "", n, flags=re.I).strip()
             for c, n in names.items() if n}
    out = {}
    items = list(clean.items())
    for i in range(0, len(items), 40):
        part = dict(items[i:i + 40])
        q = urllib.parse.quote("|".join(sorted(set(part.values()))))
        d = net.get_json(f"https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1&prop=pageprops"
                         f"&ppprop=wikibase_item&titles={q}", headers=UA)["query"]
        alias = {x["from"]: x["to"] for x in d.get("normalized", []) + d.get("redirects", [])}
        qid = {p["title"]: p.get("pageprops", {}).get("wikibase_item") for p in d.get("pages", {}).values()}
        ids = sorted({v for v in qid.values() if v})
        if not ids:
            continue
        ents = net.get_json("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=claims&ids="
                            + "|".join(ids), headers=UA)["entities"]
        for code, name in part.items():
            t = alias.get(alias.get(name, name), alias.get(name, name))
            claims = (ents.get(qid.get(t) or "", {}) or {}).get("claims", {})
            for prop in ("P18", "P948"):
                try:
                    f = claims[prop][0]["mainsnak"]["datavalue"]["value"].replace(" ", "_")
                except (KeyError, IndexError):
                    continue
                if not BAD.search(f):
                    out[code] = f
                    break
    return out


def url(file, width=640):
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(file)}?width={width}"


def refresh(db, force=False):
    """Caută poze pentru destinațiile care nu au încă. Întoarce câte s-au găsit acum."""
    have = {} if force else (db.get_kv("photos") or {})
    tried = set() if force else set(db.get_kv("photos_tried") or [])
    codes = sorted({r["dest"] for r in db.q("SELECT DISTINCT dest FROM fares")} - set(have) - tried)
    found = 0
    for i in range(0, len(codes), 150):
        part = codes[i:i + 150]
        try:
            res = _query(part)
        except Exception as e:
            log.warning("Poze Wikidata: %s", e)
            break
        have.update(res)
        found += len(res)
        tried.update(set(part) - set(res))
    missing = [c for c in codes if c not in have]
    if missing:
        names = {p["code"]: p["name"] for p in db.q("SELECT code, name FROM places")}
        try:
            res = _by_name({c: names.get(c) for c in missing})
            have.update(res)
            found += len(res)
            tried.difference_update(res)
        except Exception as e:
            log.warning("Poze după nume: %s", e)
    db.set_kv("photos", have)
    db.set_kv("photos_tried", sorted(tried))
    if codes:
        log.info("Poze destinații: %s noi (%s în total)", found, len(have))
    return found


def public(db):
    """{cod: fișier} pentru site."""
    return db.get_kv("photos") or {}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    from .db import DB
    d = DB()
    print(refresh(d, force="--force" in sys.argv), "găsite;", len(public(d)), "în total")
    print(json.dumps(dict(list(public(d).items())[:5]), ensure_ascii=False))
