"""Poze cu orașele de destinație, de pe Wikimedia Commons (libere, gratuite, fără cont).

Aeroport (cod IATA) → orașul deservit (Wikidata P931) → poza orașului (P18) sau bannerul Wikivoyage (P948).
Se actualizează după scanări doar pentru destinațiile noi; rezultatul stă în kv „photos”: {cod: [fișier, sursă]}.
"""
import json
import logging
import os
import re
import urllib.parse

from . import net

log = logging.getLogger("photos")

SPARQL = "https://query.wikidata.org/sparql"
UA = {"User-Agent": "FlyCenterHub/1.0 (https://flycenterhub.github.io/)", "Accept": "application/sparql-results+json"}
BAD = re.compile(r"map|karte|carte|satellite|landsat|nasa|locator|location|flag|coat.of.arms|wappen|logo|"
                 r"collage|montage|montaje|montagem|composite|mosaic|compilation|kola[zž]|\.svg$|\.png$|\.gif$|\.tif", re.I)


def _query(codes, want=None):
    want = want or {}
    vals = " ".join(f'"{c}"' for c in codes)
    q = f"""SELECT ?iata ?img ?banner ?cc WHERE {{
      VALUES ?iata {{ {vals} }}
      ?a wdt:P238 ?iata .
      OPTIONAL {{ ?a wdt:P931 ?city . OPTIONAL {{ ?city wdt:P18 ?img }} OPTIONAL {{ ?city wdt:P948 ?banner }}
                 OPTIONAL {{ ?city wdt:P17/wdt:P297 ?cc }} }}
    }}"""
    data = net.get_json(f"{SPARQL}?format=json&query={urllib.parse.quote(q)}", headers=UA, timeout=90)
    out = {}
    for b in data["results"]["bindings"]:
        code = b["iata"]["value"]
        if want.get(code) and "cc" in b and b["cc"]["value"].upper() != want[code].upper():
            continue  # orașul „deservit” e în altă țară decât aeroportul: legătură greșită pe Wikidata
        for key in ("img", "banner"):
            if key in b:
                f = urllib.parse.unquote(b[key]["value"].rsplit("/", 1)[-1]).replace(" ", "_")
                if not BAD.search(f):
                    rank = ("img", "banner").index(key)
                    if code not in out or rank < out[code][1]:
                        out[code] = (f, rank)
    return {c: f for c, (f, _) in out.items()}


def _by_name(names):
    """Rezervă: numele orașului → articolul Wikipedia → Wikidata → poza (pentru coduri de oraș: NYC, ROM...)."""
    clean = {c: re.sub(r"\s*\(.*?\)|(airport|all airports|international)", "", n, flags=re.I).strip()
             for c, n in names.items() if n}
    out = {}
    items = list(clean.items())
    for i in range(0, len(items), 40):
        part = dict(items[i:i + 40])
        q = urllib.parse.quote("|".join(sorted(set(part.values()))))
        d = net.get_json(f"https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1&prop=pageprops"
                         f"&ppprop=wikibase_item&titles={q}", headers=UA)["query"]
        alias = {x["from"]: x["to"] for x in d.get("normalized", []) + d.get("redirects", [])}
        qid = {p["title"]: p.get("pageprops", {}).get("wikibase_item") for p in d.get("pages", {}).values()}
        ids = sorted({v for v in qid.values() if v})
        if not ids:
            continue
        ents = net.get_json("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=claims&ids="
                            + "|".join(ids), headers=UA)["entities"]
        for code, name in part.items():
            t = alias.get(alias.get(name, name), alias.get(name, name))
            claims = (ents.get(qid.get(t) or "", {}) or {}).get("claims", {})
            for prop in ("P18", "P948"):
                try:
                    f = claims[prop][0]["mainsnak"]["datavalue"]["value"].replace(" ", "_")
                except (KeyError, IndexError):
                    continue
                if not BAD.search(f):
                    out[code] = f
                    break
    return out


def url(file, width=640):
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(file)}?width={width}"


def refresh(db, force=False):
    """Caută poze pentru destinațiile care nu au încă. Întoarce câte s-au găsit acum."""
    import os
    if os.environ.get("FCH_CLOUD"):
        sync_from_site(db)
    have = {} if force else (db.get_kv("photos") or {})
    tried = set() if force else set(db.get_kv("photos_tried") or [])
    codes = sorted({r["dest"] for r in db.q("SELECT DISTINCT dest FROM fares")} - set(have) - tried)
    ccs = {p["code"]: p["cc"] for p in db.q("SELECT code, cc FROM places")}
    found = 0
    for i in range(0, len(codes), 150):
        part = codes[i:i + 150]
        try:
            res = _query(part, ccs)
        except Exception as e:
            log.warning("Poze Wikidata: %s", e)
            break
        have.update(res)
        found += len(res)
        tried.update(set(part) - set(res))
    missing = [c for c in codes if c not in have]
    if missing:
        names = {p["code"]: p["name"] for p in db.q("SELECT code, name FROM places")}
        try:
            res = _by_name({c: names.get(c) for c in missing})
            have.update(res)
            found += len(res)
            tried.difference_update(res)
        except Exception as e:
            log.warning("Poze după nume: %s", e)
    db.set_kv("photos", have)
    db.set_kv("photos_tried", sorted(tried))
    if codes:
        log.info("Poze destinații: %s noi (%s în total)", found, len(have))
    return found


# Poze emblematice, alese pentru fiecare destinație (monumentul/simbolul orașului) și verificate vizual.
# Au prioritate față de poza găsită automat; o destinație nouă, care nu e aici, primește poza orașului.
EMBLEMATIC = {
    'AAL': 'Aalborg_NyTorv_2004_ubt.jpeg', 'AAR': 'ARoS_"Your_rainbow"_panorama_under_construction.jpg', 'ABA': 'Abakan_017.jpg',
    'ABZ': 'Marischal_College_A.JPG', 'ACC': 'Accra_town.jpg', 'ACE': '2008-12-19_Lanzarote_Timanfaya.jpg',
    'AER': 'Sochi_adler_aerial_view_2018_14.jpg', 'AES': 'Il_giocattolo_-_panoramio.jpg', 'AEY': 'Akureyri-08-Panorama-2018-gje.jpg',
    'AGA': 'Agadir_Areal_view_cropped.jpg', 'AGH': 'Helsingborg_Kaernan.jpg', 'AGP': 'Alcazaba_de_Málaga_overview.jpg',
    'AGR': 'Taj_Mahal_(Edited).jpeg', 'AGX': 'Bangaram_Island,_Lakshadweep_20160325-_DSC1780.jpg', 'AHO': 'Alghero_-_Panorama_(02).jpg',
    'AIT': 'Aitutaki-Motu_Tapuaetai.jpg', 'AKL': 'Auckland_CBD.jpg', 'AKX': 'Nurdaulet_mosque_1.jpg',
    'ALA': '13_Вид_на_Алма-Ату_с_горы_Кок_Тюбе.jpg', 'ALC': 'Alicante_Castillo_de_Santa_Bárbara_01.jpg', 'ALG': 'Argel_3.jpg',
    'ALY': 'Bibliotheca_Alexandrina_(Alexandrie_bibliothèque).jpg', 'AMM': 'Amman_Citadel.jpg', 'AMS': 'Rijksmuseum_in_Amsterdam.jpg',
    'ANC': 'Anchorage_on_an_April_evening.jpg', 'ANK': 'Ankara_asv2021-10_img04_Anıtkabir.jpg', 'ANR': 'Antwerpen_Centraal_station_12-07-2010_14-04-17.JPG',
    'AOI': 'Cattedrale_di_San_Ciriaco_(Ancona).JPG', 'AOK': 'Pigadia.jpg', 'AQJ': 'The_Treasury,_Petra,_Jordan5.jpg',
    'ARH': 'Arkhangelsk_view_from_Vysotka.jpg', 'ARN': 'Gamla_stan_February_2013_01.jpg', 'ARW': 'Arad,_Romania_-_Administrative_Palace_(2023).jpg',
    'ASB': 'Neutrality-Road-Ashgabat-2015.JPG', 'ASF': 'Tortures_tower_in_Astrakhan_Kremlin.jpg', 'ASW': 'Großer_Tempel_(Abu_Simbel)_31.jpg',
    'ATH': 'Attica_06-13_Athens_50_View_from_Philopappos_-_Acropolis_Hill.jpg', 'ATL': 'A2ATL20250614-0721_(cropped).jpg', 'ATQ': 'Hamandir_Sahib_(Golden_Temple).jpg',
    'AUA': 'Dutch_Buildings,_Oranjestad_(4901401297).jpg', 'AUH': 'Sheikh_Zayed_Mosque_Silhouette.jpg', 'AYT': 'Antalya_Kaleiçi.jpg',
    'BAH': 'Bahrain_World_trade_Center_.jpg', 'BAK': 'View_From_Maidens_Tower_(221090097).jpeg', 'BAX': 'Barnaul_(2021)-1.jpeg',
    'BAY': 'Rivulus_Dominarum.jpg', 'BBU': 'Ateneo_Rumano,_Bucarest,_Rumanía,_2016-05-29,_DD_73.jpg', 'BCM': 'Prefectura_Bacau.jpg',
    'BCN': 'SF_maig_2026.jpg', 'BDS': 'Cathédrale_de_Brindisi.JPG', 'BEG': 'Church_of_Saint_Sava_4.jpg',
    'BER': 'Brandenburger_Tor_morgens.jpg', 'BES': 'Brest_-_Le_Château_-_PA00089847_-_011.JPG', 'BEY': 'Beirutcity.jpg',
    'BFS': 'Titanic_Belfast_side_view.jpg', 'BGI': 'Carlisle_Bay_Beach.jpeg', 'BGO': 'Bryggen,_Bergen3.JPG',
    'BGY': '20110724_Milan_Cathedral_5260.jpg', 'BHK': 'Poi_Kalon.jpg', 'BHX': 'Birmingham-Skyline-from-Edgbaston-crop.jpg',
    'BIO': 'Museo_Guggenheim,_Bilbao_(31273245344).jpg', 'BIQ': 'Biarritz-Plage.JPG', 'BJS': 'Hall_of_Supreme_Harmony_(20241127120000).jpg',
    'BJV': 'Bodrum_Castle_(2017).jpg', 'BJX': 'León_Guanajuato_banner.jpg', 'BKK': 'Wat_Arun_from_Chao_Phraya_River.jpg',
    'BLA': 'Parque_Nacional_mochima.jpg', 'BLL': 'LegoBillundTowerView.jpg', 'BLQ': '2tours_bologne_082005.jpg',
    'BLR': 'BLR_palace_main_entrance.jpg', 'BNE': 'Skyline_of_Brisbane_from_Kangaroo_Point_Cliffs_Park,_Nov_2020,_05.jpg', 'BNX': 'NKD115_Saborna_crkva_Hrista_spasitelja_Banja_Luka_RS_BiH.jpg',
    'BOB': 'Aéroport_de_Bora_Bora.jpg', 'BOD': "139_-_Place_de_la_Bourse_et_le_miroir_d'eau_-_Bordeaux.jpg", 'BOG': 'Centro_internacional.JPG',
    'BOM': 'Mumbai_03-2016_30_Gateway_of_India.jpg', 'BON': 'Crystal_Clear_waters_of_Bonaire_(13256547653).jpg', 'BOO': 'Bodø_2006.jpg',
    'BOS': 'Boston_from_the_Harbour,_Massachusetts_(493360)_(10772382303).jpg', 'BQT': 'BrestFortress7.JPG', 'BRE': 'RathausDomBuergerschaft-01.jpg',
    'BRI': 'Bari_BW_2016-10-19_13-35-11_stitch.jpg', 'BRN': 'Zytglogge_01.jpg', 'BRQ': 'Brno,_Štýřice,_Pražákova,_výhled_z_AZ_Toweru_(2013-05-22;_28).jpg',
    'BRS': 'Clifton_Suspension_Bridge-9350.jpg', 'BRU': 'Laeken_Atomium_06.jpg', 'BSL': 'Basler_-_Basler_Münster_Westfassade.jpg',
    'BSZ': 'Ala_Archa_1.JPG', 'BTS': 'Bratislava_-_Burg_(a).JPG', 'BUD': 'Budapest-Parliament-0001.jpg',
    'BUE': 'ObeliscoBA2015.jpg', 'BUH': 'Ateneo_Rumano,_Bucarest,_Rumanía,_2016-05-29,_DD_73.jpg', 'BUS': 'Batumi_Georgia_2012.jpg',
    'BVA': 'Tour_Eiffel_Wikimedia_Commons.jpg', 'BVC': 'Esporte_sobre_rio_em_Boa_Vista-RR.jpg', 'BWI': 'Inner_Harbor_from_the_Baltimore_Aquarium.jpg',
    'BWK': 'Bol_(33626391504).jpg', 'BZG': 'Stary_Rynek_w_Bydgoszczy_edit.jpg', 'BZO': 'TalferbrueckeBozenMeranBahn.jpg',
    'CAG': 'Cagliari_kathedrale_fassade01.jpg', 'CAI': 'Pyramids_of_the_Giza_Necropolis.jpg', 'CAN': '广州塔Scenery_in_Guangzhou,_China_-_panoramio_(9).jpg',
    'CAY': 'Cayenne_av_Général-de-Gaulle.jpg', 'CBR': 'Parliament_House_at_dusk,_Canberra_ACT.jpg', 'CCU': 'Victoria_Memorial_situated_in_Kolkata.jpg',
    'CDG': 'Tour_Eiffel_Wikimedia_Commons.jpg', 'CDT': 'Valencia,_Ciudad_de_las_Ciencias_y_de_las_Artes.jpg', 'CEB': "Magellan's_Cross_in_Cebu.jpg",
    'CEK': 'Кировка.jpg', 'CFR': 'Façade_sud_du_château_de_Caen.JPG', 'CFU': 'The_Old_Fortress_and_the_Old_Town_of_Corfu_-_September_2017.jpg',
    'CGK': 'Around_Monas_Jakarta_(2025)_(cropped).jpg', 'CGN': 'Kölner_Dom_von_Osten.jpg', 'CGY': 'CDO_CM_Recto-Corrales_skyline_alt_(Cagayan_De_Oro_City;_12-08-2023).jpg',
    'CHC': 'Christchurch_City.jpg', 'CHI': 'A_public_square_in_Chicago_(9326033069).jpg', 'CHQ': 'Aerial_view_of_the_Old_Venetian_Harbour_in_Chania,_Greece.jpg',
    'CIA': 'Colosseo_2020.jpg', 'CIT': 'Shymkent_independence_square_in_2023.jpg', 'CKG': 'Hongya_Cave_20180520.jpg',
    'CKZ': 'Troy1.jpg', 'CLJ': 'St_Michael_Cluj_Napoca.jpg', 'CLO': 'Panorámica_nocturna_de_Cali_2023.jpg',
    'CMB': 'Blue_lotus_tower.jpg', 'CMN': "Sunshine_on_mosque_Hassan_II_in_Casablanca,_Morocco_-_Flickr_-_Milamber's_portfolio.jpg", 'CND': 'Constanța_Casino_2025_(54606449888).jpg',
    'CNN': 'Kannur_Skyline_3.jpg', 'COK': 'Chinese_Fishing_Net_Raising_Birds_Sunrise_Ashtamudi_Kollam_Mar22_A7C_01784.jpg', 'COV': 'Mersin_banner_Cycling_event_during_the_Mediterranean_Games.jpg',
    'CPH': 'Nyhavn_Copenhagen_2.jpg', 'CPT': 'Table_Mountain_DanieVDM.jpg', 'CRA': 'Parcul_Nicolae_Romanescu_-_podul_suspendat_2.jpg',
    'CRL': 'Grand-Place,_Brussels_-_panorama,_June_2018.jpg', 'CSY': 'Cheboksary._View_of_downtown.jpg', 'CTA': 'View_of_Mount_Etna_from_Reggio_Calabria_-_Italy_-_10_Feb._2017_-_(1).jpg',
    'CTG': 'View_of_Cartagena_from_Convento_de_Santa_Cruz_de_la_Popa_01.jpg', 'CTU': 'Chengdu_Research_Base_Eingang.jpg', 'CUF': 'PiazzaGalimberti-Cuneo1.jpg',
    'CUN': 'Cancún_banner_Praia_Delfines.jpg', 'CUR': 'Handelskade_in_Willemstad.jpg', 'CUZ': '80_-_Machu_Picchu_-_Juin_2009_-_edit.jpg',
    'CVG': 'Cincinnati_Skyline_from_Devou_Park.jpg', 'DAC': 'বাংলাদেশের_জাতীয়_সংসদ_ভবন_16.jpg', 'DAD': 'The_Golden_Bridge,_Ba_Na_Hills,_Vietnam.jpg',
    'DAR': 'Dar_es_Salaam_before_dusk.jpg', 'DAY': 'Dayton_banner_skyline.jpg', 'DBV': 'Porporela_2011.jpg',
    'DEB': 'Debrecen_-_Protestant_Great_Church.JPG', 'DED': 'Panoramic_view_of_Mussoorie,_Uttarakhand.jpg', 'DEL': 'India_Gate_in_New_Delhi_03-2016.jpg',
    'DFW': 'Dallas_Skyline_with_Arts_District.jpg', 'DJE': 'Houmt_Souk_May_2007.JPG', 'DLM': 'Oludeniz.jpg',
    'DND': 'Discovery_and_the_V^A_-_geograph.org.uk_-_7342982.jpg', 'DNZ': 'Pamukkale,_Denizli_2026_68.jpg', 'DOD': 'Scene_at_Nyerere_Square,_Dodoma_City.jpg',
    'DOH': 'IslamicArtMuseumDohaSkyline.jpg', 'DOM': 'Rainforest_at_Trafalgar_Falls_(Dominica).jpg', 'DPS': 'Bali_-_Pura_Tanah_Lot,_20220827_1005_1141.jpg',
    'DRS': '100130_150006_Dresden_Frauenkirche_winter_blue_sky-2.jpg', 'DTM': 'Union-Brauerei_Dortmund.jpg', 'DTT': 'Renaissance_Center_(23_April_2017).jpg',
    'DUB': 'HalfPennyBridge.jpg', 'DUS': 'Düsseldorf_Panorama.jpg', 'DXB': 'Dubai_skyline_2015_(crop).jpg',
    'DYG': 'Yangjiajie.jpg', 'DYU': 'Tehron_Street_Dushanbe.jpg', 'EAP': 'Basler_-_Basler_Münster_Westfassade.jpg',
    'EBB': 'Getting_out_to_fish_at_dusk.jpg', 'EBL': 'Hawler_Castle.jpg', 'ECN': 'Kyrenia_01-2017_img04_view_from_castle_bastion.jpg',
    'EDI': 'Edinburgh_Castle_from_the_Grassmarket.jpg', 'EFL': 'Myrtos_Beach,_Kefalonia.jpg', 'EIN': 'Overzicht_-_Eindhoven_-_20396820_-_RCE.jpg',
    'EMA': 'Nottingham_Castle_Gate_2009.jpg', 'ENI': 'El_Nido_Palawan_2.jpg', 'ERF': 'Erfurt_Dom_Domtreppe_Severikirche_small.jpg',
    'ESB': 'Ankara_asv2021-10_img04_Anıtkabir.jpg', 'ETZ': 'Cathedrale-saint-etienne-metz-de-place-prefecture.jpg', 'EVN': '2014_Erywań,_Park_przy_Kaskadach_(17).jpg',
    'EXT': 'Exeter_Cathedral_2923rw.jpg', 'EZE': 'ObeliscoBA2015.jpg', 'EZS': 'Elazığ_City_Center.jpg',
    'FAE': 'Gasadalur,_Faroe_Islands_5.jpg', 'FAO': 'Ponta_da_Piedade_(Portugal)_(49079280062).jpg', 'FCO': 'Colosseo_2020.jpg',
    'FDF': 'Fort-de-france-harbor.jpg', 'FDH': 'Meersburg_panor2.jpg', 'FEG': 'Фергана_аллея.jpg',
    'FIH': 'Vue_Kinshasa.jpg', 'FKB': 'Baden-Baden_10-2015_img24_Stiftskirche.jpg', 'FLL': 'Skyline_of_Fort_Lauderdale,_Nov-15.jpg',
    'FLN': 'Floripa_Beira_Mar_Norte.jpg', 'FLR': 'Florence_Duomo_from_Michelangelo_hill.jpg', 'FLW': 'Ponta_do_Albernaz_Flores_Azores.JPG',
    'FMM': 'Schloss_Neuschwanstein_2013.jpg', 'FMO': 'Muenster-100725-16079-Lamberti.jpg', 'FNC': 'Madeira_19_2014.jpg',
    'FNI': 'Maison_Carree_in_Nimes_(16).jpg', 'FNJ': 'Panoramic_view_from_Juche_Tower.jpg', 'FOG': 'Piazza_Camillo_Benso_conte_di_Cavour.jpg',
    'FRA': 'Frankfurter_Altstadt_mit_Skyline_2019_(100MP).jpg', 'FRL': 'Palazzo_comunale_di_Forlì.jpg', 'FUE': 'Fuerteventura_banner.jpg',
    'FUK': 'Hakata_Port_from_Fukuoka_Tower.jpg', 'GDN': 'Monumento_Neptuno,_Gdansk,_Polonia,_2013-05-20,_DD_03.jpg', 'GEO': "St_George's_Cathedral.jpg",
    'GHV': 'Brasov,_Piata_Sfatului.jpg', 'GIG': 'Pão_de_Açucar_-_Sugarloaf_Mountain_-_Zuckerhut_-_2022.jpg', 'GLA': 'Glasgow_-_aerial_-_2025-04-17_12.jpg',
    'GME': 'DJI_0137_Edit_(51152843462).jpg', 'GNJ': 'Banner_Ganja_004_4664.jpg', 'GNO': 'Grenoble_01.JPG',
    'GOA': 'Genova_panorama_centro_storico_da_villetta_Di_Negro.jpg', 'GOH': 'Nuuk-port.jpg', 'GOI': 'Palolem_beach.jpg',
    'GOJ': 'Вид_на_Нижегородский_кремль_с_высоты_cropped.jpg', 'GOT': 'Göteborg_2503_stitch_(28573994096).jpg', 'GPA': 'C2.35_Ríobrücke.jpg',
    'GPS': 'Galapagos_Geochelone_nigra_porteri.jpg', 'GRO': 'Girona_Cathedral_2020.jpg', 'GRQ': 'Martini_Toren.JPG',
    'GRR': 'Downtown_Grand_Rapids_from_River_House.jpg', 'GRU': 'Sao_Paulo_Skyline_in_Brazil.jpg', 'GRV': 'Грозный_мечеть_2011.JPG',
    'GRX': 'Alhambra_detail.jpg', 'GRZ': '16-07-06-Rathaus_Graz_Turmblick-RR2_0275.jpg', 'GUA': 'Santa_Catalina_Arch_-_Antigua_Guatemala_Feb_2020.jpg',
    'GUW': 'Ural_River_Atyrau.JPG', 'GVA': 'Geneva_from_Mount_Salève.jpg', 'GYD': 'View_From_Maidens_Tower_(221090097).jpeg',
    'GZP': 'Alanya_kale.jpg', 'GZT': 'Zeugma_museum.jpg', 'HAJ': 'Neues_Rathaus_Hannover_2013.jpg',
    'HAK': 'Haikou_skyline_6_-_2009_09_07.jpg', 'HAM': '2019-05-10_Elbphilharmonie_Hamburg.jpg', 'HAN': 'Ho_Hoan_Kiem_(13574475044).jpg',
    'HAV': 'Cuba_libre_(6941395159).jpg', 'HBA': 'Franklin_Wharf_2015.jpg', 'HDO': 'India_Gate_in_New_Delhi_03-2016.jpg',
    'HDY': 'Hatyaicity1.jpg', 'HEL': 'Lutheran_Cathedral_Helsinki.jpg', 'HER': 'Knossos_-_North_Portico_02.jpg',
    'HFA': 'Shrine_Bab_North_West.jpg', 'HGH': 'West_Lake_-_Hangzhou,_China.jpg', 'HHN': 'Frankfurter_Altstadt_mit_Skyline_2019_(100MP).jpg',
    'HKG': 'HK_YTM_西九龍文化區_West_Kowloon_Cultural_District_M+_Plus_Museum_天台花園_roof_garden_view_Victoria_Harbour_July_2022_Px3_13.jpg', 'HKT': 'Flickr_-_Shinrya_-_Paradise_in_Phuket.jpg', 'HND': 'Tokyo_Tower_2023.jpg',
    'HNL': 'Diamond_Head_Kapiolani_Park.jpg', 'HOU': 'Houston_night.jpg', 'HRE': 'Harare_skyline.jpg',
    'HRG': 'Hurghada_Hotels_R03.jpg', 'HTA': 'Views_of_Chita_from_Titovskaya_Hill_(2026-06-10)_-_0.jpg', 'HVG': 'Cabo_Norte,_Noruega,_2019-09-03,_DD_16.jpg',
    'HYD': 'Charminar-Pride_of_Hyderabad.jpg', 'IAD': 'United_States_Capitol_west_front_edit2.jpg', 'IAH': 'Houston_night.jpg',
    'IAS': 'Exposing_Online_the_European_Cultural_Heritage_The_impact_of_Cultural_Heritage_on_the_Digital_Transformation_of_The_Society_(32746944817).jpg', 'IBZ': 'Ibiza_City_from_Mirador_asv2023-04_img1.jpg', 'ICN': '광화문_월대.jpg',
    'IEG': 'Ratuwiw21.jpg', 'IGT': 'Магас_(Magas).jpg', 'IJK': 'Aerial_photographs_of_Izhevsk-108.jpg',
    'IKT': 'Olkhon_Island_and_Lake_Baikal.jpg', 'INI': 'Niš_Fortress,_Niš,_Serbia.jpg', 'INN': 'Goldenes_Dachl_(Innsbruck).jpg',
    'INU': 'Coral_reef_on_Nauru.jpg', 'IOA': 'Κάστρο_Ιωαννίνων,_άποψη_του_τζαμιού_με_φόντο_την_λίμνη_τον_ουρανό_και_τους_γλάρους!!!(photosiotas)_(5).jpg', 'IST': 'Hagia_Sophia_Mars_2013.jpg',
    'ISU': 'Sulaymaniyah1.jpg', 'ITM': 'Osaka_Castle_02bs3200.jpg', 'ITO': 'Lava-streaming-into-ocean.jpg',
    'IVL': 'BoatInari1.jpg', 'IZM': 'Izmir_square_clock_tower.jpg', 'JDH': 'Mehrangarh_Fort.jpg',
    'JED': 'AlBalad_CoralHouses.JPG', 'JFK': 'Statue_of_Liberty_and_a_sightseeing_boat,_Liberty_Island,_New_York.jpg', 'JKH': 'Chios_Banner.jpg',
    'JKL': 'Kalymnos.JPG', 'JKT': 'Around_Monas_Jakarta_(2025)_(cropped).jpg', 'JMK': 'Little_Venice_with_a_view_of_the_ferry_terminal_in_Mykonos,_Greece_-_50661522178.jpg',
    'JNB': 'Johannesburg_CBD.jpg', 'JNX': 'Naxos-port.JPG', 'JOG': 'Borobudur-Nothwest-view.jpg',
    'JRO': 'Mount_Kilimanjaro_Dec_2009_edit1.jpg', 'JSI': 'Skiathos_wisnia6522.jpg', 'JTR': 'Greece_Santorini_Oia_Coast_by_day.JPG',
    'KAJ': 'Karolineburgin_kartano.jpg', 'KAO': 'Kuusamo_keskusta.JPG', 'KBL': 'Kabul_TV_Hill_view.jpg',
    'KBV': 'Railay.jpg', 'KEF': 'Hallgrimskirkja_mai_2026.jpg', 'KEJ': 'Kemerovo_City_Council.jpg',
    'KEM': 'Kemi_Church_20220421.jpg', 'KGD': 'Kaliningrad_05-2017_img04_Kant_Island.jpg', 'KGF': 'Караганда_проспект.JPG',
    'KGL': 'Kigali2018Cropped.jpg', 'KGS': 'Kos_seaport.jpg', 'KHH': 'Kaohsiung_Skyline_2020.jpg',
    'KIN': 'PortofKingston.jpg', 'KIX': 'Osaka_Castle_02bs3200.jpg', 'KJA': 'Aerial_view_of_Krasnoyarsk_1.jpg',
    'KKN': 'Kirkenes,_with_a_foggy_Varangerfjord.jpg', 'KLU': 'Aerial_image_of_Wörthersee_(view_from_the_southeast).jpg', 'KMG': '五华区与盘龙区天际线_-_航拍_-_2025-05-16_03.jpg',
    'KOW': 'Ganzhounan_Railway_Station_7959_1.jpg', 'KRK': 'Wawel_on_Wisla.JPG', 'KRN': '00_2797_Kiruna_(Schweden)_-_Erzbergwerk.jpg',
    'KRR': 'Park_near_the_stadium_in_Krasnodar_(3).jpg', 'KRS': 'Przystan_ks_ubt.jpeg', 'KSC': 'Dóm_svätej_Alžbety_a_Kaplnka_sv._Michala,_Košice,_Slovensko.jpg',
    'KSD': 'Karlstad_banner_View_from_Klaraborgsbron.jpg', 'KSY': 'Ani_seen_from_Armenia.jpg', 'KTM': 'Bouddhanath,_2009.jpg',
    'KTT': 'Levi_hiihtokeskus_2003.jpg', 'KTW': 'Katowice_Spodek_E_aerial_2026.jpg', 'KUA': 'Kuantan_Street_-_Wall_St.jpg',
    'KUF': 'Samara_-_Port_(2008-07-13).jpg', 'KUL': 'Kuala_Lumpur_-_panoramio_(18).jpg', 'KUN': 'Kaunas_Castle_in_2011.JPG',
    'KUT': '2014_Kutaisi,_Katedra_Bagrati_(04).jpg', 'KVA': 'Port_of_Kavala.jpg', 'KVO': 'Manastir_Žiča,_Srbija,_045.JPG',
    'KVX': 'Архитектурный_ансамбль_Трифонова_монастыря,_вид_с_озера_осенью.jpg', 'KWI': 'Kuwait_towers.jpg', 'KZN': 'Казанский_кремль._Панорама_с_колеса_обозрения.jpg',
    'LAP': 'La_Paz_vista_desde_the_one.jpg', 'LAS': 'Las_Vegas_63.jpg', 'LAX': 'Hollywood_Sign_(Zuschnitt).jpg',
    'LBA': 'Leedstownhall2.jpg', 'LCA': 'Larnaca_01-2017_img14_Finikoudes.jpg', 'LCG': 'Torre_de_Hércules_2023.jpg',
    'LCJ': 'Łódź_-_Centrum,_Ulica_Piotrkowska_-_panoramio.jpg', 'LED': 'Grand_Cascade_in_Peterhof_01.jpg', 'LEI': 'Alcazaba_de_Almería.jpg',
    'LEJ': 'Völkerschlachtdenkmal_außen.JPG', 'LGA': 'Statue_of_Liberty_and_a_sightseeing_boat,_Liberty_Island,_New_York.jpg', 'LGB': 'RMS_Queen_Mary_Long_Beach_January_2011_view.jpg',
    'LGK': 'Langkawi_cablecar_bridge.jpg', 'LGW': 'London_-_London_Tower_Bridge_-_140806_171049.jpg', 'LHE': 'Badshahi_Mosque_July_1_2005_pic32_by_Ali_Imran_(1).jpg',
    'LIL': 'Lille_vue_gd_place.JPG', 'LIM': 'Plaza_Mayor_de_Lima-1.jpg', 'LIN': '20110724_Milan_Cathedral_5260.jpg',
    'LIR': 'Volcán_Miravalles_-_panoramio.jpg', 'LIS': 'Belem_Tower_-_April_2019_(2).jpg', 'LJU': '2021-07-28_Ljubljana-0881.jpg',
    'LLA': 'Lulea-city-festival-water.jpg', 'LNZ': 'PlacodeLinz.jpg', 'LON': 'London_-_London_Tower_Bridge_-_140806_171049.jpg',
    'LOP': 'Gunung_Rinjani_dari_Jalur_Sembalun.jpg', 'LPA': 'Roque_Nublo_24.JPG', 'LPL': 'Royal_Liver_Building.jpg',
    'LTN': 'London_-_London_Tower_Bridge_-_140806_171049.jpg', 'LUX': 'Palacio_Gran_Ducal_de_Luxemburgo.jpg', 'LUZ': 'Lublin_Zamek.JPG',
    'LXR': 'Luxor,_Egypt,_Karnak.jpg', 'LXS': 'MirinaLimnosGreece.jpg', 'LYS': 'France-003038_-_Basilica_of_Notre-Dame_de_Fourvière_(15939822990).jpg',
    'MAA': 'Ripon_Building_aerial_view.jpg', 'MAD': 'Palacio_Real_de_Madrid_Julio_2016_(cropped).jpg', 'MAH': 'Ciudadela,_en_Menorca_(Baleares,_España).jpg',
    'MAN': 'Manchester_Town_Hall_from_Lloyd_St.jpg', 'MBA': 'Fort_JesusMombasa.jpg', 'MCT': 'Sultan_Qaboos_Grand_Mosque_(1).jpg',
    'MCX': 'ЖумгІа_мажгит,_МахІачхъала.jpg', 'MDC': 'Bunaken2.jpg', 'MDE': 'Panorámica_de_Medellín_desde_el_Cerro_El_Picacho.jpg',
    'MDZ': 'Aconcagua2016.jpg', 'MED': 'Madeena_masjid_nabavi_12122008230.jpg', 'MEL': '1_flinders_st_station_melb.jpg',
    'MES': 'Medan_city_2019_(cropped).jpg', 'MEX': 'Atardecer_En_Bellas_Artes_Vertical_(128312121).jpeg', 'MHG': 'Mannheim_Innenstadt.jpg',
    'MIA': 'Miamimetroarea.jpg', 'MIL': '20110724_Milan_Cathedral_5260.jpg', 'MIR': 'View_of_Monastir_from_the_ribat_tower.jpg',
    'MJT': 'Mytilene_banner.JPG', 'MLA': 'Malta,_2010_-_panoramio_-_Bengt_Nyman_(23).jpg', 'MLE': 'Maldives_banner_Small_island_shoreline_with_beach.jpg',
    'MLG': 'Skyline_Malang_Barat.jpg', 'MLX': '44_malatya_panorama.JPG', 'MMA': '19-07-12-Malmö-DJI_0765-Turning-Torso-RalfR.jpg',
    'MME': 'TransportbrugMiddlesbrough.JPG', 'MMK': 'Murmansk.jpg', 'MMX': '19-07-12-Malmö-DJI_0765-Turning-Torso-RalfR.jpg',
    'MNL': 'Big_Manila.jpg', 'MOL': 'View_of_Molde_church.jpg', 'MOW': "00_0568_Saint_Basil's_Cathedral_-_Moscow.jpg",
    'MPL': 'Montpellier_-_Opéra_Comédie.jpg', 'MQF': 'Magnitogorsk_-_Правобережный_район.jpg', 'MQM': 'Mardin,_Mardin_Merkez-Mardin,_Turkey_-_panoramio_(1).jpg',
    'MRS': 'Marseille_Old_Port.jpg', 'MRU': 'Le_Morne_Peninsula_in_Mauritius_(53697779236).jpg', 'MRV': 'Вокзал_МВ.jpg',
    'MSQ': 'Мінск._Сквер_па_плошчы_Незалежнасці.jpg', 'MSY': 'French_Quarter,_looking_north_with_Mississippi_River_to_the_right_2011.jpg', 'MUC': 'Marienplatz_und_Rathaus_München.jpg',
    'MXP': '20110724_Milan_Cathedral_5260.jpg', 'NAJ': 'Momine_Hatoon_Mausoleum.jpg', 'NAL': 'Белый_дом_КБР.jpg',
    'NAP': "Castel_dell'_Ovo.jpg", 'NAV': 'View_of_Cappadocia_edit.jpg', 'NBC': 'Naberezhnye_Tchelny_1.JPG',
    'NBE': 'Sousse_Kasbah.JPG', 'NBO': 'A_lone_giraffe_in_Nairobi_National_Park.jpg', 'NCE': 'Nice_abc_1.jpg',
    'NCL': 'Tyne_Bridge_HDR-IMG_8199_200_201_202_203_HDR.jpg', 'NCU': 'The_Karakalpakstan_State_Museum_of_Art_named_after_I.V._Savitsky.jpg', 'NGB': 'Ningbo_South_Business_District_24-09-2018.jpg',
    'NHA': '04052023_Ponagar_Hindu_temples_complex,_Nha_Trang_Vietnam_-_240.jpg', 'NKG': 'Nanjing_CBD_from_City_Wall.jpg', 'NMA': 'Moellah_Kirigizmadrassa.jpg',
    'NOS': 'View_of_Nosy_Komba,_Madagascar.jpg', 'NOZ': 'Шерегеш.jpg', 'NQT': 'Nottingham_Castle_Gate_2009.jpg',
    'NQZ': 'Night_at_Esil_District,_Astana_(P1190721).jpg', 'NRT': 'Tokyo_Tower_2023.jpg', 'NTE': 'Nantes_aérien_château3.jpg',
    'NTL': 'Newcastle_-_aerial_images_(3)_(7445134654).jpg', 'NUE': 'Nürnberg_Burg_ArM.jpg', 'NVI': 'Город_Навои,_проспект_Халклар_Дустлиги.JPG',
    'NYC': 'Statue_of_Liberty_and_a_sightseeing_boat,_Liberty_Island,_New_York.jpg', 'NYO': 'Gamla_stan_February_2013_01.jpg', 'OAK': 'GoldenGateBridge-001.jpg',
    'ODB': 'Mezquita_de_Córdoba_desde_el_aire_(Córdoba,_España).jpg', 'OGL': "St_George's_Cathedral.jpg", 'OGZ': 'View_of_Vladikavkaz.jpg',
    'OHD': 'Church_of_St._John_at_Kaneo_6.jpg', 'OLB': 'Capriccioli.jpg', 'OMO': 'Mostar_Old_Town_Panorama_2007.jpg',
    'OMR': '2025-05-04_Nagyváradi_részlet_05.jpg', 'OMS': 'Omsk_banner.jpg', 'ONT': 'Hollywood_Sign_(Zuschnitt).jpg',
    'OPO': 'Puente_Don_Luis_I,_Oporto,_Portugal,_2012-05-09,_DD_13.JPG', 'ORD': 'A_public_square_in_Chicago_(9326033069).jpg', 'ORF': 'Norfolk_Virginia_Wikivoyage_banner.jpg',
    'ORK': 'Centre,_Cork,_Ireland_-_panoramio_(5).jpg', 'ORL': 'Magic_Kingdom_castle.jpg', 'ORY': 'Tour_Eiffel_Wikimedia_Commons.jpg',
    'OSA': 'Osaka_Castle_02bs3200.jpg', 'OSI': 'Osijek_panorama_Gornji_grad.jpg', 'OSL': 'Full_Opera_by_night.jpg',
    'OSR': 'Katedrála_Božského_Spasitele,_Nová_Karolina_a_Dolní_oblast_Vítkovic,_pohled_z_Nové_radnice,_srpen_2011.jpg', 'OSS': 'Osh,_Kyrgyzstan_-_panoramio_(4).jpg', 'OST': '0_Beffroi_et_halle_aux_draps_-_Bruges_(Belgique)_1.jpg',
    'OTP': 'Ateneo_Rumano,_Bucarest,_Rumanía,_2016-05-29,_DD_73.jpg', 'OUL': 'Oulu_Cathedral.jpg', 'OVB': 'Novosibirsk_view.jpg',
    'OVD': 'Cathedral_of_Oviedo_2021_-_exterior.jpg', 'OZG': 'Zagora.jpg', 'PAD': 'Paderborn_Dom_asv2024-05_img13.jpg',
    'PAE': 'Space_Needle002.jpg', 'PAR': 'Tour_Eiffel_Wikimedia_Commons.jpg', 'PDL': 'Lagoa_das_Sete_Cidades3.jpg',
    'PDV': 'Antique-theater-plovdiv.jpg', 'PED': 'Pardubice_CZ_Zelena_brana.JPG', 'PEE': 'Perm_Russia.jpg',
    'PEG': 'Perugia-Piazza-del-Comune.jpg', 'PEK': 'Hall_of_Supreme_Harmony_(20241127120000).jpg', 'PER': 'Elizabeth_Quay_February_2016_(cropped).jpg',
    'PEZ': 'Penza_from_Ferris_wheel.JPG', 'PFO': 'Tombs_of_the_Kings_(Paphos).jpg', 'PHL': 'Exterior_of_the_Independence_Hall,_Aug_2019.jpg',
    'PHX': 'Phoenix,_Arizona.JPG', 'PIX': 'Ilha_do_Pico_vista_da_Fajã_Grande,_Calheta,_ilha_de_São_Jorge,_Açores,_Portugal.JPG', 'PKV': 'Pskov_asv07-2018_Kremlin_before_sunset.jpg',
    'PLQ': 'Quite_summer_evening_in_the_port_city_Klaipeda.jpg', 'PMF': 'Parma_-_Italy_-_July_7th_2013_-_07.jpg', 'PMI': 'Kathedrale_von_Palma_II.jpg',
    'PMO': 'Palermo_Cathedral_BW_2025-04-29_11-57-44.jpg', 'PNA': 'Pamplona_2022_-_west_facade_front.jpg', 'POM': 'Port_Moresby_Town2_Mschlauch.jpg',
    'POP': 'Puertoplatafromtheair.JPG', 'POR': 'Yyteri1.jpg', 'POZ': 'Poznan_10-2013_img10_Town_hall.jpg',
    'PPT': 'Papeete_-_Marina_Taina.JPG', 'PQC': 'Bai-sao-phu-quoc-tuonglamphotos.jpg', 'PRG': 'Prague_07-2016_View_from_Petrinska_Tower_img2.jpg',
    'PRI': 'Valleé_de_mai2.jpg', 'PRN': 'PRISHTINA_2013_(13).jpg', 'PSA': 'Campanile_Dôme_-_Pise_(IT52)_-_2022-08-31_-_20.jpg',
    'PSR': 'Pescara_-_foce_del_fiume_vista_dal_ponte_del_mare.JPG', 'PTP': 'Pointe_de_la_Petite-Tortue.JPG', 'PTY': 'Panama_Canal_Gatun_Locks.jpg',
    'PUF': 'Château_Pau_Enceinte.jpg', 'PUJ': 'Punta_Cana_29_april_2012.jpg', 'PUS': 'Gamcheon_Culture_Village_1.jpg',
    'PUY': 'The_new_old_amphitheater_in_Pula_Istria_(19629095974).jpg', 'PVG': 'Promenade_du_Bund.jpg', 'PVK': 'Port_of_Preveza_2013.jpg',
    'PXO': 'Porto_Santo_(22361800223).jpg', 'QSR': 'Ravello_September_2007.jpg', 'RAK': 'MoroccoMarrakech_DjemaaElFna..jpg',
    'RDO': 'Pałac_Kultury_i_Nauki_2019.jpg', 'REG': 'Reggio_Calabria_-_Museo_archeologico_nazionale_-_Bronzi_di_Riace_-_11.jpg', 'REK': 'Hallgrimskirkja_mai_2026.jpg',
    'REN': 'Вид_с_новостройки_на_Ул_Чкалова_(263014995)_(cropped).jpeg', 'REU': 'Amphitheatre_of_Tarragona_02.jpg', 'RGK': 'Gorno-Altaysk_Center_0665.jpg',
    'RHO': 'RhodosStadtzentrum5.JPG', 'RIC': 'Richmond,_Virginia_-_Facing_West_(32664969852).jpg', 'RIO': 'Pão_de_Açucar_-_Sugarloaf_Mountain_-_Zuckerhut_-_2022.jpg',
    'RIX': "House_of_Blackheads_and_St._Peter's_Church_Tower,_Riga,_Latvia_-_Diliff.jpg", 'RJK': 'Rijeka-view-2.jpg', 'RKT': 'Ras_al-Khaimah_December_2015_by_Vincent_Eisfeld.jpg',
    'RMF': 'Marsa_Alam,_Egypt_2007feb08_byDanielCsorfoly.JPG', 'RMI': 'Tempio_malatestiano,_esterno_04.JPG', 'RMO': 'Ansamblul_Catedralei_„Nașterea_Domnului”_8.jpg',
    'RNS': 'Vue_sud-ouest_de_la_place_du_parlement_de_Bretagne,_Rennes,_France.jpg', 'ROM': 'Colosseo_2020.jpg', 'RTM': 'Rotterdam_erasmusbrug.jpg',
    'RTW': 'Крытый_рынок._Саратов.jpg', 'RUH': 'Riyadh_Skyline.jpg', 'RVN': 'Rovaniemi_06101999_rescanned.jpg',
    'RZE': 'PL_Rzeszów,_ratusz_2021-05-04--11-00-20_(cropped).jpg', 'RZV': 'Panorama_of_Rize.jpg', 'SAI': 'Angkor_Wat.jpg',
    'SAL': 'San_Salvador_-_El_Salvador_(50899440617).jpg', 'SAN': 'San_Diego_skyline_18_(cropped).jpg', 'SAO': 'Sao_Paulo_Skyline_in_Brazil.jpg',
    'SAW': 'Hagia_Sophia_Mars_2013.jpg', 'SBZ': 'Hermannstadt,_Großer_Ring_2011a.jpeg', 'SCL': 'Santiago_de_Chile,_Desde_Cerro_San_Cristóbal_(cropped).jpg',
    'SCN': 'SB-Rathaus.jpg', 'SCO': 'Aktau_plane.jpg', 'SCQ': 'Santiago_cathedral_2021.jpg',
    'SCV': 'View_on_Suceava_(Romania)_from_Fortess.jpg', 'SCW': 'Сыктывкар_-_panoramio_(1).jpg', 'SDF': 'Louisville_Panorama_banner.jpg',
    'SDQ': 'Santo_Domingo_(Dominican_Republic)_taken_atop_Novocentro_tower_viewing_the_city_to_the_southwest_2010.jpg', 'SDR': 'Palacio_de_la_Magdalena.jpg', 'SEA': 'Space_Needle002.jpg',
    'SEL': '광화문_월대.jpg', 'SEZ': 'La_Digue_asv2024-10_img15_Union_Estate.jpg', 'SFO': 'GoldenGateBridge-001.jpg',
    'SGC': 'Surgut,_Russia_06.jpg', 'SGN': 'Basílica_de_Nuestra_Señora,_Ciudad_Ho_Chi_Minh,_Vietnam,_2013-08-14,_DD_09.JPG', 'SHA': 'Promenade_du_Bund.jpg',
    'SHJ': 'Sharjah_city_skyline_in_2015.jpg', 'SIA': 'Terracotta_Army,_View_of_Pit_1.jpg', 'SID': 'Sal_SantaMaria.jpg',
    'SIN': 'Marina_Bay_Sands_Hotel_3_(31345110894).jpg', 'SJC': 'San_Jose_(California)_banner_Center_for_the_Performing_Arts.jpg', 'SJJ': 'Baščaršija_2006.jpg',
    'SJO': 'Cityscape_of_San_José,_Costa_Rica_(253552473).jpg', 'SJU': 'Old_San_Juan_aerial_view.jpg', 'SKD': 'Registan_01.jpg',
    'SKG': 'White_Tower_in_Thessaloniki.jpg', 'SKP': 'Stone_Bridge_Skopje_4.jpg', 'SLL': 'Downtown_Salalah_Oman.jpg',
    'SMI': 'Samos_049_2009.JPG', 'SNN': 'Ireland_Cliffs_of_Moher_BW_2025-09-11_14-27-51.jpg', 'SOF': 'AlexanderNevskyCathedral-Sofia-6.jpg',
    'SPC': 'Roque_de_los_Muchachos_view1.jpg', 'SPU': "Diocletian's_Palace_(original_appearance).jpg", 'SPX': 'Pyramids_of_the_Giza_Necropolis.jpg',
    'SSH': 'Sharm_El_Sheikh_Panoramic.jpg', 'STI': 'SantiagoCityDominicanRep.JPG', 'STN': 'London_-_London_Tower_Bridge_-_140806_171049.jpg',
    'STO': 'Gamla_stan_February_2013_01.jpg', 'STR': 'Neues_Schloss_Schlossplatzspringbrunnen_Jubiläumssäule_Schlossplatz_Stuttgart_2015_01.jpg', 'STW': 'Центр_Ставрополя.jpg',
    'SUF': "Santa_Maria_dell'Isola_-_Tropea_-_Calabria_-_Italy_-_July_25th_2013_-_03.jpg", 'SUJ': 'Satu_Mare,_parcul_si_Hotel_Dacia.jpg', 'SVG': 'Preikestolen_Norge.jpg',
    'SVQ': 'Plaza_de_España_(Sevilla)_-_01.jpg', 'SVX': 'Views_of_Yekaterinburg_from_Vysotsky_viewpoint_-_12.jpg', 'SWF': 'Statue_of_Liberty_and_a_sightseeing_boat,_Liberty_Island,_New_York.jpg',
    'SXB': 'Strasbourg_Cathedral_Exterior_-_Diliff.jpg', 'SXR': 'Dal_LakeVR.jpg', 'SYD': '00_1375_Sydney_Opera_House_(Australia).jpg',
    'SYX': 'Hainan_Sanya_1.jpg', 'SZF': 'Samsun_-_panoramio_(11).jpg', 'SZG': 'Salzburg_-_Festung_Hohensalzburg.JPG',
    'SZX': 'The_west_panorama_of_Shenzhen2021.jpg', 'SZY': 'Zamek_Olsztyn_(2).jpg', 'SZZ': 'Szczecin_aerial_3a.jpg',
    'TAG': 'Chocolate_Hills_overview.JPG', 'TAO': '青岛湛山及太平山俯瞰_2018-10-10.jpg', 'TAS': 'Aerial_view_of_Tashkent,_Uzbekistan.JPG',
    'TAT': 'Panorama_High_Tatras_from_Poprad.jpg', 'TAY': 'Tartu_asv2022-04_img31_View_from_Emajõe_Tower.jpg', 'TBS': 'Narikala,_Tiflis,_Georgia,_2016-09-29,_DD_91.jpg',
    'TCI': 'Teide_von_Nordosten_(Zuschnitt_2).jpg', 'TFS': 'Teide_von_Nordosten_(Zuschnitt_2).jpg', 'TGD': 'Titograd.jpg',
    'TGM': 'Palatul_Culturii_(Targu_Mures).jpg', 'TIA': 'Tirana_-_Skanderbeg_Square_(Sheshi_Skënderbej)_-_by_Pudelek.jpg', 'TIV': '20090719_Crkva_Gospa_od_Zdravlja_Kotor_Bay_Montenegro.jpg',
    'TJM': 'Крестовоздвиженская_церковь_(Тюмень)-2.jpg', 'TKU': 'Turku_Castle,_Turku,_Finland.jpg', 'TLL': 'Tallin_mauer_mit_turm.jpg',
    'TLN': 'PlaceLiberteToulon.jpg', 'TLS': 'Toulouse_capitole_R.jpg', 'TLV': 'Sarona_CBD_01.jpg',
    'TMJ': 'Termez_Sultan-Saodat.jpg', 'TMP': 'Tammerkoski_2021.jpg', 'TNG': 'Tangier_-_44699733295.jpg',
    'TNR': 'Lake_Anosy,_Central_Antananarivo,_Capital_of_Madagascar,_Photo_by_Sascha_Grabow.jpg', 'TOS': 'Tromsø_sentrum_(5835702754).jpg', 'TPA': 'Tampa_banner.jpg',
    'TPE': 'Taipei_101_from_Xiangshan_20250731.jpg', 'TPS': 'Erice.jpg', 'TQO': 'Tulum_2006_2.jpg',
    'TRD': 'Die_Nidaros_Kathedrale_in_Trondheim._05.jpg', 'TRF': 'Full_Opera_by_night.jpg', 'TRG': 'Mount_Maunganui_25.jpg',
    'TRN': 'Mole_Antonelliana_in_Turin.jpg', 'TRS': 'Plaza_de_la_Unidad_de_Italia,_Trieste,_Italia,_2017-04-15,_DD_11-15_HDR.jpg', 'TRV': 'Thiruvanthapuram_Temple.JPG',
    'TSF': 'Panorama_of_Canal_Grande_and_Ponte_di_Rialto,_Venice_-_September_2017.jpg', 'TSR': 'Rumunska_saborna_crkva_03.jpg', 'TUN': 'Sidi_Bou_Said,_Tunisia,_19_March_2018_DSC_8004.jpg',
    'TYO': 'Tokyo_Tower_2023.jpg', 'TYS': 'Downtown_Knoxville_(cropped).jpg', 'TZL': 'Tuzla_View_of_Tuzla.jpg',
    'TZX': 'Sümela_Manastır.jpg', 'UBN': 'Chinggis_Khaan_statue_Complex.jpg', 'UFA': 'Salavat_Yulaev_Panorama.jpg',
    'UGC': 'KhivaWalls.jpg', 'UIO': 'FACHADA_ASAMBLEA_NACIONAL._QUITO,_20_DE_FEBRERO_2020._01.jpg', 'UKK': 'Панорама_города_Усть-Каменогорск.jpg',
    'ULH': 'Madain_Saleh_WV_banner.jpg', 'ULY': 'The_city_of_Ulyanovsk,_Russia.jpg', 'UNN': 'Thailand_-_Koh_Phayam_(24873552885).jpg',
    'URA': 'Краеведческий_музей_-_panoramio_(8).jpg', 'URT': 'Surat_Thani_waterfront.jpg', 'USH': 'Ushuaia_aerial_panorama.jpg',
    'USM': 'Koh_Samui_Lipa_Noi2.jpg', 'UTH': 'Wat_Pa_Phu_Kon_Udon_Thani.jpg', 'UTP': 'Pattaya_beach_from_view_point.jpg',
    'VAA': 'Vaasa_Church_from_water_tower.jpg', 'VAR': 'Varna-cathedral-Orel.jpg', 'VCE': 'Panorama_of_Canal_Grande_and_Ponte_di_Rialto,_Venice_-_September_2017.jpg',
    'VDH': 'Phongnhakebang6.jpg', 'VGO': 'Centro_e_porto_de_Vigo_cropped.jpg', 'VIE': 'Schloss_Schönbrunn_Wien_2014_(Zuschnitt_2).jpg',
    'VLC': 'Valencia,_Ciudad_de_las_Ciencias_y_de_las_Artes.jpg', 'VLN': 'Valencia_(Venezuela)_Skyline.jpg', 'VNO': 'Gedimino_pilis_by_Augustas_Didzgalvis.jpg',
    'VNS': 'Varanasi,_India,_Varanasi_eternal.jpg', 'VOG': 'Волгоград._Мамев_курган._Родина-мать_зовет.jpg', 'VRN': 'Arena-XE3F2406a.jpg',
    'VTE': 'Pha_That_Luang_Vientiane_Laos.jpg', 'VVO': 'Russky_Bridge_(October_2024)-0_2.jpg', 'VXO': 'Växjö_from_plane.JPG',
    'WAS': 'United_States_Capitol_west_front_edit2.jpg', 'WAW': 'Pałac_Kultury_i_Nauki_2019.jpg', 'WLG': 'WellingtonPanorama.jpg',
    'WMI': 'Pałac_Kultury_i_Nauki_2019.jpg', 'WRO': 'Wroclaw-Rathaus.jpg', 'WUH': 'CN_-_Hubei_-_Wuhan_-_Kranichpagode.jpg',
    'XCR': 'Hôtel_de_ville_de_Châlons-en-Champagne_(Marne).JPG', 'XMN': '鼓浪屿_-_panoramio.jpg', 'YEA': 'Downtown_edmonton.jpg',
    'YEI': 'Green_Mosque_in_Bursa.jpg', 'YIW': 'Yiwu_3.jpg', 'YKS': 'Проспект_Ленина_возле_остановки_«Кинотеатр_Центральный».jpg',
    'YMQ': 'Basilique_Notre-Dame_de_Montreal_02.jpg', 'YOW': 'Parliament_Hill,_Ottawa.jpg', 'YQB': 'Château_Frontenac01.jpg',
    'YQQ': 'Comox_BC_aerial_view.jpg', 'YTO': 'Sunset_Toronto_Skyline_Panorama_Crop_from_Snake_Island.jpg', 'YTZ': 'Sunset_Toronto_Skyline_Panorama_Crop_from_Snake_Island.jpg',
    'YUY': 'Rouynnoranda349398383.JPG', 'YVR': 'Skyline_of_Vancouver,_Canada.jpg', 'YXE': 'Saskatoon-banner.jpg',
    'YYC': 'PengrowthSaddledomeDay.jpg', 'ZAD': 'Sea_organ_Zadar_3.JPG', 'ZAG': 'Zagreb_Church_of_St._Mark_(34411766366).jpg',
    'ZAZ': 'Zaragoza_-_Basilica_de_Nuestra_Señora_del_Pilar_01.jpg', 'ZNZ': 'Zanzibar_sultan_palace.jpg', 'ZRH': 'Grossmünster_Zurich_Switzerland_24Jun2021.jpg',
    'ZTH': 'Navagio_beach_Zakynthos.jpg',
}
# Turnul Eiffel: varianta pe orizontală, se vede întreg pe card
_PARIS = "La_Tour_Eiffel_vue_de_la_Tour_Saint-Jacques,_Paris_août_2014_(2).jpg"
OVERRIDES = {**EMBLEMATIC, "CDG": _PARIS, "ORY": _PARIS, "BVA": _PARIS, "PAR": _PARIS}


def public(db):
    """{cod: fișier} pentru site. Pozele alese de tine în pagina „Poze” (kv photo_custom) au prioritate."""
    return {**(db.get_kv("photos") or {}), **OVERRIDES, **(db.get_kv("photo_custom") or {})}


def sync_from_site(db):
    """În cloud: preia pozele de pe site-ul publicat de laptop (inclusiv cele încărcate de tine), ca să nu se piardă."""
    try:
        data = net.get_json("https://flycenterhub.github.io/data/photos.json", headers=UA, timeout=30)
        if isinstance(data, dict) and len(data) > 100:
            db.set_kv("photo_custom", data)
            for f in data.values():
                if isinstance(f, str) and f.startswith(LOCAL):
                    name = local_name(f)
                    path = os.path.join(local_dir(), name)
                    if not os.path.exists(path):
                        os.makedirs(local_dir(), exist_ok=True)
                        with open(path, "wb") as out:
                            out.write(net.request(f"https://flycenterhub.github.io/photos/{name}", timeout=60))
    except Exception as e:
        log.warning("Poze de pe site: %s", e)


# ---------- poze încărcate de pe laptop: web/photos/COD.jpg, în kv apar ca „local:COD.jpg?v=...” ----------
LOCAL = "local:"


def local_dir():
    from . import config
    return os.path.join(config.WEB_DIR, "photos")


def local_name(f):
    return f[len(LOCAL):].split("?")[0]


def save_upload(db, code, data_url):
    """Poza trimisă din pagina „Poze” (JPEG deja micșorat în browser) -> web/photos/COD.jpg."""
    import base64
    import time
    m = re.match(r"data:image/(jpeg|jpg|png|webp);base64,(.+)$", data_url or "", re.S)
    if not m:
        return None
    raw = base64.b64decode(m.group(2))
    if len(raw) > 3_000_000:
        return None
    ext = "jpg" if m.group(1) in ("jpeg", "jpg") else m.group(1)
    os.makedirs(local_dir(), exist_ok=True)
    name = f"{re.sub(r'[^A-Z0-9]', '', code.upper())}.{ext}"
    with open(os.path.join(local_dir(), name), "wb") as f:
        f.write(raw)
    ref = f"{LOCAL}{name}?v={int(time.time())}"
    set_custom(db, code, ref)
    return ref


def local_files(db):
    """Pozele încărcate de tine care sunt folosite acum (pentru publicarea pe site): {cale: bytes}."""
    out = {}
    for f in (public(db) or {}).values():
        if isinstance(f, str) and f.startswith(LOCAL):
            path = os.path.join(local_dir(), local_name(f))
            if os.path.exists(path):
                with open(path, "rb") as fh:
                    out[f"photos/{local_name(f)}"] = fh.read()
    return out


# ---------- pagina „Poze” (doar pe laptop): verifici și schimbi poza fiecărei destinații ----------
COMMONS = "https://commons.wikimedia.org/w/api.php"


def parse_file(text):
    """Link Wikimedia Commons (pagina pozei sau adresa imaginii) sau numele fișierului -> numele fișierului."""
    t = urllib.parse.unquote((text or "").strip())
    m = re.search(r"(?:File|Fișier|Datei|Fichier|Archivo|Plik):([^?#]+)", t, re.I)
    if m:
        t = m.group(1)
    elif "upload.wikimedia.org" in t:
        parts = t.split("?")[0].split("/")
        t = parts[-2] if "/thumb/" in t else parts[-1]
    return t.strip().replace(" ", "_")


def file_info(file):
    """Verifică pe Commons că fișierul există și e fotografie. Întoarce {file, thumb} sau None."""
    q = (f"{COMMONS}?action=query&format=json&prop=imageinfo&iiprop=url|mime&iiurlwidth=500&titles="
         + urllib.parse.quote("File:" + file))
    pages = net.get_json(q, headers=UA)["query"]["pages"]
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        if "missing" in p or ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            return None
        return {"file": p["title"][5:].replace(" ", "_"), "thumb": ii.get("thumburl") or ii.get("url")}
    return None


def search(query, limit=24):
    """Caută fotografii pe Wikimedia Commons (libere, gratuite)."""
    q = (f"{COMMONS}?action=query&format=json&generator=search&gsrnamespace=6&gsrlimit={limit}"
         f"&gsrsearch={urllib.parse.quote(query + ' filetype:bitmap')}&prop=imageinfo&iiprop=url|mime|size&iiurlwidth=400")
    pages = (net.get_json(q, headers=UA).get("query") or {}).get("pages", {})
    out = []
    for p in sorted(pages.values(), key=lambda x: x.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("mime") == "image/jpeg" and ii.get("width", 0) >= 800 and not BAD.search(p["title"]):
            out.append({"file": p["title"][5:].replace(" ", "_"), "thumb": ii.get("thumburl")})
    return out


def set_custom(db, code, file):
    """Salvează poza aleasă pentru o destinație ('' = revine la poza automată)."""
    custom = db.get_kv("photo_custom") or {}
    if file:
        custom[code] = file
    else:
        custom.pop(code, None)
    db.set_kv("photo_custom", custom)


def admin_list(db):
    """Toate destinațiile, cu poza actuală și de unde vine."""
    auto, custom = db.get_kv("photos") or {}, db.get_kv("photo_custom") or {}
    names = {p["code"]: (p["name"], p["country"]) for p in db.q("SELECT code, name, country FROM places")}
    rows = []
    for r in db.q("SELECT dest, COUNT(*) AS n FROM fares GROUP BY dest ORDER BY n DESC"):
        c = r["dest"]
        f = custom.get(c) or OVERRIDES.get(c) or auto.get(c)
        src = "aleasă de tine" if c in custom else "emblematică" if c in OVERRIDES else "automată" if f else "fără poză"
        name, country = names.get(c, (c, ""))
        rows.append({"code": c, "name": name or c, "country": country or "", "zboruri": r["n"], "file": f, "src": src})
    return rows


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    from .db import DB
    d = DB()
    print(refresh(d, force="--force" in sys.argv), "găsite;", len(public(d)), "în total")
    print(json.dumps(dict(list(public(d).items())[:5]), ensure_ascii=False))
