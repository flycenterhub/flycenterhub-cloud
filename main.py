"""Zboruri ieftine - monitorizare bilete de avion din Timișoara, Budapesta, Oradea, Cluj și București.

Utilizare:
    python main.py                  pornește aplicația (dashboard + scanări automate)
    python main.py --open           la fel, și deschide dashboard-ul în browser
    python main.py --scan           o singură scanare completă, apoi iese
    python main.py --feeds          verifică o dată site-urile de oferte
    python main.py --telegram       configurează notificările Telegram
    python main.py --autostart-on   pornește automat odată cu Windows
    python main.py --autostart-off  oprește pornirea automată
    python main.py --send-telegram "text"   trimite un mesaj pe Telegram (folosit de rutina zilnică)
"""
import argparse
import logging
import os
import socket
import sys
import threading
import webbrowser
from logging.handlers import RotatingFileHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import config  # noqa: E402

STARTUP_FILE = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup",
                            "ZboruriIeftine.vbs")


def setup_logging(console=True):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    handlers = [RotatingFileHandler(os.path.join(config.DATA_DIR, "app.log"), maxBytes=2_000_000,
                                    backupCount=3, encoding="utf-8")]
    if console and sys.stdout:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def our_app_on(port):
    """True dacă pe portul dat răspunde chiar această aplicație."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=3) as r:
            return "running" in json.loads(r.read().decode("utf-8"))
    except Exception:
        return False


def run_app(open_browser):
    cfg = config.load()
    port = int(cfg["port"])
    if our_app_on(port):
        # Aplicația rulează deja (de ex. pornită automat cu Windows)
        if open_browser:
            webbrowser.open(config.dashboard_url(cfg))
        return
    setup_logging()
    log = logging.getLogger("main")
    if port_in_use(port):
        # Portul e ocupat de alt program: folosim un port de rezervă
        log.warning("Portul %s e ocupat de alt program - folosesc 8765", port)
        port = cfg["port"] = 8765
        if our_app_on(port):
            if open_browser:
                webbrowser.open(config.dashboard_url(cfg))
            return
    url = config.dashboard_url(cfg)
    from app.engine import Engine
    from app.server import serve, serve_redirect
    engine = Engine()
    engine.dashboard_url = url
    httpd = serve(engine, port)
    with open(os.path.join(config.DATA_DIR, "app.pid"), "w") as f:
        f.write(str(os.getpid()))
    for old in cfg.get("legacy_ports") or []:
        if int(old) != port and not port_in_use(int(old)):
            try:
                threading.Thread(target=serve_redirect(int(old), url).serve_forever, daemon=True).start()
            except OSError:
                pass
    threading.Thread(target=engine.scheduler, daemon=True).start()
    logging.getLogger("main").info("Dashboard: %s", url)
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop.set()


def run_scan():
    setup_logging()
    from app.engine import Engine
    e = Engine()
    last = {}

    def show():
        import time
        while e.running or not last:
            p = " | ".join(e.progress.values())
            if p and p != last.get("p"):
                print("  " + p, flush=True)
                last["p"] = p
            last["x"] = 1
            time.sleep(2)
    threading.Thread(target=show, daemon=True).start()
    e.full_scan()
    s = e.db.last_scan("full")
    print("\nRezultat:", s["status"], s["info"])


def run_feeds():
    setup_logging()
    from app.engine import Engine
    new = Engine().poll_feeds()
    print(f"{len(new)} articole noi relevante")
    for p in new:
        print(f"  [{p['feed']}] {p['cities']}: {p['title']}")


def setup_telegram():
    from app import telegram
    cfg = config.load()
    print("=== Configurare Telegram ===\n")
    print("1. Deschide Telegram și caută @BotFather")
    print("2. Trimite-i mesajul /newbot, alege un nume (ex: Zboruri Ieftine) și un username terminat în 'bot'")
    print("3. BotFather îți dă un token de forma 123456789:ABCdef...\n")
    token = input("Lipește aici tokenul și apasă Enter: ").strip()
    if not token:
        print("Nu ai introdus niciun token.")
        return
    try:
        me = telegram._call(token, "getMe")
    except Exception as e:
        print(f"Tokenul nu pare valid: {e}")
        return
    print(f"\nPerfect, botul tău este @{me['username']}.")
    print(f"4. Deschide în Telegram https://t.me/{me['username']} , apasă START (sau trimite orice mesaj).")
    print("   Aștept mesajul tău (maxim 3 minute)...")
    chat_id, _ = telegram.discover_chat_id(token, 180)
    if not chat_id:
        print("Nu am primit niciun mesaj. Rulează din nou configurarea.")
        return
    cfg["telegram"].update({"enabled": True, "bot_token": token, "chat_id": str(chat_id)})
    config.save(cfg)
    telegram.send(cfg, "✅ Gata! De acum primești aici ofertele de zbor din Timișoara, Budapesta, Oradea, Cluj și București.")
    print("\nGata! Ți-am trimis un mesaj de test pe Telegram. Notificările sunt active.")
    print("Dacă aplicația rulează deja, preia setările la următoarea scanare.")


def autostart(on):
    if on:
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pyw):
            pyw = sys.executable
        script = os.path.abspath(__file__)
        vbs = (
            'Set sh = CreateObject("WScript.Shell")\r\n'
            f'sh.CurrentDirectory = "{os.path.dirname(script)}"\r\n'
            f'sh.Run """{pyw}"" ""{script}""", 0, False\r\n'
        )
        with open(STARTUP_FILE, "w", encoding="utf-8") as f:
            f.write(vbs)
        print(f"Pornirea automată este activă ({STARTUP_FILE}).")
        print("Aplicația va porni singură, invizibil, la fiecare pornire a Windows-ului.")
    else:
        if os.path.exists(STARTUP_FILE):
            os.remove(STARTUP_FILE)
            print("Pornirea automată a fost dezactivată.")
        else:
            print("Pornirea automată nu era activă.")


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Zboruri ieftine")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--feeds", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--autostart-on", action="store_true")
    ap.add_argument("--autostart-off", action="store_true")
    ap.add_argument("--send-telegram", metavar="TEXT", help="trimite un mesaj (HTML Telegram) pe botul configurat")
    a = ap.parse_args()
    if a.send_telegram:
        from app import telegram
        cfg = config.load()
        if not telegram.enabled(cfg):
            print("Telegram nu este configurat")
            sys.exit(1)
        telegram.send(cfg, a.send_telegram)
        print("Trimis")
    elif a.scan:
        run_scan()
    elif a.feeds:
        run_feeds()
    elif a.telegram:
        setup_telegram()
    elif a.autostart_on:
        autostart(True)
    elif a.autostart_off:
        autostart(False)
    else:
        run_app(a.open)


if __name__ == "__main__":
    main()
