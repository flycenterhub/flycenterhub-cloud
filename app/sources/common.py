"""Funcții comune pentru surse: intervale de date, combinare dus-întors, linkuri."""
import base64
import datetime as dt
import logging
import time
import urllib.parse

log = logging.getLogger("sources")


class Throttle:
    """Pauză adaptivă între cereri: crește când serverul semnalează suprasolicitare."""

    def __init__(self, base, maximum=6.0):
        self.base = self.delay = float(base)
        self.maximum = maximum

    def hit(self, status=None):
        self.delay = min(self.delay * 1.6 + 0.5, self.maximum)

    def ok(self):
        self.delay = max(self.base, self.delay * 0.98)

    def sleep(self, factor=1.0):
        time.sleep(self.delay * factor)


def scan_routes(name, pairs, fetch_route, info, progress, stop, throttle):
    """Parcurge rutele (origin, dest); cele eșuate se reîncearcă o dată la final, după o pauză."""
    failed, fails_in_row = [], 0
    for attempt in (1, 2):
        todo = pairs if attempt == 1 else failed
        if attempt == 2:
            if not failed or stop.is_set():
                break
            failed = []
            progress(f"{name}: pauză înainte de reîncercare ({len(todo)} rute)")
            stop.wait(90)
        for i, (o, d) in enumerate(todo, 1):
            if stop.is_set():
                return
            progress(f"{name} {o}→{d} ({i}/{len(todo)}{', reîncercare' if attempt == 2 else ''})",
                     i - 1 if attempt == 1 else len(pairs), len(pairs))
            try:
                n = fetch_route(o, d)
                info["routes_ok"] += 1
                info["fares"] += n
                fails_in_row = 0
                throttle.ok()
            except Exception as e:
                fails_in_row += 1
                throttle.hit()
                log.warning("%s %s-%s: %s", name, o, d, e)
                if attempt == 1:
                    failed.append((o, d))
                else:
                    info["routes_failed"] += 1
                    if len(info["errors"]) < 10:
                        info["errors"].append(f"{o}-{d}: {e}")
                if fails_in_row >= 8:
                    info["routes_failed"] += len(todo) - i + (len(failed) if attempt == 1 else 0)
                    info["errors"].append(f"Prea multe erori la rând - opresc {name} pentru această scanare")
                    return
                throttle.sleep(5)


def date_range_end(months_ahead):
    return dt.date.today() + dt.timedelta(days=int(months_ahead * 30.5))


def month_starts(months_ahead):
    """Prima zi a fiecărei luni de acum până la orizontul de căutare."""
    today = dt.date.today()
    end = date_range_end(months_ahead)
    d = today.replace(day=1)
    out = []
    while d <= end:
        out.append(d)
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out


def windows(months_ahead, days=30):
    """Intervale consecutive [start, end] de maximum `days`+1 zile."""
    start = dt.date.today()
    end = date_range_end(months_ahead)
    out = []
    while start <= end:
        stop = min(start + dt.timedelta(days=days), end)
        out.append((start, stop))
        start = stop + dt.timedelta(days=1)
    return out


def combine_round_trips(out_fares, back_fares, min_nights, max_nights, make_row):
    """Pentru fiecare zi de plecare, cel mai ieftin retur între min_nights și max_nights nopți.

    out_fares/back_fares: dict {date_iso: fare_row(OW)}. make_row(out, back) -> rând dus-întors.
    """
    back_by_date = {dt.date.fromisoformat(k): v for k, v in back_fares.items()}
    rows = []
    for d_iso, o in out_fares.items():
        d = dt.date.fromisoformat(d_iso)
        best = None
        for n in range(min_nights, max_nights + 1):
            b = back_by_date.get(d + dt.timedelta(days=n))
            if b and (best is None or b["price_eur"] < best["price_eur"]):
                best = b
        if best:
            rows.append(make_row(o, best))
    return rows


def _pb_varint(n):
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _pb(field, value):
    """Un câmp protobuf: număr (varint) sau text/octeți."""
    if isinstance(value, int):
        return _pb_varint(field << 3) + _pb_varint(value)
    data = value.encode() if isinstance(value, str) else value
    return _pb_varint(field << 3 | 2) + _pb_varint(len(data)) + data


def _gf_airports(field, code):
    from .serpapi import CITY_AIRPORTS  # coduri de oraș (LON, TYO...) -> toate aeroporturile orașului
    return b"".join(_pb(field, _pb(1, 1) + _pb(2, a)) for a in CITY_AIRPORTS.get(code, code).split(","))


def google_flights_link(origin, dest, dep_date, ret_date="", adults=1, children=0, infants=0):
    """Google Flights direct pe rezultatele pentru exact ruta, datele și pasagerii (formatul „tfs” al Google)."""
    legs = [(dep_date, origin, dest)] + ([(ret_date, dest, origin)] if ret_date else [])
    tfs = _pb(1, 28) + _pb(2, 2)
    for day, a, b in legs:
        tfs += _pb(3, _pb(2, day) + _gf_airports(13, a) + _gf_airports(14, b))
    for kind, n in ((1, adults), (2, children), (4, infants)):
        tfs += _pb(8, kind) * max(n, 0)
    tfs += _pb(9, 1) + _pb(14, 1) + _pb(19, 1 if ret_date else 2)
    code = base64.urlsafe_b64encode(tfs).decode().rstrip("=")
    return f"https://www.google.com/travel/flights/search?tfs={code}&hl=ro&gl=ro&curr=EUR"
