"""Viza și actele de intrare pentru cetățenii români, pe țara de destinație.

Datele (`visa_ro.json`, cod țară -> [tip, cerință, ședere]) sunt preluate din Wikipedia
„Visa requirements for Romanian citizens” (surse Timatic/IATA), actualizate la VISA_UPDATED.
Sunt orientative: pe site trimitem la MAE pentru confirmare înainte de plecare.
"""
import json
import os
import re

from .fmt import country_ro

VISA_UPDATED = "2026-10"
_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "visa_ro.json")
# Teritoriile SUA urmează regula SUA (intrarea României în Visa Waiver e suspendată)
_SAME_AS_US = {"PR", "VI", "GU", "MP", "AS"}
_AUTH = {"ESTA": "ESTA", "ETA": "ETA", "eTA / Visa not required": "eTA", "eVisitor": "eVisitor", "NZeTA": "NZeTA",
         "ETA-IL": "ETA-IL", "ETA UK": "ETA", "Electronic Travel Authorisation": "ETA"}


def _load():
    with open(_DATA, encoding="utf-8") as f:
        data = json.load(f)
    for cc in _SAME_AS_US:
        if "US" in data:
            data[cc] = data["US"]
    return data


def _stay_ro(stay):
    m = re.match(r"(\d+)\s*(day|month)", stay or "")
    if not m:
        return ""
    n, unit = int(m.group(1)), m.group(2)
    return f"{n} {'zile' if n != 1 else 'zi'}" if unit == "day" else f"{n} {'luni' if n != 1 else 'lună'}"


def info(cc, data=None):
    """[tip, text în română, ședere] pentru un cod de țară; None pentru UE/Schengen sau necunoscut."""
    row = (data or _load()).get((cc or "").upper())
    if not row:
        return None
    _, req, stay = row
    stay = _stay_ro(stay)
    if req == "Freedom of movement":
        return None
    if req == "Visa not required":
        return ["free", "Fără viză", stay]
    if req in _AUTH:
        return ["eta", f"Fără viză, dar cu autorizație online înainte de plecare ({_AUTH[req]})", stay]
    if req == "eVisa":
        return ["evisa", "Viză electronică (e-Visa), se cere online înainte de plecare", stay]
    if req == "Visa on arrival":
        return ["voa", "Viză la sosire, la aeroport", stay]
    if "Visa on arrival" in req:
        return ["voa", "Viză la sosire sau e-Visa online înainte de plecare", stay]
    if req == "Visa required":
        return ["visa", "Viză obligatorie, de la ambasadă, înainte de plecare", stay]
    return None


def public(db):
    """{nume țară în română: [tip, text, ședere]} pentru țările din baza de date (cum apar pe carduri)."""
    data, out = _load(), {}
    for p in db.q("SELECT DISTINCT country, cc FROM places WHERE cc IS NOT NULL AND cc <> ''"):
        v = info(p["cc"], data)
        if v:
            out[country_ro(p["country"])] = v
    return {"updated": VISA_UPDATED, "countries": out}
