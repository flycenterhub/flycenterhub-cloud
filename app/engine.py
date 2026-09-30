"""Motorul: rulează scanările (automat, la interval) și trimite alertele."""
import datetime as dt
import logging
import threading
import time
import traceback

from . import analysis, config, fx, telegram
from .db import DB
from .fmt import country_ro
from .regions import region_of
from .sources import aviasales, feeds, ryanair, wizzair

log = logging.getLogger("engine")

SOURCES = [("ryanair", ryanair), ("wizzair", wizzair), ("aviasales", aviasales)]
FAR_REGIONS = {"asia", "insule", "america_n", "caraibe", "america_s", "oceania"}


def _parse(ts):
    return dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") if ts else None


class Engine:
    def __init__(self):
        self.db = DB()
        self.cfg = config.load()
        self.scan_lock = threading.Lock()
        self.feeds_lock = threading.Lock()
        self.stop = threading.Event()
        self.progress = {}
        self.progress_counts = {}
        self.running = False
        self.scan_kind = None
        self.scan_started = None
        self.data_version = 0          # crește când se recalculează ofertele (dashboard-ul se reîncarcă)
        self.analysis_lock = threading.Lock()
        self.publish_lock = threading.Lock()
        self.linkcheck_lock = threading.Lock()
        self.dashboard_url = config.dashboard_url(self.cfg)

    def _prog(self, name, text, done=None, total=None):
        self.progress[name] = text
        if total:
            self.progress_counts[name] = (done or 0, total)

    def progress_info(self):
        """Procentul scanării în curs și minutele estimate rămase."""
        if not self.running or not self.progress_counts:
            return None, None
        done = sum(d for d, _ in self.progress_counts.values())
        total = sum(t for _, t in self.progress_counts.values())
        pct = min(99, round(done / total * 100)) if total else 0
        elapsed = time.time() - (self.scan_started or time.time())
        eta = round(elapsed / done * (total - done) / 60) if done >= 3 else None
        return pct, eta

    def reanalyze(self, final=False):
        """Recalculează ofertele din prețurile curente (și în timpul scanării, ca să vezi prețuri noi)."""
        with self.analysis_lock:
            deals = analysis.run(self.cfg, self.db, final=final)
            self.data_version += 1
            return deals

    # ---------- scanare completă ----------
    def source_enabled(self, cfg, name):
        v = cfg["sources"].get(name)
        return bool(v.get("enabled") and v.get("token")) if isinstance(v, dict) else bool(v)

    def quick_scan(self, manual=False):
        """Verificare rapidă (la oră): Aviasales + cele mai mici prețuri Ryanair spre toate destinațiile."""
        return self.full_scan(only=["ryanair", "aviasales"], quick=True, manual=manual)

    def full_scan(self, only=None, quick=False, manual=False):
        """Scanează toate sursele active (sau doar cele din `only`) și recalculează ofertele."""
        if not self.scan_lock.acquire(blocking=False):
            return False
        self.running = True
        self.progress = {}
        self.progress_counts = {}
        self.scan_kind = "quick" if quick else "partial" if only else "full"
        self.scan_started = time.time()
        scan_id = None
        try:
            cfg = self.cfg = config.load()
            fx.refresh()
            scan_id = self.db.start_scan("quick" if quick else "partial" if only else "full")
            t0 = time.time()
            results = {}
            threads = []
            for name, mod in SOURCES:
                if not self.source_enabled(cfg, name) or (only and name not in only):
                    continue
                fn = getattr(mod, "quick", mod.scan) if quick else mod.scan

                def work(name=name, fn=fn):
                    try:
                        results[name] = fn(cfg, self.db, scan_id,
                                           lambda s, d=None, t=None, n=name: self._prog(n, s, d, t), self.stop)
                        if name == "aviasales" and not quick and not only:
                            # după Aviasales: zborurile dus din orașele exotice spre casă (dus într-un oraș, întors din altul)
                            from . import extras
                            try:
                                results["exotic_back"] = extras.scan_exotic_back(
                                    cfg, self.db, lambda s, d=None, t=None: self._prog("exotice-intors", s, d, t), self.stop)
                            except Exception as e:
                                log.warning("Exotice întors: %s", e)
                            finally:
                                self.progress.pop("exotice-intors", None)
                                if "exotice-intors" in self.progress_counts:
                                    self.progress_counts["exotice-intors"] = (self.progress_counts["exotice-intors"][1],) * 2
                        if name == "ryanair" and not quick and not only:
                            # după Ryanair: zborurile din hub-uri, pentru escalele făcute de tine (extras.py)
                            from . import extras
                            try:
                                results["escale"] = extras.scan_hubs(
                                    cfg, self.db, lambda s, d=None, t=None: self._prog("escale", s, d, t), self.stop)
                            except Exception as e:
                                log.warning("Escale: %s", e)
                            finally:
                                self.progress.pop("escale", None)
                                if "escale" in self.progress_counts:
                                    self.progress_counts["escale"] = (self.progress_counts["escale"][1],) * 2
                    except Exception as e:
                        log.error("Sursa %s a eșuat: %s", name, traceback.format_exc())
                        results[name] = {"routes_ok": 0, "routes_failed": 0, "fares": 0, "errors": [str(e)]}
                    finally:
                        self.progress.pop(name, None)
                        if name in self.progress_counts:
                            self.progress_counts[name] = (self.progress_counts[name][1],) * 2
                t = threading.Thread(target=work, daemon=True)
                t.start()
                threads.append(t)

            # Pe parcursul scanării, ofertele se recalculează la ~2 minute cu prețurile deja aduse
            done_evt = threading.Event()

            def refresher():
                while not done_evt.wait(120):
                    try:
                        self.reanalyze()
                    except Exception:
                        log.error("Actualizare intermediară: %s", traceback.format_exc())
            if not quick:
                threading.Thread(target=refresher, daemon=True).start()
            for t in threads:
                t.join()
            done_evt.set()

            self.progress["analiza"] = "Calculez ofertele…"
            self.db.cleanup()
            deals = self.reanalyze(final=True)
            info = {"sources": results, "deals": len(deals), "seconds": round(time.time() - t0)}
            ok = any(r.get("routes_ok") for r in results.values())
            errors = any(r.get("errors") for r in results.values())
            status = "ok" if ok and not errors else ("partial" if ok else "error")
            if ok:
                info["alerts"] = self.send_deal_alerts(cfg, deals)
                try:  # poze pentru destinațiile noi (Wikimedia Commons)
                    from . import photos
                    photos.refresh(self.db)
                except Exception as e:
                    log.warning("Poze: %s", e)
                try:  # vremea medie la destinațiile noi (NASA POWER)
                    from . import extras
                    extras.refresh_climate(self.db)
                except Exception as e:
                    log.warning("Vremea: %s", e)
                # scanare pornită din butoane: publică imediat; automată: cel mult o dată la N minute
                threading.Thread(target=self.publish_site, args=(manual,), daemon=True).start()
            self.db.finish_scan(scan_id, status, info)
            log.info("Scanare terminată: %s, %s oferte, %ss", status, len(deals), info["seconds"])
            return True
        except Exception as e:
            log.error("Scanarea a eșuat: %s", traceback.format_exc())
            if scan_id:
                self.db.finish_scan(scan_id, "error", {"error": str(e)})
            return False
        finally:
            self.progress = {}
            self.progress_counts = {}
            self.running = False
            self.scan_kind = None
            self.scan_lock.release()

    def send_deal_alerts(self, cfg, deals):
        # pe Telegram vin doar prețuri reale: Wizz Air, Ryanair și cele confirmate pe Google Flights
        deals = [d for d in deals if d["source"] != "aviasales"]
        items, first = analysis.select_alerts(cfg, self.db, deals)
        if not telegram.enabled(cfg):
            return 0
        if not items:
            return 0
        places = self.places()

        def region(d):
            p = places.get(d["dest"]) or {}
            return region_of(d["dest"], p.get("cc"), p.get("country_en"))

        def exotic(d):
            return bool(region(d))
        n = int(cfg["telegram"]["max_items_per_message"])
        n_ex = max(5, n // 2)
        # Întâi destinațiile îndepărtate (Asia, insule, America, Oceania), apoi Orientul Mijlociu / Africa
        far = [d for d in items if region(d) in FAR_REGIONS]
        near = [d for d in items if exotic(d) and region(d) not in FAR_REGIONS]
        ex = far[: max(n_ex - min(2, len(near)), 0)]
        ex += near[: n_ex - len(ex)]
        lm = [d for d in items if not exotic(d) and "LAST_MINUTE" in d["flags"]][: max(4, n // 3)]
        reg = [d for d in items if not exotic(d) and "LAST_MINUTE" not in d["flags"]][:n]
        top = reg + lm + ex
        sections = [("🔥 Oferte", reg), ("⏰ Last minute", lm), ("🌴 Exotice", ex)]
        try:
            telegram.send(cfg, telegram.format_deals(sections, places, first, self.share_url()))
        except Exception as e:
            log.error("Telegram: %s", e)
            return 0
        # La prima rulare marcăm toate ofertele existente, ca să nu primești sute de mesaje
        analysis.mark_notified(self.db, items if first else top)
        return len(top)

    def share_url(self):
        """Linkul din mesajele Telegram: site-ul public (merge și pe telefon) sau, dacă nu există, cel local."""
        url = (self.db.get_kv("public_site") or {}).get("url")
        return url or f"{self.dashboard_url} (pe calculatorul tău)"

    def places(self):
        return {r["code"]: {**r, "country": country_ro(r["country"]), "country_en": r["country"]}
                for r in self.db.q("SELECT * FROM places")}

    # ---------- site-uri de oferte ----------
    def poll_feeds(self):
        if not self.feeds_lock.acquire(blocking=False):
            return []
        try:
            cfg = self.cfg = config.load()
            first = not self.db.q1("SELECT 1 AS x FROM posts LIMIT 1")
            new, errors = feeds.poll(cfg, self.db)
            self.db.set_kv("feeds_last", {"at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                          "new": len(new), "errors": errors})
            if new and not first and telegram.enabled(cfg) and cfg["telegram"].get("send_feed_posts", True):
                try:
                    telegram.send(cfg, "🗞 <b>Oferte noi pe site-uri de specialitate</b>\n\n" +
                                  telegram.format_posts(new[:15], self.places()))
                    self.db.x(f"UPDATE posts SET notified=1 WHERE url IN ({','.join('?' * len(new))})",
                              [p["url"] for p in new])
                except Exception as e:
                    log.error("Telegram (articole): %s", e)
            return new
        except Exception:
            log.error("Feed-uri: %s", traceback.format_exc())
            return []
        finally:
            self.feeds_lock.release()

    # ---------- prețuri reale Google Flights (SerpApi) ----------
    def auto_verify(self):
        """Confirmă zilnic pe Google Flights cele mai bune zboruri ale altor companii (prioritate: exotice)."""
        from .sources import serpapi
        cfg = self.cfg = config.load()
        if not serpapi.enabled(cfg):
            return 0
        s = cfg.get("serpapi") or {}
        per_day, limit = int(s.get("auto_per_day", 0)), int(s.get("monthly_limit", 250))
        if per_day <= 0:
            return 0
        places = self.places()
        explored = 0

        def region(d):
            p = places.get(d["dest"]) or {}
            return region_of(d["dest"], p.get("cc"), p.get("country_en"))
        cands = analysis.best_per_route([dict(r) for r in self.db.q(
            "SELECT * FROM deals WHERE source='aviasales' OR (source='google' AND link NOT LIKE 'gfpost:%' AND link NOT LIKE '%flypgs%')")])
        cands.sort(key=lambda d: (0 if region(d) in FAR_REGIONS else 1 if region(d) else 2, -d["score"], d["price_eur"]))
        recent = self.db.get_kv("gf_checked", {}) or {}
        cutoff = (dt.date.today() - dt.timedelta(days=3)).isoformat()
        done = 0
        for d in cands:
            # o verificare = până la 3 căutări; păstrăm 30 pe lună pentru butonul „Verifică prețul real”
            if done >= per_day or serpapi.used_this_month(self.db) + 3 > limit - 30:
                break
            k = f"{d['origin']}-{d['dest']}-{d['dep_date']}-{d['ret_date']}"
            if recent.get(k, "") >= cutoff:
                continue
            try:
                serpapi.check(cfg, self.db, d["origin"], d["dest"], d["dep_date"], d["ret_date"])
            except Exception as e:
                log.warning("Google Flights: %s", e)
                break
            recent[k] = dt.date.today().isoformat()
            done += 1
        self.db.set_kv("gf_checked", {k: v for k, v in recent.items() if v >= cutoff})
        if done or explored:
            deals = self.reanalyze()
            self.send_deal_alerts(cfg, deals)
            threading.Thread(target=self.publish_site, daemon=True).start()
        return done

    def explore_run(self, slot):
        """Destinațiile exotice cu preț real Google („Explore”), de mai multe ori pe zi.
        Fiecare rulare ia o parte din regiuni, ca toate să se actualizeze zilnic în limita lunară gratuită."""
        from .sources import serpapi
        cfg = self.cfg = config.load()
        s = cfg.get("serpapi") or {}
        from .queries import exotic_origins
        hours = s.get("explore_hours") or [10, 18]
        names = list(serpapi.EXPLORE_AREAS)
        origins = exotic_origins(cfg)
        # fiecare rulare: un oraș și jumătate din regiuni; după 2 zile toate combinațiile sunt actualizate
        k = dt.date.today().toordinal() * len(hours) + slot
        origin = origins[(k // 2) % len(origins)]
        part = names if s.get("explore_all_each_run") else names[k % 2::2]
        limit = int(s.get("monthly_limit", 250))
        if serpapi.used_this_month(self.db) + len(part) > limit - int(s.get("reserve", 20)):
            log.info("Google Explore: limita lunară aproape atinsă, sar peste rulare")
            return 0
        found = serpapi.explore(cfg, self.db, origin, {a: serpapi.EXPLORE_AREAS[a] for a in part})["found"]
        if found:
            deals = self.reanalyze()
            self.send_deal_alerts(cfg, deals)
            threading.Thread(target=self.publish_site, daemon=True).start()
        return found

    def check_links(self):
        """Zilnic: fiecare „Rezervă” trebuie să ducă exact la zborul lui (vezi linkcheck.py)."""
        from . import linkcheck
        if not self.linkcheck_lock.acquire(blocking=False):
            return None
        try:
            rep = linkcheck.run(self)
            if rep["fixed"] or rep["removed"]:
                self.reanalyze()
            threading.Thread(target=self.publish_site, args=(True,), daemon=True).start()
            return rep
        except Exception:
            log.error("Verificare linkuri: %s", traceback.format_exc())
            return None
        finally:
            self.linkcheck_lock.release()

    # ---------- site public (GitHub Pages) ----------
    def publish_site(self, force=False):
        """Publică copia doar-pentru-vizualizare a site-ului, cel mult o dată la N minute."""
        from . import publish
        ps = (config.load().get("public_site") or {})
        if not ps.get("enabled", True) or not (ps.get("github_token") or "").strip():
            return None
        if not self.publish_lock.acquire(blocking=False):
            self.db.set_kv("publish_pending", True)  # o publicare e deja în curs: mai publicăm o dată după ea
            return None
        try:
            last = (self.db.get_kv("public_site") or {}).get("last_publish")
            gap = float(ps.get("min_minutes_between_publishes", 50))
            if not force and last and _parse(last) > dt.datetime.now() - dt.timedelta(minutes=gap):
                self.db.set_kv("publish_pending", True)  # se publică automat când trece intervalul
                return None
            self.db.set_kv("publish_pending", False)
            res = publish.publish(self)
            if not (res or {}).get("ok"):
                self.db.set_kv("publish_pending", True)
            return res
        finally:
            self.publish_lock.release()

    # ---------- rezumatul zilnic ----------
    def daily_summary(self):
        from . import queries
        cfg = self.cfg = config.load()
        if not telegram.enabled(cfg):
            return False
        today = dt.date.today().isoformat()
        try:
            deals = queries.deals(self.db, cfg["origins"])
            top = sorted(deals, key=lambda d: (-d["score"], d["price_eur"]))[:5]
            lm = sorted([d for d in deals if "LAST_MINUTE" in d["flags"]], key=lambda d: d["price_eur"])[:3]
            ex = queries.exotic(self.db, cfg, self.source_enabled(cfg, "aviasales"))["fares"]
            ex = (sorted([r for r in ex if r["trip"] == "RT"], key=lambda r: r["price_eur"]) or ex)[:3]
            last = self.db.last_scan("full")
            counts = self.db.q1("SELECT (SELECT COUNT(*) FROM fares) AS fares, "
                                "(SELECT COUNT(DISTINCT origin || dest) FROM fares) AS routes")
            since = (dt.datetime.now() - dt.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            posts = self.db.q1("SELECT COUNT(*) AS n FROM posts WHERE first_seen >= ?", (since,))["n"]
            warnings = []
            if not last:
                warnings.append("încă nu s-a terminat nicio scanare")
            else:
                if last["status"] != "ok":
                    for name, r in (last.get("info") or {}).get("sources", {}).items():
                        if r.get("errors"):
                            warnings.append(f"{name}: {r.get('routes_failed', 0)} rute cu erori")
                age = dt.datetime.now() - (_parse(last["finished_at"]) or dt.datetime.now())
                if age > dt.timedelta(hours=float(cfg["scan_interval_hours"]) * 2 + 1):
                    warnings.append(f"ultima scanare reușită e de acum {int(age.total_seconds() // 3600)} ore")
            summary = {
                "last_scan": (last or {}).get("finished_at", "-")[:16], "fares": counts["fares"],
                "routes": counts["routes"] // 2 or counts["routes"], "deals": len(deals),
                "top": top, "lm": lm, "exotic": ex, "posts": posts, "warnings": warnings,
                "links": self.db.get_kv("linkcheck"),
            }
            telegram.send(cfg, telegram.format_daily(summary, self.places(), self.share_url()))
            self.db.set_kv("daily_summary_date", today)
            return True
        except Exception:
            log.error("Rezumat zilnic: %s", traceback.format_exc())
            return False

    # ---------- programare ----------
    def next_full_scan_at(self):
        last = self.db.last_scan("full")
        if not last:
            return dt.datetime.now()
        base = _parse(last["finished_at"]) or dt.datetime.now()
        hours = float(self.cfg["scan_interval_hours"])
        if last["status"] == "error":
            hours = min(hours, 1.0)
        return base + dt.timedelta(hours=hours)

    def next_quick_scan_at(self):
        last = self.db.q1("SELECT finished_at FROM scans WHERE finished_at IS NOT NULL AND status != 'interrupted' "
                          "ORDER BY id DESC LIMIT 1")
        minutes = float(self.cfg.get("quick_scan_interval_minutes") or 0)
        if not last or minutes <= 0:
            return None
        return _parse(last["finished_at"]) + dt.timedelta(minutes=minutes)

    def next_feeds_at(self):
        last = self.db.get_kv("feeds_last")
        if not last:
            return dt.datetime.now()
        return _parse(last["at"]) + dt.timedelta(minutes=float(self.cfg["feeds_interval_minutes"]))

    def scheduler(self):
        # Scanările rămase neterminate (aplicația a fost închisă/repornită) sunt marcate ca întrerupte;
        # nu sunt erori și nu se afișează ca ultima scanare
        self.db.x("UPDATE scans SET finished_at=?, status='interrupted', info='{\"error\": \"întreruptă\"}' "
                  "WHERE finished_at IS NULL", (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
        self.db.x("UPDATE scans SET status='interrupted' WHERE status='error' AND info LIKE '%întreruptă%'")
        while not self.stop.is_set():
            now = dt.datetime.now()
            try:
                # cursul BNR: verificat din oră în oră (la 10 minute după ora 13, până apare cel nou);
                # când BNR publică un curs nou, site-ul public se actualizează imediat cu prețurile în lei noi
                if fx.refresh() and not self.running:
                    threading.Thread(target=self.publish_site, args=(True,), daemon=True).start()
                # prima publicare a site-ului public, imediat ce există tokenul GitHub
                ps = self.cfg.get("public_site") or {}
                if (ps.get("github_token") or "").strip() and not self.running and                         not (self.db.get_kv("public_site") or {}).get("last_publish") and                         (self.db.get_kv("public_site") or {}).get("last_error_at", "") <                         (now - dt.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"):
                    threading.Thread(target=self.publish_site, args=(True,), daemon=True).start()
                if self.db.get_kv("publish_pending") and not self.running:
                    last = (self.db.get_kv("public_site") or {}).get("last_publish")
                    gap = float(ps.get("min_minutes_between_publishes", 50))
                    err = (self.db.get_kv("public_site") or {}).get("last_error_at", "")
                    if (not last or _parse(last) <= now - dt.timedelta(minutes=gap)) and                             err < (now - dt.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"):
                        threading.Thread(target=self.publish_site, daemon=True).start()
                if self.cfg["sources"].get("feeds", True) and now >= self.next_feeds_at():
                    threading.Thread(target=self.poll_feeds, daemon=True).start()
                if not self.running and now >= self.next_full_scan_at():
                    threading.Thread(target=self.full_scan, daemon=True).start()
                elif not self.running:
                    nq = self.next_quick_scan_at()
                    if nq and now >= nq:
                        threading.Thread(target=self.quick_scan, daemon=True).start()
                if (not self.running and now.hour >= 10 and (self.cfg.get("serpapi") or {}).get("api_key")
                        and self.db.get_kv("gf_auto_date") != now.date().isoformat()):
                    self.db.set_kv("gf_auto_date", now.date().isoformat())
                    threading.Thread(target=self.auto_verify, daemon=True).start()
                lh = int((self.cfg.get("link_check") or {}).get("hour", 7))
                if (not self.running and now.hour >= lh
                        and self.db.get_kv("linkcheck_date") != now.date().isoformat()):
                    self.db.set_kv("linkcheck_date", now.date().isoformat())
                    threading.Thread(target=self.check_links, daemon=True).start()
                sp = self.cfg.get("serpapi") or {}
                if not self.running and sp.get("api_key") and sp.get("explore", True):
                    today = now.date().isoformat()
                    done = self.db.get_kv("gf_explore_slots") or {}
                    if done.get("date") != today:
                        done = {"date": today, "slots": []}
                    for i, h in enumerate(sp.get("explore_hours") or [10, 18]):
                        if now.hour >= int(h) and i not in done["slots"]:
                            done["slots"].append(i)
                            self.db.set_kv("gf_explore_slots", done)
                            threading.Thread(target=self.explore_run, args=(i,), daemon=True).start()
                            break
                hour = (self.cfg.get("telegram") or {}).get("daily_summary_hour")
                if (hour is not None and now.hour >= int(hour) and not self.running and telegram.enabled(self.cfg)
                        and self.db.get_kv("daily_summary_date") != now.date().isoformat()):
                    self.db.set_kv("daily_summary_date", now.date().isoformat())
                    threading.Thread(target=self.daily_summary, daemon=True).start()
            except Exception:
                log.error("Planificator: %s", traceback.format_exc())
            self.stop.wait(30)
