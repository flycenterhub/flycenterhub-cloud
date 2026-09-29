"""Cursuri valutare: BNR (oficial, pentru lei și conversii) + BCE ca rezervă.

BNR publică zilnic (în zilele lucrătoare, ~13:00) cursul de referință: câți lei costă o unitate
din fiecare monedă. Verificăm la fiecare oră, iar prețurile în lei se calculează la cerere, deci
sunt mereu la cursul BNR în vigoare.
"""
import json
import logging
import os
import re
import threading
import time

from . import config, net

log = logging.getLogger("fx")

BNR_URL = "https://curs.bnr.ro/nbrfxrates.xml"
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
CACHE = os.path.join(config.DATA_DIR, "fx.json")

_lock = threading.Lock()
_ron_per = {"RON": 1.0}          # BNR: lei pentru 1 unitate din monedă
_bnr_date = None                  # data cursului BNR în vigoare
# BCE: unități per 1 EUR (rezervă pentru monedele fără curs BNR). Valori inițiale aproximative.
_ecb = {"EUR": 1.0, "RON": 5.0, "HUF": 390.0, "PLN": 4.3, "GBP": 0.85, "USD": 1.1}
_checked = {"bnr": 0.0, "ecb": 0.0}
_loaded_cache = False


def _load_cache():
    global _bnr_date, _loaded_cache
    _loaded_cache = True
    if not os.path.exists(CACHE):
        return
    try:
        with open(CACHE, encoding="utf-8") as f:
            data = json.load(f)
        if "bnr" in data:
            _ron_per.update(data["bnr"].get("rates") or {})
            _bnr_date = data["bnr"].get("date")
            _ecb.update(data.get("ecb") or {})
        else:  # format vechi (doar BCE)
            _ecb.update(data)
    except Exception:
        pass


def _save_cache():
    try:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump({"bnr": {"date": _bnr_date, "rates": _ron_per}, "ecb": _ecb}, f)
    except Exception:
        pass


def refresh(force=False):
    """Actualizează cursurile (BNR cel mult o dată pe oră, BCE la 6 ore)."""
    global _bnr_date
    with _lock:
        if not _loaded_cache:
            _load_cache()
        now = time.time()
        changed = False
        if force or now - _checked["bnr"] > 3600:
            _checked["bnr"] = now
            try:
                xml = net.get_text(BNR_URL, timeout=20, retries=2)
                rates = {}
                for attrs, value in re.findall(r"<Rate ([^>]*)>([\d.]+)</Rate>", xml):
                    cur = re.search(r'currency="([A-Z]{3})"', attrs)
                    mult = re.search(r'multiplier="(\d+)"', attrs)
                    if cur:
                        rates[cur.group(1)] = float(value) / (int(mult.group(1)) if mult else 1)
                date = re.search(r'<Cube date="([\d-]+)"', xml)
                if rates.get("EUR"):
                    if date and date.group(1) != _bnr_date:
                        log.info("Curs BNR nou (%s): 1 EUR = %.4f lei", date.group(1), rates["EUR"])
                    _ron_per.update(rates)
                    _bnr_date = date.group(1) if date else _bnr_date
                    changed = True
            except Exception as e:
                log.warning("Nu am putut lua cursul BNR: %s", e)
        if force or now - _checked["ecb"] > 6 * 3600:
            _checked["ecb"] = now
            try:
                xml = net.get_text(ECB_URL, timeout=20, retries=2)
                found = {c: float(r) for c, r in re.findall(r"currency='([A-Z]{3})' rate='([\d.]+)'", xml)}
                if found:
                    _ecb.update(found)
                    changed = True
            except Exception as e:
                log.warning("Nu am putut lua cursul BCE: %s", e)
        if changed:
            _save_cache()


def eur_ron():
    """Lei pentru 1 EUR la cursul BNR (sau BCE dacă BNR nu e disponibil)."""
    return _ron_per.get("EUR") or _ecb.get("RON") or 5.0


def to_ron(amount, currency):
    currency = (currency or "EUR").upper()
    if currency == "RON":
        return float(amount)
    if currency in _ron_per:
        return float(amount) * _ron_per[currency]
    if currency in _ecb:  # rezervă: prin EUR (BCE), apoi în lei (BNR)
        return float(amount) / _ecb[currency] * eur_ron()
    return None


def to_eur(amount, currency):
    currency = (currency or "EUR").upper()
    if currency == "EUR":
        return round(float(amount), 2)
    ron = to_ron(amount, currency)
    return round(ron / eur_ron(), 2) if ron is not None else None


def eur_to(amount, currency):
    currency = currency.upper()
    if currency == "RON":
        return round(float(amount) * eur_ron(), 2)
    per_unit = _ron_per.get(currency)
    return round(float(amount) * eur_ron() / per_unit, 2) if per_unit else round(float(amount) * _ecb.get(currency, 1.0), 2)


def lei_of(price_eur, price_orig=None, currency=None):
    """Prețul în lei: exact al companiei dacă biletul e în lei, altfel la cursul BNR din moneda biletului."""
    currency = (currency or "").upper()
    if currency == "RON" and price_orig:
        return round(float(price_orig), 2)
    if currency and currency != "EUR" and price_orig:
        ron = to_ron(price_orig, currency)
        if ron is not None:
            return round(ron, 2)
    return round(float(price_eur) * eur_ron(), 2)


def info():
    return {"source": "BNR" if _ron_per.get("EUR") else "BCE", "date": _bnr_date, "eur_ron": round(eur_ron(), 4),
            "huf100_ron": round(_ron_per["HUF"] * 100, 4) if "HUF" in _ron_per else None}
