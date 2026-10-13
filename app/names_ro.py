"""Numele în română ale orașelor/aeroporturilor și țărilor (sursele le dau în engleză).
Folosit la publicare și în aplicație, ca vizitatorul să găsească „Viena”, nu doar „Vienna”."""

CITY = {
    "VIE": "Viena", "ATH": "Atena", "PRG": "Praga", "LIS": "Lisabona", "CPH": "Copenhaga", "MUC": "München",
    "CGN": "Köln", "SVQ": "Sevilla", "TRN": "Torino", "GOA": "Genova", "NUE": "Nürnberg", "LGW": "Londra Gatwick",
    "LHR": "Londra Heathrow", "LON": "Londra", "BBU": "București Băneasa", "GHV": "Brașov", "TGM": "Târgu Mureș",
    "SBZ": "Sibiu", "IAS": "Iași", "SCV": "Suceava", "BCM": "Bacău", "CND": "Constanța", "ARW": "Arad", "CRA": "Craiova",
    "VCE": "Veneția Marco Polo", "RHO": "Rodos", "WMI": "Varșovia Modlin", "WAW": "Varșovia Chopin", "BRU": "Bruxelles",
    "CDG": "Paris Charles de Gaulle", "MRS": "Marsilia", "NCE": "Nisa", "ZRH": "Zürich", "MXP": "Milano Malpensa",
    "LIN": "Milano Linate", "FLR": "Florența", "SKG": "Salonic", "HER": "Heraklion (Creta)", "KRK": "Cracovia",
    "GDN": "Gdańsk", "WRO": "Wrocław", "SPX": "Cairo Sphinx", "IST": "Istanbul", "SAW": "Istanbul Sabiha Gökçen",
    "BEG": "Belgrad", "EVN": "Erevan", "BAK": "Baku", "GYD": "Baku", "MOW": "Moscova", "SVO": "Moscova", "LED": "Sankt Petersburg",
    "BJS": "Beijing", "PEK": "Beijing", "SEL": "Seul", "ICN": "Seul", "TYO": "Tokyo", "FNJ": "Phenian", "RMO": "Chișinău",
    "KIV": "Chișinău", "KEF": "Reykjavík", "ARN": "Stockholm Arlanda", "NYO": "Stockholm Skavsta", "LCA": "Larnaca",
    "TLV": "Tel Aviv", "MEX": "Ciudad de México", "HAV": "Havana", "DPS": "Bali (Denpasar)", "MLE": "Malé (Maldive)",
    "SEZ": "Mahé (Seychelles)", "RUN": "Saint-Denis (Réunion)", "SGN": "Ho Chi Minh", "RAK": "Marrakech", "TNG": "Tanger",
    "ALG": "Alger", "SAO": "São Paulo", "BOG": "Bogotá", "SCL": "Santiago de Chile", "PTY": "Panama", "SJO": "San José (Costa Rica)",
    "SJC": "San Jose (California)", "CUN": "Cancún", "GOT": "Göteborg", "CAI": "Cairo", "MLA": "Malta", "SXF": "Berlin",
}

# același oraș, aeroporturi diferite -> un singur oraș (la gruparea „o variantă pe oraș”)
CITY_OF = {
    "SPX": "CAI", "TSF": "VCE", "CIA": "FCO", "LTN": "LON", "STN": "LON", "LGW": "LON", "LHR": "LON", "BVA": "PAR",
    "ORY": "PAR", "CDG": "PAR", "WMI": "WAW", "CRL": "BRU", "NYO": "STO", "ARN": "STO", "BMA": "STO", "TRF": "OSL",
    "DMK": "BKK", "HND": "TYO", "NRT": "TYO", "PEK": "BJS", "PKX": "BJS", "ICN": "SEL", "GYD": "BAK", "SAW": "IST",
    "BGY": "MIL", "MXP": "MIL", "LIN": "MIL", "SVO": "MOW", "DME": "MOW", "VKO": "MOW", "KIV": "RMO",
}

COUNTRY = {
    "North Korea": "Coreea de Nord", "South Korea": "Coreea de Sud", "China": "China", "India": "India", "Indonesia": "Indonezia",
    "Philippines": "Filipine", "Vietnam": "Vietnam", "Malaysia": "Malaezia", "Singapore": "Singapore", "Sri Lanka": "Sri Lanka",
    "Nepal": "Nepal", "Cape Verde": "Capul Verde", "Dominican Republic": "Republica Dominicană", "Kyrgyzstan": "Kârgâzstan",
    "Tajikistan": "Tadjikistan", "Turkmenistan": "Turkmenistan", "Mongolia": "Mongolia", "Brazil": "Brazilia",
    "Argentina": "Argentina", "Chile": "Chile", "Colombia": "Columbia", "Peru": "Peru", "Mexico": "Mexic", "Cuba": "Cuba",
    "Jamaica": "Jamaica", "Bahamas": "Bahamas", "Barbados": "Barbados", "Costa Rica": "Costa Rica", "Panama": "Panama",
    "Guatemala": "Guatemala", "El Salvador": "El Salvador", "Venezuela": "Venezuela", "Bolivia": "Bolivia",
    "Paraguay": "Paraguay", "Uruguay": "Uruguay", "Ecuador": "Ecuador", "Kenya": "Kenya", "Tanzania": "Tanzania",
    "South Africa": "Africa de Sud", "Ethiopia": "Etiopia", "Nigeria": "Nigeria", "Ghana": "Ghana", "Rwanda": "Rwanda",
    "Madagascar": "Madagascar", "Mauritius": "Mauritius", "Seychelles": "Seychelles", "Réunion": "Réunion", "Iran": "Iran",
    "Iraq": "Irak", "Pakistan": "Pakistan", "Bangladesh": "Bangladesh", "Australia": "Australia",
    "New Zealand": "Noua Zeelandă", "Fiji": "Fiji", "Algeria": "Algeria", "Russia": "Rusia", "Belarus": "Belarus",
    "Taiwan": "Taiwan", "Hong Kong": "Hong Kong", "Equatorial Guinea": "Guineea Ecuatorială", "Sierra Leone": "Sierra Leone",
    "Botswana": "Botswana", "Mauritania": "Mauritania", "Papua New Guinea": "Papua Noua Guinee", "Puerto Rico": "Puerto Rico",
    "U.S. Virgin Islands": "Insulele Virgine Americane", "British Virgin Islands": "Insulele Virgine Britanice",
    "Cayman Islands": "Insulele Cayman", "Curaçao": "Curaçao", "Guadeloupe": "Guadelupa", "Martinique": "Martinica",
    "Afghanistan": "Afganistan", "Syria": "Siria", "Yemen": "Yemen", "Libya": "Libia", "Sudan": "Sudan",
}


def city(code, name):
    return CITY.get(code) or name
