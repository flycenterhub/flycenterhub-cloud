"""Regiuni în afara Europei (pentru tab-ul „Exotice”)."""
import re

REGION_LABELS = {
    "asia": "Asia",
    "insule": "Insule exotice (Oceanul Indian)",
    "orient": "Orientul Mijlociu & Caucaz",
    "africa": "Africa",
    "america_n": "America de Nord",
    "caraibe": "Caraibe & America Centrală",
    "america_s": "America de Sud",
    "oceania": "Oceania & Pacific",
}

_BY_REGION = {
    "asia": "TH VN KH LA MM MY SG ID PH BN TL CN HK MO TW JP KR KP MN IN LK NP BT BD PK AF UZ KZ KG TJ TM",
    "insule": "MV MU SC RE YT KM MG",
    "orient": "AE QA OM BH KW SA JO IL LB IQ IR YE SY PS GE AM AZ",
    "africa": "EG MA TN DZ LY SD KE TZ UG RW BI ET ER DJ SO ZA NA BW ZW ZM MZ MW LS SZ AO CD CG GA CM NG GH CI SN GM "
              "GN SL LR ML BF NE TD CF BJ TG CV ST GQ MR SS",
    "america_n": "US CA MX GL",
    "caraibe": "CU DO JM BS BB TT PR AW CW SX BQ LC AG KN DM GD VC KY TC GP MQ BL MF HT VG VI AI MS CR PA GT BZ HN NI SV",
    "america_s": "BR AR CL PE CO EC BO PY UY VE GY SR GF FK",
    "oceania": "AU NZ FJ PF NC PG WS TO VU SB KI FM MH PW GU MP CK NU",
}
CC_REGION = {cc: r for r, ccs in _BY_REGION.items() for cc in ccs.split()}

# Aeroporturi care merită altă categorie decât țara lor
AIRPORT_REGION = {"ZNZ": "insule", "PBH": "asia"}

# Rezervă când nu avem codul țării (nume în engleză, cum vin de la surse)
NAME_CC = {
    "Thailand": "TH", "Vietnam": "VN", "Viet Nam": "VN", "Cambodia": "KH", "Laos": "LA", "Myanmar": "MM",
    "Malaysia": "MY", "Singapore": "SG", "Indonesia": "ID", "Philippines": "PH", "China": "CN", "Hong Kong": "HK",
    "Taiwan": "TW", "Japan": "JP", "South Korea": "KR", "Korea": "KR", "Mongolia": "MN", "India": "IN",
    "Sri Lanka": "LK", "Nepal": "NP", "Bangladesh": "BD", "Pakistan": "PK", "Uzbekistan": "UZ",
    "Kazakhstan": "KZ", "Kyrgyzstan": "KG", "Tajikistan": "TJ", "Turkmenistan": "TM",
    "Maldives": "MV", "Mauritius": "MU", "Seychelles": "SC", "Reunion": "RE", "Réunion": "RE", "Madagascar": "MG",
    "United Arab Emirates": "AE", "Qatar": "QA", "Oman": "OM", "Bahrain": "BH", "Kuwait": "KW",
    "Saudi Arabia": "SA", "Jordan": "JO", "Israel": "IL", "Lebanon": "LB", "Iraq": "IQ", "Iran": "IR",
    "Georgia": "GE", "Armenia": "AM", "Azerbaijan": "AZ",
    "Egypt": "EG", "Morocco": "MA", "Tunisia": "TN", "Algeria": "DZ", "Kenya": "KE", "Tanzania": "TZ",
    "Uganda": "UG", "Rwanda": "RW", "Ethiopia": "ET", "South Africa": "ZA", "Namibia": "NA", "Nigeria": "NG",
    "Ghana": "GH", "Senegal": "SN", "Cape Verde": "CV", "Gambia": "GM",
    "United States": "US", "USA": "US", "Canada": "CA", "Mexico": "MX",
    "Cuba": "CU", "Dominican Republic": "DO", "Jamaica": "JM", "Bahamas": "BS", "Barbados": "BB",
    "Costa Rica": "CR", "Panama": "PA", "Guatemala": "GT",
    "Brazil": "BR", "Argentina": "AR", "Chile": "CL", "Peru": "PE", "Colombia": "CO", "Ecuador": "EC",
    "Australia": "AU", "New Zealand": "NZ", "Fiji": "FJ", "French Polynesia": "PF",
}


def region_of(code, cc=None, country=None):
    if code in AIRPORT_REGION:
        return AIRPORT_REGION[code]
    cc = (cc or NAME_CC.get(country or "") or "").upper()
    return CC_REGION.get(cc)


# Cuvinte care indică o destinație exotică într-un articol (RO / EN / HU / PL / DE)
EXOTIC_WORDS = [
    r"thail|tajland|thaif[öo]ld|bangkok|phuket|krabi|koh |ko samui|chiang",
    r"vietn|wietnam|hanoi|ho chi minh|saigon|da nang|phu quoc",
    r"zanzib|sansibar|mauritius|maurit|maldiv|malediv|seychel|seszel|sri lanka|srí lanka|madagas",
    r"bali\b|indonez|indones|jakarta|singap|szingap|malaysi|malezj|malajzi|kuala lumpur|philippin|filipin|fülöp|manil",
    r"\bchin[ae]\b|\bkína|\bchiny|peking|beijing|shanghai|sanghaj|szanghaj|hong ?kong|guangzhou|chengdu|taiwan|tajwan|tajvan",
    r"japan|japon|jap[aá]n|tokyo|tokio|osaka|oszaka|kyoto|korea|seoul|szöul|seul",
    r"\bindia|\bindii|\bindi[aá]\b|goa\b|delhi|mumbai|nepal|kathmandu|cambod|kambodzs|kambodż|laos|myanmar|uzbek|kazah|kazach|almaty",
    r"\bazja|\bazji|\basia\b|\basien\b|[áa]zsi[aá]|\bafrica|\bafryk|\bafrika|kenya|kenia|tanzan|uganda|entebbe|nairobi|cape town|fokváros|kapstadt|namib",
    r"mexic|meksyk|mexikó|mexiko|cancun|kuba|\bcuba|dominica|dominikan|punta cana|jamaica|jamajka|karaib|caribb|karib",
    r"brazil|brazyl|brazília|brasil|argentin|peru\b|colombia|kolumbi|chile\b|new york|nowy jork|miami|los angeles|\busa\b|\bsua\b|kalifornia|california",
    r"australi|ausztrália|nowa zelandia|new zealand|új-zéland|fidżi|fiji|tahiti|hawaii|hawaj",
    r"dubai|dubaj|abu dhabi|abu zabi|katar|qatar|doha|oman|muscat|maszkat|jordan|iordania|egipt|egypt|hurghada|sharm|marrakech|marrakesz|marokk|maroc|tunez|tunisz|tunisia",
]
EXOTIC_RX = re.compile("|".join(EXOTIC_WORDS), re.I)


def is_exotic_text(text):
    return bool(EXOTIC_RX.search(text or ""))
