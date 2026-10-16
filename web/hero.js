/* Căutarea simplă de sus („Unde zbori ieftin?”): De unde · Unde · Când · Buget → o singură listă.
   Modul separat: dacă nu-l mai vrem, ștergem <script src="hero.js"> și <link href="hero.css"> din index.html.
   Folosește funcțiile din app.js (api, flightCard, sunny, bestSeason, state…). */
(function () {
  // doar orașe chiar la munte (Alpi, Tatra), nu aeroporturi de oraș mare „aproape de munte”
  const MOUNTAIN = new Set(["INN", "SZG", "BZO", "GVA", "KLU", "GNB", "CMF", "SIR", "TAT", "GHV", // Alpi, Tatra, Brașov
    "KTM", "IXL", "LPB", "FTE", "MDZ", "ALA", "SLC", "YYC", "DLI"]);                         // Himalaya, Anzi, Rockies, Tian Shan
  // „La plajă”: orașe din interior sau metropole unde e doar cald, nu de plajă
  const INLAND = new Set(["MAD", "SVQ", "ZAZ", "CAI", "SPX", "RAK", "OZZ", "AMM", "RUH", "ELQ", "MED", "LHE", "DEL", "BOM", "BKK", "DMK",
    "KUL", "HKG", "SIN", "IST", "ESB", "CNX", "DLI", "KTM", "HAN", "MEX", "BOG", "MDE", "SCL", "JNB", "NBO", "ADD", "KGL", "TAS", "SKD",
    "BHK", "UGC", "NQZ", "ALA", "BSZ", "DYU", "ASB", "EVN", "TBS", "THR", "BGW", "EBL", "SAO", "LIM", "LAS", "SLC", "PHX", "ATL", "CHI",
    "SEL", "BJS", "PEK", "SGN", "BLR", "CCU", "PTY", "SAL", "SJO", "ACC", "MDZ", "LPB", "CBB", "FTE", "TNR", "BUE", "EZE", "GRU", "IXL", "JED", "SZX", "CAN", "SHA", "PVG", "TPE", "MNL", "SHJ", "DOH", "KWI", "BAH", "WUH", "HGH", "TYO", "NRT", "HND", "CTU", "CKG", "SIA", "ORN", "ALG", "TUN", "CMN", "TLS", "LYS", "BOD", "PRG", "VIE", "BER"]);
  // „City break”: insule și stațiuni de plajă (nu sunt city break)
  const RESORT = new Set(["HRG", "SSH", "RMF", "AYT", "TFS", "LPA", "PMI", "MAH", "ZTH", "CFU", "RHO", "JTR", "CHQ", "HER", "FNC", "PFO",
    "AHO", "RMI", "FAO", "LEI", "CDT", "DJE", "MIR", "NBE", "MLA", "CAG", "CTA", "PMO", "SUF", "BRI", "PSR", "DBV", "TGD", "FMM", "SNN", "TGM", "BBU", "BLL",
    "GZP", "BJV", "DLM", "BOJ", "VAR", "IBZ", "FUE", "ACE", "TCI", "TFN", "OLB", "JSI", "JKH", "LMP", "PXO", "PDL", "HOR", "PUY",
    "TIV", "ECN", "KGS", "EFL", "PVK", "SMI", "KLX", "AOK", "JMK", "SPU", "ZAD", "BDS", 
    "ARW", "BCM", "IAS", "SCV", "SBZ", "CND", "CRA", "OTP", "CLJ", "TSR", "OMR"]);
  const CAUCASUS = new Set(["KUT", "TBS", "BUS", "EVN", "LWN", "GYD", "BAK", "NAJ", "GNJ"]);
  const IDEAS = [
    ["any", "🌍", "Oriunde"], ["beach", "🏖️", "La plajă"], ["city", "🏙️", "City break"],
    ["exotic", "🌴", "Exotic"], ["ski", "⛷️", "La munte"],
  ];
  const BUDGETS = [0, 50, 100, 200, 300, 500, 800, 1200];
  const PAGE = 12;
  const H = { from: "ALL", where: "any", text: "", when: "", budget: 0, trip: "RT", shown: PAGE, rows: null, busy: false, regions: null, label: "" };
  // „la plajă”: medie zi+noapte de cel puțin 21°C (≈ 26°C ziua) și fără ploi multe; prinde și Canarele, Cipru, Egipt
  const beach = (dest, m) => { const [t, mm] = (CLIMATE[dest] || [])[m] || []; return t != null && t >= 21 && mm < 110; };
  const norm = s => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  // numele în română pentru țările/orașele salvate în engleză (ca să găsești „Coreea de Nord”, „Phenian”, „Filipine”…)
  const ALIAS = {
    "north korea": "coreea de nord", "south korea": "coreea de sud", "philippines": "filipine", "brazil": "brazilia",
    "cape verde": "capul verde", "colombia": "columbia", "dominican republic": "republica dominicana", "equatorial guinea": "guineea ecuatoriala",
    "ethiopia": "etiopia", "guadeloupe": "guadelupa", "iraq": "irak", "kyrgyzstan": "kargazstan kirghizstan", "malaysia": "malaezia",
    "mexico": "mexic", "new zealand": "noua zeelanda", "papua new guinea": "papua noua guinee", "south africa": "africa de sud",
    "tajikistan": "tadjikistan", "u.s. virgin islands": "insulele virgine", "british virgin islands": "insulele virgine britanice",
    "cayman islands": "insulele cayman", "reunion": "reunion", "pyongyang": "phenian", "beijing": "pekin", "seoul": "seul",
    "tokyo": "tokio", "new delhi": "delhi", "male": "maldive", "denpasar (bali)": "bali indonezia", "mahe": "seychelles",
  };
  const alias = s => ALIAS[norm(s)] || "";
  // același oraș, aeroporturi diferite (Londra Luton/Stansted, Veneția Treviso/Marco Polo…) = o singură variantă
  const CITY_OF = { SPX: "CAI", CAI: "CAI", TSF: "VCE", VCE: "VCE", CIA: "FCO", FCO: "FCO", LTN: "LON", STN: "LON", LGW: "LON", LHR: "LON",
    BVA: "PAR", ORY: "PAR", CDG: "PAR", WMI: "WAW", WAW: "WAW", CRL: "BRU", BRU: "BRU", NYO: "STO", ARN: "STO", TRF: "OSL", OSL: "OSL",
    DMK: "BKK", BKK: "BKK", HND: "TYO", NRT: "TYO", TYO: "TYO", PEK: "BJS", BJS: "BJS", ICN: "SEL", SEL: "SEL", GYD: "BAK", BAK: "BAK",
    SAW: "IST", IST: "IST", MXP: "MIL", LIN: "MIL" };
  const addDays = (s, n) => { const d = new Date(s + "T12:00"); d.setDate(d.getDate() + n); return iso(d); };

  function months() {
    const now = new Date();
    const n = (state.status?.settings?.exotic?.months_ahead ?? 8); // datele merg atât de departe
    return Array.from({ length: n }, (_, i) => new Date(now.getFullYear(), now.getMonth() + i, 1))
      .map(d => [`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`, `${MONTHS_FULL[d.getMonth()]}${d.getFullYear() !== now.getFullYear() ? " " + d.getFullYear() : ""}`]);
  }
  // fereastra de plecare / întoarcere pentru „Când”
  const MON3 = ["ian", "feb", "mar", "apr", "mai", "iun", "iul", "aug", "sep", "oct", "nov", "dec"];
  const dShort = d => d ? `${+d.slice(8, 10)} ${MON3[+d.slice(5, 7) - 1]}` : "";
  // date fixe: „fix:2026-11-12:2026-11-19” (întoarcerea poate lipsi = doar dus)
  const fixed = when => /^fix:/.test(when || "") ? { dep: when.slice(4, 14), ret: when.slice(15, 25) } : null;
  const fixedLabel = when => { const f = fixed(when); return f ? (f.ret ? `${dShort(f.dep)} → ${dShort(f.ret)}` : `${dShort(f.dep)} · doar dus`) : ""; };
  function window_(when) {
    if (!when) return null;
    const f = fixed(when);
    if (f) return { dep: [f.dep, f.dep], ret: f.ret ? [f.ret, f.ret] : [f.dep, addDays(f.dep, 60)], exact: true };
    if (when === "weekend") {
      const d = new Date(), day = d.getDay(), toFri = (5 - day + 7) % 7;
      const fri = iso(new Date(d.getFullYear(), d.getMonth(), d.getDate() + (day === 6 || day === 0 ? 0 : toFri)));
      const start = day === 6 || day === 0 ? iso(d) : fri;
      return { dep: [start, addDays(fri, 1)], ret: [addDays(fri, 2), addDays(fri, 3)] };
    }
    const [y, m] = when.split("-").map(Number), last = iso(new Date(y, m, 0));
    const first = when + "-01" < iso(new Date()) ? iso(new Date()) : when + "-01";
    return { dep: [first, last], ret: [addDays(first, 2), addDays(last, 21)] };
  }

  async function regionsMap() {
    if (H.regions) return H.regions;
    try {
      const ex = state.exotic || await api("/api/exotic");
      H.regions = { labels: ex.regions || {}, by: Object.fromEntries((ex.fares || []).map(f => [f.dest, f.region])) };
    } catch (e) { H.regions = { labels: {}, by: {} }; }
    return H.regions;
  }

  async function run() {
    H.busy = true; H.shown = PAGE; render();
    const w = window_(H.when), q = new URLSearchParams();
    if (state.exact) q.set("exact", "1");
    if (w) {
      q.set("dep_from", w.dep[0]); q.set("dep_to", w.dep[1]);
      if (H.trip === "RT") { q.set("ret_from", w.ret[0]); q.set("ret_to", w.ret[1]); }
    }
    const eq = new URLSearchParams(w ? { dep_from: w.dep[0], dep_to: w.dep[1] } : {});
    const [rows0, ex] = await Promise.all([
      api(`/api/search?${q}`).catch(() => []),
      api(`/api/exotic?${eq}`).catch(() => null),  // exoticele (Google Explore) au date fixe dus-întors
    ]);
    let rows = [...(rows0 || []), ...((ex && ex.fares) || [])];
    const reg = await regionsMap(), text = norm(H.text);
    const maxNights = H.when === "weekend" ? 4 : fixed(H.when) ? 90 : 28;
    rows = rows.filter(r => {
      if (r.trip !== H.trip) return false;
      if (!text && (NOVAC.has(r.dest) || !r.dest_name || r.dest_name === r.dest)) return false; // nu le propunem la idei, dar se găsesc dacă le scrii
      if (H.from !== "ALL" && r.origin !== H.from) return false;
      if (H.budget && r.price_eur > H.budget) return false;
      if (!(r.days_to_dep >= 1)) return false;
      if (w && r.trip === "RT" && r.ret_date > w.ret[1]) return false;
      if (w?.exact && (r.dep_date !== w.dep[0] || (r.trip === "RT" && r.ret_date !== w.ret[0]))) return false; // exact zilele alese
      if (r.trip === "RT" && r.nights != null && (r.nights < 2 || r.nights > maxNights)) return false;
      const region = reg.by[r.dest];
      if (text) return true; // filtrat mai jos: întâi după oraș, apoi după țară
      if (H.where === "beach") return !INLAND.has(r.dest) && beach(r.dest, +r.dep_date.slice(5, 7) - 1);
      if (H.where === "city") return !region && !MOUNTAIN.has(r.dest) && !RESORT.has(r.dest);
      if (H.where === "exotic") return !!region && !CAUCASUS.has(r.dest);
      if (H.where === "ski") return MOUNTAIN.has(r.dest); // iarna schi, vara drumeții
      return true;
    });
    if (text) { // „Roma” = orașul Roma, nu „România”; potrivire la început de cuvânt
      const word = x => (" " + norm(x).replace(/[^a-z0-9]+/g, " ")).includes(" " + text);
      const whole = x => (" " + norm(x).replace(/[^a-z0-9]+/g, " ") + " ").includes(" " + text + " ");
      const exact = rows.filter(r => [r.dest_name, r.dest, alias(r.dest_name)].some(whole)); // „Roma” = Roma, nu „La Romana”
      const byCity = exact.length ? exact : rows.filter(r => [r.dest_name, r.dest, alias(r.dest_name)].some(word));
      rows = byCity.length ? byCity : rows.filter(r => [r.country, alias(r.country)].some(word));
    }
    // o singură variantă pe destinație: cea mai ieftină
    const best = new Map();
    for (const r of rows) { // același oraș cu 2 coduri (ex. Baku GYD/BAK) = o singură destinație
      const k = CITY_OF[r.dest] || norm(r.dest_name) + "|" + norm(r.country), c = best.get(k);
      if (!c || r.price_eur < c.price_eur) best.set(k, r);
    }
    H.rows = [...best.values()].sort((a, b) => a.price_eur - b.price_eur)
      .map(r => reg.by[r.dest] ? { ...r, region: reg.by[r.dest], region_label: reg.labels[reg.by[r.dest]] } : r);
    H.label = summary();
    H.busy = false;
    render();
    try { gcEvent("cautare: " + H.label); } catch (e) { /* ignorat */ }
    $("#hero-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function summary() {
    const idea = H.text ? H.text : (IDEAS.find(i => i[0] === H.where) || [])[2];
    const when = !H.when ? "oricând" : H.when === "weekend" ? "weekendul acesta" : fixed(H.when) ? "pe " + fixedLabel(H.when) : "în " + (months().find(m => m[0] === H.when) || [, ""])[1].toLowerCase();
    const from = H.from === "ALL" ? "din orice oraș" : "din " + ORIGIN_NAMES[H.from];
    return `${idea === "Oriunde" ? "Oriunde" : idea} ${when}, ${from}${H.budget ? `, sub ${H.budget} €` : ""}`;
  }

  // combinații uzuale; dacă ai ales altceva din „👤” de jos, apare și aceea
  const PAX = [[1,0,0],[2,0,0],[3,0,0],[4,0,0],[5,0,0],[6,0,0],[1,1,0],[1,2,0],[2,1,0],[2,2,0],[2,3,0],[2,0,1],[2,1,1],[2,2,1],[3,1,0],[4,2,0]];
  function paxText([a, c, i]) {
    const p = [`${a} ${a === 1 ? "adult" : "adulți"}`];
    if (c) p.push(`${c} ${c === 1 ? "copil" : "copii"}`);
    if (i) p.push(`${i} ${i === 1 ? "bebeluș" : "bebeluși"}`);
    return p.join(" + ");
  }
  function paxOptions() {
    const cur = [state.adults || 1, state.children || 0, state.infants || 0], key = cur.join("-");
    const list = PAX.some(p => p.join("-") === key) ? PAX : [...PAX, cur];
    return list.map(p => `<option value="${p.join("-")}"${p.join("-") === key ? " selected" : ""}>${paxText(p)}</option>`).join("");
  }

  function field(id, label, icon, control) {
    return `<label class="hf" for="${id}"><span class="hf-l">${label}</span><span class="hf-v"><span class="hf-i" aria-hidden="true">${icon}</span>${control}</span></label>`;
  }

  function formHtml() {
    const origins = (state.status?.origins || []).map(o => o.code).filter(c => ORIGIN_NAMES[c]);
    const sel = (v, cur) => v === cur ? " selected" : "";
    return `
      <div class="hero-in">
        <div class="hero-sl" aria-hidden="true"><i></i><i></i></div>
        <div class="hero-txt">
          <h2 class="hero-h">Lumea e mai <span class="script">aproape</span> decât crezi.</h2>
          <p class="hero-p">Verificăm zilnic mii de zboruri din Timișoara, Cluj, Oradea, București și Budapesta. Tu alegi doar destinația, noi găsim cel mai bun preț.</p>
        </div>
        <form class="hero-box" id="hero-form" autocomplete="off">
          ${field("h-from", "De unde", "🛫", `<select id="h-from"><option value="ALL">Oricare</option>${origins.map(c => `<option value="${c}"${sel(c, H.from)}>${esc(ORIGIN_NAMES[c])}</option>`).join("")}</select>`)}
          ${field("h-text", "Unde", "📍", `<input id="h-text" type="text" placeholder="${esc((IDEAS.find(i => i[0] === H.where) || IDEAS[0])[2])} sau o țară, un oraș" value="${esc(H.text)}">`)}
          ${field("h-when", "Când", "📅", `<select id="h-when"><option value="pick">📅 Alege datele exacte…</option>${fixed(H.when) ? `<option value="${H.when}" selected>📅 ${fixedLabel(H.when)}</option>` : ""}<option value=""${H.when ? "" : " selected"}>Oricând</option><option value="weekend"${sel("weekend", H.when)}>Weekendul acesta</option>${months().map(([v, l]) => `<option value="${v}"${sel(v, H.when)}>${l}</option>`).join("")}</select>`)}
          ${field("h-budget", "Buget / pers.", "💶", `<select id="h-budget">${BUDGETS.map(b => `<option value="${b}"${sel(b, H.budget)}>${b ? "sub " + b + " €" : "Oricât"}</option>`).join("")}</select>`)}
          ${field("h-pax", "Persoane", "👥", `<select id="h-pax">${paxOptions()}</select>`)}
          <button class="hero-go" type="submit"><span>Caută zboruri</span> <span aria-hidden="true">→</span></button>
        </form>
        <div class="hero-row">
          <div class="hero-ideas" role="group" aria-label="Ce fel de vacanță">
            ${IDEAS.map(([k, i, l]) => `<button type="button" class="hero-chip${!H.text && H.where === k ? " on" : ""}" data-hwhere="${k}"><span aria-hidden="true">${i}</span> ${l}</button>`).join("")}
          </div>
          <div class="hero-trip" role="group" aria-label="Tip bilet">
            <button type="button" data-htrip="RT" class="${H.trip === "RT" ? "on" : ""}">Dus-întors</button><button type="button" data-htrip="OW" class="${H.trip === "OW" ? "on" : ""}">Doar dus</button>
          </div>
        </div>
      </div>`;
  }

  function resultsHtml() {
    if (H.busy) return `<div class="hero-res"><div class="hero-loading"><span class="spin"></span> Caut cele mai bune variante…</div></div>`;
    if (!H.rows) return "";
    const n = H.rows.length, shown = H.rows.slice(0, H.shown);
    const head = `<div class="hero-res-h"><div><h3>${n ? `${n} ${n === 1 ? "variantă" : "variante"}` : "Nicio variantă"}</h3><p class="muted">${esc(H.label)} · ${H.trip === "RT" ? "dus-întors" : "doar dus"}, de persoană, de la cel mai ieftin</p></div>
      <button type="button" class="btn small ghost" id="hero-close">✕ Închide</button></div>`;
    if (!n) return `<div class="hero-res" id="hero-results">${head}<div class="empty">Nu am găsit zboruri pentru alegerile tale. Încearcă alt buget, altă lună sau „Oriunde”.</div></div>`;
    const cards = shown.map(r => flightCard(r, r.region ? { region: r.region_label, season: bestSeason(r.dest) } : {})).join("");
    const more = n > H.shown ? `<div class="hero-more"><button type="button" class="btn" id="hero-more">Arată mai multe (${n - H.shown})</button></div>` : "";
    return `<div class="hero-res" id="hero-results">${head}<div class="hero-grid">${cards}</div>${more}</div>`;
  }

  function render() {
    let el = $("#hero");
    if (!el) {
      el = document.createElement("section");
      el.id = "hero"; el.className = "hero";
      const anchor = $("#trust") || $(".tabs");
      anchor.before(el);
    }
    ddClose();
    el.innerHTML = formHtml() + resultsHtml();
    ddEnhance();
    slidesMount();
  }

  // ---------- meniuri proprii în locul listelor clasice ale browserului: un click oriunde pe câmp le deschide ----------
  let DD = null; // {sel, menu, back}
  function ddEnhance() {
    for (const sel of document.querySelectorAll(".hf select")) {
      sel.classList.add("hf-native"); sel.tabIndex = -1;
      const b = document.createElement("button");
      b.type = "button"; b.className = "hf-btn"; b.dataset.for = sel.id;
      b.setAttribute("aria-haspopup", "listbox"); b.setAttribute("aria-expanded", "false");
      b.innerHTML = `<span class="hf-t">${esc(sel.selectedOptions[0]?.text || "")}</span><svg class="hf-chev" viewBox="0 0 12 8" aria-hidden="true"><path d="M1 1.5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
      sel.after(b);
    }
  }
  function ddClose() {
    if (!DD) return;
    const { menu, back, btn } = DD; DD = null;
    btn?.setAttribute("aria-expanded", "false"); btn?.closest(".hf")?.classList.remove("open");
    menu.classList.remove("in"); back?.classList.remove("in");
    setTimeout(() => { menu.remove(); back?.remove(); }, 160);
  }
  function ddOpen(btn) {
    const sel = document.getElementById(btn.dataset.for), field = btn.closest(".hf");
    if (DD && DD.sel === sel) return ddClose();
    ddClose();
    const sheet = innerWidth <= 560;
    const menu = document.createElement("div");
    menu.className = "hdd" + (sheet ? " sheet" : ""); menu.setAttribute("role", "listbox");
    const title = field.querySelector(".hf-l")?.textContent || "";
    menu.innerHTML = (sheet ? `<div class="hdd-h">${esc(title)}</div>` : "") + [...sel.options].map(o =>
      `<button type="button" role="option" class="hdd-o${o.selected ? " on" : ""}" aria-selected="${o.selected}" data-v="${esc(o.value)}"><span>${esc(o.text)}</span><svg viewBox="0 0 16 12" aria-hidden="true"><path d="M1.5 6.5l4 4 9-9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>`).join("");
    let back = null;
    if (sheet) { back = document.createElement("div"); back.className = "hdd-back"; document.body.append(back); }
    document.body.append(menu);
    if (!sheet) {
      const r = field.getBoundingClientRect(), w = Math.max(r.width, 230);
      menu.style.minWidth = w + "px";
      menu.style.left = Math.max(8, Math.min(r.left + scrollX, scrollX + innerWidth - w - 8)) + "px";
      const below = innerHeight - r.bottom, h = Math.min(menu.scrollHeight, 340);
      menu.style.top = (below < h + 16 && r.top > below ? r.top + scrollY - h - 8 : r.bottom + scrollY + 8) + "px";
    }
    DD = { sel, menu, back, btn };
    btn.setAttribute("aria-expanded", "true"); field.classList.add("open");
    void menu.offsetHeight; // pornește animația de deschidere
    menu.classList.add("in"); back?.classList.add("in");
    const cur = menu.querySelector(".hdd-o.on") || menu.querySelector(".hdd-o");
    cur?.scrollIntoView({ block: "nearest" }); cur?.focus({ preventScroll: true });
  }
  function ddPick(v) {
    const { sel, btn } = DD;
    ddClose();
    if (sel.value === v) return;
    sel.value = v;
    if (btn) btn.querySelector(".hf-t").textContent = sel.selectedOptions[0]?.text || "";
    sel.dispatchEvent(new Event("change", { bubbles: true }));
  }
  document.addEventListener("click", e => {
    const o = e.target.closest(".hdd-o");
    if (o && DD) { ddPick(o.dataset.v); return; }
    if (e.target.closest(".hdd")) return;
    const f = e.target.closest(".hf");
    const btn = f?.querySelector(".hf-btn");
    if (btn) { e.preventDefault(); ddOpen(btn); return; }
    if (DD) ddClose();
  });
  document.addEventListener("keydown", e => {
    if (!DD) return;
    if (DD.menu.classList.contains("hdp")) { if (e.key === "Escape") ddClose(); return; } // în fereastra de date: tastele normale
    const opts = [...DD.menu.querySelectorAll(".hdd-o")], i = opts.indexOf(document.activeElement);
    if (e.key === "Escape") { const b = DD.btn; ddClose(); b?.focus(); e.preventDefault(); }
    else if (e.key === "ArrowDown") { opts[Math.min(i + 1, opts.length - 1)]?.focus(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { opts[Math.max(i - 1, 0)]?.focus(); e.preventDefault(); }
    else if (e.key === "Tab") ddClose();
  });
  addEventListener("resize", () => { if (DD) ddClose(); });

  // ---------- pozele de sus care se schimbă singure (Unsplash, gratuite; legate direct de la Unsplash, mărime după ecran) ----------
  const SLIDES = ["hero-bg.jpg", // Seychelles (Wikimedia), prima ca rezervă
    "photo-1590523277543-a94d2e4eb00b", "photo-1590523277543-a94d2e4eb00b",
    "photo-1620065487644-1080510335f5", "photo-1516815231560-8f41ec531527",
    "photo-1573843981267-be1999ff37cd", "photo-1576158831003-d41033ec31fd", "photo-1467377791767-c929b5dc9a23",
    "photo-1738762932370-468a90e0ff68", "photo-1706461168280-da6986cd91ec", "photo-1652842183703-47c2f7bb8c3c",
    "photo-1580725869538-9b164c27c44f", "photo-1534008897995-27a23e859048", "photo-1506665531195-3566af2b4dfa",
    "photo-1531761535209-180857e963b9", "photo-1575999502951-4ab25b5ca889", "photo-1646668072507-b2215b873c70",
    "photo-1665449417444-fe7fec4b7425", "photo-1577717903315-1691ae25ab3f", "photo-1555400038-63f5ba517a47",
    "photo-1544644181-1484b3fdfc62", "photo-1515238152791-8216bfdf89a7", "photo-1507525428034-b723cf961d3e",
    "photo-1468413253725-0d5181091126", "photo-1437719417032-8595fd9e9dc6", "photo-1618064541372-289bdb6f5b7b",
    "photo-1617362985992-d0b6814cacef", "photo-1553829176-61484f865ac3", "photo-1596250470244-d172e7eb4054",
    "photo-1537640685236-a9df2496e232", "photo-1513415277900-a62401e19be4", "photo-1507187632231-5beb21a654a2"];
  const SL_EVERY = 7000;
  const SL_STILL = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const SL = { cur: Math.floor(Math.random() * SLIDES.length), timer: 0 };
  function slideUrl(i) {
    const id = SLIDES[i];
    if (!id.startsWith("photo-")) return innerWidth <= 560 ? "hero-bg-1280.jpg" : id;
    const box = $(".hero-in"), dpr = Math.min(devicePixelRatio || 1, 2);
    const w = box ? Math.max(box.offsetWidth, box.offsetHeight * 1.6) : innerWidth;
    const px = Math.min(2400, Math.ceil(w * dpr / 200) * 200);
    return `https://images.unsplash.com/${id}?w=${px}&q=80&auto=format&fit=crop`;
  }
  function slidesMount() { // după fiecare render: arată imediat poza curentă (fără fade)
    const [a] = document.querySelectorAll(".hero-sl i");
    if (!a) return;
    a.style.transition = "none"; a.style.backgroundImage = `url("${slideUrl(SL.cur)}")`; a.classList.add("on");
    requestAnimationFrame(() => requestAnimationFrame(() => { a.style.transition = ""; }));
    if (!SL_STILL && !SL.timer) SL.timer = setTimeout(slideNext, SL_EVERY);
  }
  function slideNext() {
    SL.timer = 0;
    if (document.hidden) { SL.timer = setTimeout(slideNext, SL_EVERY); return; }
    const next = (SL.cur + 1) % SLIDES.length, url = slideUrl(next), img = new Image();
    img.onload = () => { // schimbăm doar după ce poza s-a descărcat complet
      const els = [...document.querySelectorAll(".hero-sl i")], on = els.find(x => x.classList.contains("on")), off = els.find(x => x !== on);
      if (on && off) { off.style.backgroundImage = `url("${url}")`; off.classList.add("on"); on.classList.remove("on"); }
      SL.cur = next; SL.timer = setTimeout(slideNext, SL_EVERY);
    };
    img.onerror = () => { SL.cur = next; SL.timer = setTimeout(slideNext, 500); }; // poză indisponibilă: sărim peste
    img.src = url;
  }

  function readForm() {
    H.from = $("#h-from").value; H.when = $("#h-when").value; H.budget = +$("#h-budget").value;
    H.text = $("#h-text").value.trim();
  }

  // „Alege datele exacte…”: fereastră cu plecare + întoarcere (calendarul telefonului/browserului)
  function datePanel() {
    const field = $("#h-when")?.closest(".hf"); if (!field) return;
    ddClose();
    const f = fixed(H.when) || {}, today = iso(new Date()), max = addDays(today, 30 * ((state.status?.settings?.exotic?.months_ahead ?? 8)));
    const sheet = innerWidth <= 560, menu = document.createElement("div");
    menu.className = "hdd hdp" + (sheet ? " sheet" : "");
    menu.innerHTML = `<div class="hdd-h">Date fixe</div>
      <label class="hdp-f"><span>🛫 Plecare</span><input type="date" id="hdp-dep" min="${today}" max="${max}" value="${f.dep || ""}"></label>
      <label class="hdp-f"><span>🛬 Întoarcere <small>(lasă gol pentru doar dus)</small></span><input type="date" id="hdp-ret" min="${f.dep || today}" max="${max}" value="${f.ret || ""}"></label>
      <p class="hdp-err" id="hdp-err" hidden></p>
      <div class="hdp-b"><button type="button" class="hdp-cancel" id="hdp-cancel">Renunță</button><button type="button" class="hdp-ok" id="hdp-ok">Caută pe aceste date</button></div>`;
    let back = null;
    if (sheet) { back = document.createElement("div"); back.className = "hdd-back"; document.body.append(back); }
    document.body.append(menu);
    if (!sheet) {
      const rc = field.getBoundingClientRect(), w = 300;
      menu.style.minWidth = w + "px";
      menu.style.left = Math.max(8, Math.min(rc.left + scrollX, scrollX + innerWidth - w - 8)) + "px";
      const h = menu.scrollHeight, below = innerHeight - rc.bottom;
      menu.style.top = (below < h + 16 && rc.top > below ? rc.top + scrollY - h - 8 : rc.bottom + scrollY + 8) + "px";
    }
    DD = { sel: $("#h-when"), menu, back, btn: field.querySelector(".hf-btn") };
    field.classList.add("open");
    void menu.offsetHeight; menu.classList.add("in"); back?.classList.add("in");
    const dep = menu.querySelector("#hdp-dep"), ret = menu.querySelector("#hdp-ret"), err = menu.querySelector("#hdp-err");
    dep.addEventListener("change", () => { ret.min = dep.value || today; if (ret.value && ret.value < dep.value) ret.value = ""; });
    menu.querySelector("#hdp-cancel").onclick = () => ddClose();
    menu.querySelector("#hdp-ok").onclick = () => {
      if (!dep.value) { err.textContent = "Alege data plecării."; err.hidden = false; return; }
      if (ret.value && ret.value <= dep.value) { err.textContent = "Întoarcerea trebuie să fie după plecare."; err.hidden = false; return; }
      ddClose();
      readForm();
      H.when = `fix:${dep.value}:${ret.value || ""}`;
      H.trip = ret.value ? "RT" : "OW";
      run();
    };
    setTimeout(() => dep.focus(), 50);
  }
  document.addEventListener("change", e => {
    if (e.target.id === "h-when" && e.target.value === "pick") {
      e.target.value = H.when;
      const t = e.target.closest(".hf")?.querySelector(".hf-t"); if (t) t.textContent = e.target.selectedOptions[0]?.text || "Oricând";
      datePanel();
    }
  });
  document.addEventListener("change", e => {
    if (e.target.id !== "h-pax") return;
    const [a, c, i] = e.target.value.split("-").map(Number);
    readForm(); state.adults = a; state.children = c; state.infants = i;
    setPax("adults", 0); // salvează, actualizează „👤” de jos și restul paginii (+ căutarea de sus, prin înlocuirea de mai jos)
  });
  // și când schimbi persoanele din „👤” de jos, căutarea de sus se actualizează
  const setPaxApp = window.setPax;
  window.setPax = (k, d) => { setPaxApp(k, d); if ($("#hero")) render(); };
  document.addEventListener("submit", e => {
    if (e.target.id !== "hero-form") return;
    e.preventDefault(); readForm(); run();
  });
  document.addEventListener("click", e => {
    const w = e.target.closest("[data-hwhere]"), t = e.target.closest("[data-htrip]");
    if (w) { readForm(); H.where = w.dataset.hwhere; H.text = ""; run(); return; }
    if (t) { readForm(); H.trip = t.dataset.htrip; if (H.rows) run(); else render(); return; }
    if (e.target.closest("#hero-more")) { H.shown += PAGE; render(); return; }
    if (e.target.closest("#hero-close")) { H.rows = null; render(); }
  });

  // ---------- subsolul: cifre live + sfaturi de călătorie ----------
  const TIPS = [
    "Bagajul mic de sub scaun e inclus la Wizz Air și Ryanair; trollerul de cabină se plătește separat.",
    "La Ryanair, check-in-ul online e gratuit; la aeroport te costă o taxă.",
    "Cardul european de sănătate (CEAM) e gratuit de la CNAS și te acoperă în UE pentru urgențe.",
    "Pentru Asia, Africa sau America, pașaportul trebuie de regulă să fie valabil încă 6 luni de la intrare.",
    "În UE poți călători doar cu buletinul, dar pentru Marea Britanie îți trebuie pașaport.",
    "Prețurile low-cost cresc de obicei pe măsură ce se umplu avioanele: o ofertă bună azi poate dispărea mâine.",
    "Zborurile cu plecare dimineața devreme sau seara târziu sunt adesea mai ieftine.",
    "Pentru SUA, românii au nevoie de viză: programul Visa Waiver e suspendat pentru România.",
    "Pentru Thailanda, Maldive sau Mauritius, românii nu au nevoie de viză în avans la sejururi scurte (verifică totuși pe mae.ro înainte).",
    "Dus-întors cu două companii diferite iese uneori mai ieftin decât cu aceeași companie.",
    "Plătește în moneda companiei aeriene (de obicei euro), nu cu conversia oferită de site, ca să eviți comisioanele.",
    "Fă o poză pașaportului și buletinului și păstreaz-o în telefon sau pe email: ajută mult dacă le pierzi.",
  ];
  let tipI = Math.floor(Math.random() * TIPS.length);
  function footer() {
    const t = $("#sf-tip"); if (t) t.textContent = TIPS[tipI % TIPS.length];
    api("/api/deals").then(rows => {
      if (!Array.isArray(rows) || !rows.length || !$("#sf-nums")) return;
      const dests = new Set(rows.map(r => r.dest)), ctr = new Set(rows.map(r => r.country).filter(Boolean));
      const fmt = n => n.toLocaleString("ro-RO");
      $("#sf-nums").innerHTML = `<div><b>${fmt(rows.length)}</b><span>oferte găsite</span></div><div><b>${fmt(dests.size)}</b><span>destinații</span></div><div><b>${fmt(ctr.size)}</b><span>țări</span></div>`;
      const c = rows.filter(r => r.days_to_dep >= 1).sort((a, b) => a.price_eur - b.price_eur)[0];
      if (c) $("#sf-cheap").innerHTML = `Cel mai ieftin zbor acum: <b>${esc(c.origin_name)} → ${esc(c.dest_name)}</b> cu <b>${Math.round(c.price_eur)} €</b> ${c.trip === "RT" ? "dus-întors" : "doar dus"}.`;
    }).catch(() => {});
  }
  document.addEventListener("click", e => { if (e.target.closest("#sf-next")) { tipI++; $("#sf-tip").textContent = TIPS[tipI % TIPS.length]; } });
  footer();

  // prima afișare, după ce aplicația a încărcat orașele (status)
  const start = () => {
    if (!state.status) return setTimeout(start, 300);
    H.from = state.origin || "ALL";
    render();
  };
  start();
})();
