"""Site-urile oficiale ale companiilor aeriene (cod IATA -> nume, adresă), pentru „Rezervă la <companie>”."""

WIZZ_CODES = {"W6", "W4", "W9", "5W"}
RYANAIR_CODES = {"FR", "RK", "AL", "RR", "MW", "LW"}  # Ryanair, Buzz, Malta Air, Lauda: toate pe ryanair.com
PEGASUS_CODES = {"PC"}


def pegasus_link(frm, to, dep, ret="", adults=1, children=0, infants=0):
    """Exact zborul pe site-ul Pegasus (ruta, data, pasagerii), cu prețul real (Google nu vinde bilete Pegasus)."""
    return ("https://web.flypgs.com/booking?language=ro&adultCount=%d&childCount=%d&infantCount=%d"
            "&departurePort=%s&arrivalPort=%s&departureDate=%s%s&dateOption=1&currency=EUR"
            % (adults, children, infants, frm, to, dep, f"&returnDate={ret}" if ret else ""))

SITES = {
    **{c: ("Wizz Air", "https://www.wizzair.com/ro-ro") for c in WIZZ_CODES},
    **{c: ("Ryanair", "https://www.ryanair.com/ro/ro") for c in RYANAIR_CODES},
    "RO": ("TAROM", "https://www.tarom.ro"),
    "H4": ("HiSky", "https://hisky.aero"),
    "A2": ("Animawings", "https://www.animawings.com"),
    "PC": ("Pegasus Airlines", "https://www.flypgs.com"),
    "VF": ("AJet", "https://ajet.com"),
    "XQ": ("SunExpress", "https://www.sunexpress.com"),
    "TK": ("Turkish Airlines", "https://www.turkishairlines.com"),
    "LH": ("Lufthansa", "https://www.lufthansa.com"),
    "VL": ("Lufthansa", "https://www.lufthansa.com"),
    "OS": ("Austrian Airlines", "https://www.austrian.com"),
    "LX": ("SWISS", "https://www.swiss.com"),
    "2L": ("Helvetic Airways", "https://www.helvetic.com"),
    "EW": ("Eurowings", "https://www.eurowings.com"),
    "DE": ("Condor", "https://www.condor.com"),
    "LO": ("LOT", "https://www.lot.com"),
    "JU": ("Air Serbia", "https://www.airserbia.com"),
    "OU": ("Croatia Airlines", "https://www.croatiaairlines.com"),
    "FB": ("Bulgaria Air", "https://www.air.bg"),
    "A3": ("Aegean Airlines", "https://en.aegeanair.com"),
    "BA": ("British Airways", "https://www.britishairways.com"),
    "AF": ("Air France", "https://www.airfrance.com"),
    "KL": ("KLM", "https://www.klm.com"),
    "IB": ("Iberia", "https://www.iberia.com"),
    "UX": ("Air Europa", "https://www.aireuropa.com"),
    "VY": ("Vueling", "https://www.vueling.com"),
    "TP": ("TAP Air Portugal", "https://www.flytap.com"),
    "AZ": ("ITA Airways", "https://www.ita-airways.com"),
    "EI": ("Aer Lingus", "https://www.aerlingus.com"),
    "SK": ("SAS", "https://www.flysas.com"),
    "AY": ("Finnair", "https://www.finnair.com"),
    "N7": ("Finnair", "https://www.finnair.com"),
    "BT": ("airBaltic", "https://www.airbaltic.com"),
    "DY": ("Norwegian", "https://www.norwegian.com"),
    "D8": ("Norwegian", "https://www.norwegian.com"),
    "U2": ("easyJet", "https://www.easyjet.com"),
    "EC": ("easyJet", "https://www.easyjet.com"),
    "DS": ("easyJet", "https://www.easyjet.com"),
    "HV": ("Transavia", "https://www.transavia.com"),
    "X3": ("TUI fly", "https://www.tuifly.com"),
    "QS": ("Smartwings", "https://www.smartwings.com"),
    "WX": ("CityJet", "https://www.cityjet.com"),
    "LY": ("EL AL", "https://www.elal.com"),
    "6H": ("Israir", "https://www.israir.co.il"),
    "QR": ("Qatar Airways", "https://www.qatarairways.com"),
    "EK": ("Emirates", "https://www.emirates.com"),
    "EY": ("Etihad Airways", "https://www.etihad.com"),
    "FZ": ("flydubai", "https://www.flydubai.com"),
    "G9": ("Air Arabia", "https://www.airarabia.com"),
    "WY": ("Oman Air", "https://www.omanair.com"),
    "GF": ("Gulf Air", "https://www.gulfair.com"),
    "SV": ("Saudia", "https://www.saudia.com"),
    "RJ": ("Royal Jordanian", "https://www.rj.com"),
    "MS": ("EgyptAir", "https://www.egyptair.com"),
    "AT": ("Royal Air Maroc", "https://www.royalairmaroc.com"),
    "TU": ("Tunisair", "https://www.tunisair.com"),
    "ET": ("Ethiopian Airlines", "https://www.ethiopianairlines.com"),
    "KQ": ("Kenya Airways", "https://www.kenya-airways.com"),
    "MK": ("Air Mauritius", "https://www.airmauritius.com"),
    "J2": ("Azerbaijan Airlines", "https://www.azal.az"),
    "KC": ("Air Astana", "https://airastana.com"),
    "DV": ("SCAT", "https://www.scat.kz"),
    "HY": ("Uzbekistan Airways", "https://www.uzairways.com"),
    "AI": ("Air India", "https://www.airindia.com"),
    "UL": ("SriLankan Airlines", "https://www.srilankan.com"),
    "SQ": ("Singapore Airlines", "https://www.singaporeair.com"),
    "TG": ("THAI Airways", "https://www.thaiairways.com"),
    "VN": ("Vietnam Airlines", "https://www.vietnamairlines.com"),
    "CX": ("Cathay Pacific", "https://www.cathaypacific.com"),
    "CA": ("Air China", "https://www.airchina.com"),
    "MU": ("China Eastern", "https://www.ceair.com"),
    "FM": ("China Eastern", "https://www.ceair.com"),
    "CZ": ("China Southern", "https://www.csair.com"),
    "HU": ("Hainan Airlines", "https://www.hainanairlines.com"),
    "KE": ("Korean Air", "https://www.koreanair.com"),
    "NH": ("ANA", "https://www.ana.co.jp"),
    "JL": ("Japan Airlines", "https://www.jal.co.jp"),
    "UA": ("United Airlines", "https://www.united.com"),
    "AA": ("American Airlines", "https://www.aa.com"),
    "DL": ("Delta", "https://www.delta.com"),
    "AC": ("Air Canada", "https://www.aircanada.com"),
}


def site_of(code):
    """(nume, adresă) sau None."""
    return SITES.get((code or "").upper())
