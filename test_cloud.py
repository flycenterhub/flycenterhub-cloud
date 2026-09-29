"""Test: răspund Wizz Air, Ryanair și site-urile de oferte de pe serverele GitHub?"""
import datetime as dt
import re
import sys

from app import net
from app.sources import wizzair

ok = True
d0 = dt.date.today() + dt.timedelta(days=20)

try:
    html = net.get_text(wizzair.HOME, timeout=40, retries=2)
    m = re.search(r'(https://be\.wizzair\.com/[\d.]+/Api)', html)
    api = m.group(1)
    print("Wizz Air pagina:", "OK", api)
    conns, _ = wizzair.route_map(api)
    print("Wizz Air rute din BUD:", len(conns.get("BUD", [])))
    t = wizzair.timetable(api, "BUD", "LTN", d0, d0 + dt.timedelta(days=10))
    n = len(t.get("outboundFlights") or [])
    print("Wizz Air prețuri BUD-LTN:", n, "zile", [(f.get("departureDate", "")[:10], (f.get("price") or {}).get("amount"),
                                                     (f.get("price") or {}).get("currencyCode")) for f in (t.get("outboundFlights") or [])[:3]])
    ok &= n > 0
except Exception as e:
    ok = False
    print("Wizz Air EȘUAT:", repr(e)[:300])

try:
    r = net.get_json("https://www.ryanair.com/api/farfnd/v4/oneWayFares?departureAirportIataCode=BUD"
                     f"&outboundDepartureDateFrom={d0}&outboundDepartureDateTo={d0 + dt.timedelta(days=30)}")
    fares = r.get("fares") or []
    print("Ryanair prețuri din BUD:", len(fares), [(f["outbound"]["arrivalAirport"]["iataCode"], f["outbound"]["price"]["value"],
                                                   f["outbound"]["price"]["currencyCode"]) for f in fares[:3]])
    ok &= len(fares) > 0
except Exception as e:
    ok = False
    print("Ryanair EȘUAT:", repr(e)[:300])

for u in ["https://utazomajom.hu/feed/", "https://www.travelfree.info/feed/", "https://travelator.ro/feed/"]:
    try:
        x = net.get_text(u, timeout=30, retries=1)
        print("Feed", u, "OK", x.count("<item"))
    except Exception as e:
        print("Feed", u, "EȘUAT", repr(e)[:150])

print("REZULTAT:", "MERGE" if ok else "NU MERGE")
sys.exit(0)
