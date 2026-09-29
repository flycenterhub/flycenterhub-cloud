"""Baza de date SQLite: prețuri curente, istoric pe rute, oferte, articole de pe site-uri."""
import datetime as dt
import json
import os
import sqlite3
import threading

from . import config

DB_PATH = os.path.join(config.DATA_DIR, "zboruri.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS fares(
    source TEXT NOT NULL, origin TEXT NOT NULL, dest TEXT NOT NULL,
    dep_date TEXT NOT NULL, ret_date TEXT NOT NULL DEFAULT '',
    price_eur REAL NOT NULL, price_orig REAL, currency TEXT,
    dep_time TEXT, ret_time TEXT, flight_no TEXT, airline TEXT, link TEXT,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, last_scan INTEGER,
    prev_price_eur REAL, price_changed_at TEXT, lowest_eur REAL,
    PRIMARY KEY(source, origin, dest, dep_date, ret_date)
);
CREATE INDEX IF NOT EXISTS ix_fares_route ON fares(origin, dest);
CREATE INDEX IF NOT EXISTS ix_fares_dep ON fares(dep_date);

CREATE TABLE IF NOT EXISTS route_daily(
    day TEXT NOT NULL, origin TEXT NOT NULL, dest TEXT NOT NULL, trip TEXT NOT NULL,
    min_eur REAL, p25_eur REAL, p50_eur REAL, n INTEGER,
    PRIMARY KEY(day, origin, dest, trip)
);

CREATE TABLE IF NOT EXISTS route_stats(
    origin TEXT NOT NULL, dest TEXT NOT NULL, trip TEXT NOT NULL,
    typical_eur REAL, min_prev_eur REAL, history_days INTEGER, n_today INTEGER,
    PRIMARY KEY(origin, dest, trip)
);

CREATE TABLE IF NOT EXISTS deals(
    source TEXT, origin TEXT, dest TEXT, trip TEXT, dep_date TEXT, ret_date TEXT,
    price_eur REAL, typical_eur REAL, discount_pct REAL, min_prev_eur REAL,
    prev_price_eur REAL, history_days INTEGER, flags TEXT, score REAL, days_to_dep INTEGER,
    dep_time TEXT, ret_time TEXT, airline TEXT, flight_no TEXT, link TEXT, computed_at TEXT,
    is_new INTEGER DEFAULT 0,
    PRIMARY KEY(source, origin, dest, dep_date, ret_date)
);

CREATE TABLE IF NOT EXISTS notified(
    route_key TEXT PRIMARY KEY, price_eur REAL, notified_at TEXT
);

CREATE TABLE IF NOT EXISTS posts(
    url TEXT PRIMARY KEY, feed TEXT, title TEXT, summary TEXT, published TEXT,
    cities TEXT, first_seen TEXT, notified INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS places(code TEXT PRIMARY KEY, name TEXT, country TEXT);

CREATE TABLE IF NOT EXISTS scans(
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, started_at TEXT, finished_at TEXT,
    status TEXT, info TEXT
);

CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""

FARE_COLS = ["source", "origin", "dest", "dep_date", "ret_date", "price_eur", "price_orig",
             "currency", "dep_time", "ret_time", "flight_no", "airline", "link"]

UPSERT = f"""
INSERT INTO fares({", ".join(FARE_COLS)}, first_seen, last_seen, last_scan, lowest_eur)
VALUES({", ".join("?" * len(FARE_COLS))}, ?, ?, ?, ?)
ON CONFLICT(source, origin, dest, dep_date, ret_date) DO UPDATE SET
    prev_price_eur = CASE WHEN abs(coalesce(excluded.price_orig, 0) - coalesce(fares.price_orig, 0)) >= 0.01
                          THEN fares.price_eur ELSE fares.prev_price_eur END,
    price_changed_at = CASE WHEN abs(coalesce(excluded.price_orig, 0) - coalesce(fares.price_orig, 0)) >= 0.01
                          THEN excluded.last_seen ELSE fares.price_changed_at END,
    price_eur = excluded.price_eur, price_orig = excluded.price_orig, currency = excluded.currency,
    dep_time = excluded.dep_time, ret_time = excluded.ret_time, flight_no = excluded.flight_no,
    airline = excluded.airline, link = excluded.link,
    last_seen = excluded.last_seen, last_scan = excluded.last_scan,
    lowest_eur = min(coalesce(fares.lowest_eur, excluded.price_eur), excluded.price_eur)
"""


def now_str():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class DB:
    def __init__(self, path=DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript(SCHEMA)
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(places)")]
            if "cc" not in cols:
                self.conn.execute("ALTER TABLE places ADD COLUMN cc TEXT")
            self.conn.commit()

    # ---------- utilitare ----------
    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def q1(self, sql, args=()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    def get_kv(self, k, default=None):
        r = self.q1("SELECT v FROM kv WHERE k=?", (k,))
        return json.loads(r["v"]) if r else default

    def set_kv(self, k, v):
        self.x("INSERT INTO kv(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
               (k, json.dumps(v)))

    # ---------- scanări ----------
    def start_scan(self, kind):
        cur = self.x("INSERT INTO scans(kind, started_at, status) VALUES(?, ?, 'running')", (kind, now_str()))
        return cur.lastrowid

    def finish_scan(self, scan_id, status, info):
        self.x("UPDATE scans SET finished_at=?, status=?, info=? WHERE id=?",
               (now_str(), status, json.dumps(info, ensure_ascii=False), scan_id))

    def last_scan(self, kind, finished_only=True):
        cond = "AND finished_at IS NOT NULL AND status != 'interrupted'" if finished_only else ""
        r = self.q1(f"SELECT * FROM scans WHERE kind=? {cond} ORDER BY id DESC LIMIT 1", (kind,))
        if r and r.get("info"):
            r["info"] = json.loads(r["info"])
        return r

    # ---------- prețuri ----------
    def save_places(self, places):
        """places: iterabil de (code, name, country[, cod_țară_ISO2])."""
        def clean(v):
            return v.strip() if isinstance(v, str) else v
        rows = [(p[0], clean(p[1]), clean(p[2]), (p[3] or "").upper() or None if len(p) > 3 else None)
                for p in places]
        with self.lock:
            self.conn.executemany(
                "INSERT INTO places(code, name, country, cc) VALUES(?, ?, ?, ?) "
                "ON CONFLICT(code) DO UPDATE SET name=coalesce(excluded.name, places.name), "
                "country=coalesce(excluded.country, places.country), cc=coalesce(excluded.cc, places.cc)", rows)
            self.conn.commit()

    def _upsert(self, scan_id, rows, ts):
        self.conn.executemany(UPSERT, [
            tuple(r.get(c, "" if c == "ret_date" else None) for c in FARE_COLS) + (ts, ts, scan_id, r["price_eur"])
            for r in rows])

    def upsert_rows(self, scan_id, rows):
        with self.lock:
            self._upsert(scan_id, rows, now_str())
            self.conn.commit()

    def replace_route(self, source, scan_id, a, b, rows):
        """Salvează prețurile pentru perechea a<->b și șterge ce nu mai există (zboruri epuizate)."""
        ts = now_str()
        with self.lock:
            self._upsert(scan_id, rows, ts)
            self.conn.execute(
                "DELETE FROM fares WHERE source=? AND ((origin=? AND dest=?) OR (origin=? AND dest=?)) "
                "AND last_scan != ?", (source, a, b, b, a, scan_id))
            self.conn.commit()

    def replace_origin(self, source, scan_id, origin, rows):
        ts = now_str()
        with self.lock:
            self._upsert(scan_id, rows, ts)
            self.conn.execute("DELETE FROM fares WHERE source=? AND origin=? AND last_scan != ?",
                              (source, origin, scan_id))
            self.conn.commit()

    def cleanup(self):
        today = dt.date.today().isoformat()
        old = (dt.datetime.now() - dt.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        cutoff_hist = (dt.date.today() - dt.timedelta(days=400)).isoformat()
        with self.lock:
            self.conn.execute("DELETE FROM fares WHERE dep_date < ? OR last_seen < ?", (today, old))
            self.conn.execute("DELETE FROM route_daily WHERE day < ?", (cutoff_hist,))
            self.conn.execute("DELETE FROM posts WHERE first_seen < ?", (cutoff_hist,))
            self.conn.commit()
