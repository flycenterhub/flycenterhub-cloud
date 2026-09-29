"""Formatare în română: date, prețuri, nume de orașe."""
import datetime as dt

from . import fx

ORIGIN_NAMES = {"TSR": "Timișoara", "BUD": "Budapesta", "OMR": "Oradea", "CLJ": "Cluj-Napoca", "OTP": "București"}
MONTHS = ["ian", "feb", "mar", "apr", "mai", "iun", "iul", "aug", "sep", "oct", "nov", "dec"]
DAYS = ["lun", "mar", "mie", "joi", "vin", "sâm", "dum"]


COUNTRIES_RO = {
    "Albania": "Albania", "Armenia": "Armenia", "Austria": "Austria", "Azerbaijan": "Azerbaidjan",
    "Belgium": "Belgia", "Bosnia and Herzegovina": "Bosnia și Herțegovina", "Bulgaria": "Bulgaria",
    "Croatia": "Croația", "Cyprus": "Cipru", "Czech Republic": "Cehia", "Czechia": "Cehia",
    "Denmark": "Danemarca", "Egypt": "Egipt", "Estonia": "Estonia", "Finland": "Finlanda",
    "France": "Franța", "Georgia": "Georgia", "Germany": "Germania", "Greece": "Grecia",
    "Hungary": "Ungaria", "Iceland": "Islanda", "Ireland": "Irlanda", "Israel": "Israel",
    "Italy": "Italia", "Jordan": "Iordania", "Kosovo": "Kosovo", "Latvia": "Letonia",
    "Lithuania": "Lituania", "Luxembourg": "Luxemburg", "Malta": "Malta", "Moldova": "Moldova",
    "Montenegro": "Muntenegru", "Morocco": "Maroc", "Netherlands": "Țările de Jos",
    "North Macedonia": "Macedonia de Nord", "Norway": "Norvegia", "Poland": "Polonia",
    "Portugal": "Portugalia", "Romania": "România", "Saudi Arabia": "Arabia Saudită",
    "Serbia": "Serbia", "Slovakia": "Slovacia", "Slovenia": "Slovenia", "Spain": "Spania",
    "Sweden": "Suedia", "Switzerland": "Elveția", "Türkiye": "Turcia", "Turkey": "Turcia",
    "Ukraine": "Ucraina", "United Arab Emirates": "Emiratele Arabe Unite",
    "United Kingdom": "Marea Britanie", "Tunisia": "Tunisia", "Lebanon": "Liban",
    "Kazakhstan": "Kazahstan", "Uzbekistan": "Uzbekistan", "Maldives": "Maldive",
    "Thailand": "Thailanda", "Oman": "Oman", "Qatar": "Qatar", "Kuwait": "Kuweit",
    "Bahrain": "Bahrain", "United States": "SUA", "Canada": "Canada", "Japan": "Japonia",
}


def country_ro(name):
    return COUNTRIES_RO.get(name or "", name or "")


def date_ro(iso, with_day=True):
    if not iso:
        return ""
    d = dt.date.fromisoformat(iso[:10])
    s = f"{d.day} {MONTHS[d.month - 1]}"
    return f"{DAYS[d.weekday()]} {s}" if with_day else s


def eur(v):
    if v is None:
        return "-"
    return f"{v:,.2f} €".replace(",", " ").replace(".", ",") if v < 100 else f"{round(v):,} €".replace(",", " ")


def lei(v):
    """1234.5 -> '1.234,50 lei'"""
    return f"{v:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + " lei"


def ron(price_eur, price_orig=None, currency=None):
    """Prețul în lei: exact dacă biletul e în lei, altfel la cursul BNR."""
    return lei(fx.lei_of(price_eur, price_orig, currency))


def place_name(code, places):
    if code in ORIGIN_NAMES:
        return ORIGIN_NAMES[code]
    p = places.get(code) or {}
    return p.get("name") or code


def nights(dep, ret):
    if not ret:
        return None
    return (dt.date.fromisoformat(ret) - dt.date.fromisoformat(dep)).days
