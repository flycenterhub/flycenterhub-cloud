"use strict";

const $ = (s, el = document) => el.querySelector(s);
// Site-ul public (GitHub Pages): fără server, datele vin din data/*.json prin static-api.js
const STATIC = !!window.STATIC_SITE;
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const MONTHS = ["ian", "feb", "mar", "apr", "mai", "iun", "iul", "aug", "sep", "oct", "nov", "dec"];
const WDAYS = ["dum", "lun", "mar", "mie", "joi", "vin", "sâm"];
const ORIGIN_NAMES = { TSR: "Timișoara", BUD: "Budapesta", OMR: "Oradea", CLJ: "Cluj-Napoca", OTP: "București" };
const FLAGS = {
  SUB_MEDIE: { icon: "📉", label: "Mult sub prețul obișnuit", hot: true },
  MINIM: { icon: "🏆", label: "Cel mai mic preț văzut", hot: true },
  SCADERE: { icon: "⬇️", label: "Preț scăzut recent", hot: true },
  SUPER: { icon: "🔥", label: "Super ieftin" },
  LAST_MINUTE: { icon: "⏰", label: "Last minute" },
};

const state = {
  tab: "deals", origin: "ALL", trip: "ALL", max: "", q: "", sort: "best", days: 10,
  dep: "", ret: "", flex: 0, exact: true, pax: 1, adults: 1, children: 0, infants: 0, search: [], searchLoading: false, exotic: null, exRegion: "ALL", openShelves: new Set(), favs: loadFavs(),
  status: null, deals: [], lm: [], dest: [], posts: [], lastScanId: null, wasRunning: false,
};

/* ---------- datele călătoriei ---------- */
function isoAdd(iso, n) {
  const d = d0(iso);
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function todayIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function dateWindow() {
  if (!state.dep) return null;
  const f = state.flex;
  const w = { depFrom: isoAdd(state.dep, -f), depTo: isoAdd(state.dep, f), retFrom: "", retTo: "" };
  if (w.depFrom < todayIso()) w.depFrom = todayIso();
  if (state.ret) { w.retFrom = isoAdd(state.ret, -f); w.retTo = isoAdd(state.ret, f); }
  return w;
}
function datesInvalid() { return state.dep && state.ret && state.ret < state.dep; }
function datesLabel() {
  if (!state.dep) return "";
  const fx = state.flex ? ` (±${state.flex} ${state.flex === 1 ? "zi" : "zile"})` : "";
  return state.ret ? `${fmtDate(state.dep)} → ${fmtDate(state.ret)}${fx}` : `${fmtDate(state.dep)}${fx}, doar dus`;
}

/* ---------- utilitare ---------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function d0(iso) { return new Date(iso.slice(0, 10) + "T00:00:00"); }
function fmtDate(iso, withDay = true) {
  if (!iso) return "";
  const d = d0(iso);
  const s = `${d.getDate()} ${MONTHS[d.getMonth()]}`;
  return withDay ? `${WDAYS[d.getDay()]} ${s}` : s;
}
function eur(v) {
  if (v == null) return "–";
  return (v < 100 ? v.toFixed(2).replace(".", ",") : Math.round(v).toLocaleString("ro-RO")) + " €";
}
function fmtLei(v) {
  if (v == null) return "–";
  return v.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " lei";
}
function lei(vEur) { return fmtLei(vEur * (state.status?.eur_ron || 5)); }
function bnrLabel() {
  const f = state.status?.fx;
  return f?.date ? `cursul BNR din ${fmtDate(f.date, false)} (1 € = ${f.eur_ron.toLocaleString("ro-RO", { minimumFractionDigits: 4 })} lei)` : "cursul BNR";
}
function leiSpan(r) {
  const v = r.price_ron ?? (r.price_eur * (state.status?.eur_ron || 5));
  const title = r.lei_exact ? "Prețul oficial în lei al companiei aeriene" : `Convertit la ${bnrLabel()}`;
  return `<span class="lei num" title="${esc(title)}">${fmtLei(v)}${r.lei_exact ? " ✓" : ""}</span>`;
}
function inDays(n) {
  if (n <= 0) return "azi";
  if (n === 1) return "mâine";
  return `în ${n} zile`;
}
function ago(ts) {
  if (!ts) return "";
  const m = Math.round((Date.now() - new Date(ts.replace(" ", "T")).getTime()) / 60000);
  if (m < 1) return "acum";
  if (m < 60) return `acum ${m} min`;
  const h = Math.round(m / 60);
  if (h < 24) return `acum ${h} ${h === 1 ? "oră" : "ore"}`;
  const d = Math.round(h / 24);
  return `acum ${d} ${d === 1 ? "zi" : "zile"}`;
}
function hhmm(ts) { return ts ? ts.slice(11, 16) : ""; }
function tripLabel(r) { return r.trip === "RT" ? "dus-întors" : "dus"; }
function whenText(r) {
  if (r.trip === "RT") return `${fmtDate(r.dep_date)} → ${fmtDate(r.ret_date)} · ${r.nights} ${r.nights === 1 ? "noapte" : "nopți"}`;
  return `${fmtDate(r.dep_date)}${r.dep_time ? " · " + r.dep_time : ""}`;
}
async function api(path) {
  if (STATIC) return window.staticApi(path);
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
async function post(path) {
  const r = await fetch(path, { method: "POST", headers: { "X-Zboruri": "1" } });
  return r.json();
}
function unverified(r) {
  return r.source === "aviasales" || r.out?.source === "aviasales" || r.back?.source === "aviasales";
}
function unvBadge(r) {
  if (r.source === "google") return `<span class="badge real" title="Preț real confirmat pe Google Flights">✅ Preț real · Google Flights</span>`;
  return unverified(r) ? `<span class="badge unv" title="Preț găsit recent în căutările altor călători, nu direct de la companie. Confirmă-l pe Google Flights sau pe celelalte site-uri de pe card sau „Compară prețul live”.">🔎 De verificat</span>` : "";
}
function badges(flags, isNew) {
  const out = [];
  if (isNew) out.push(`<span class="badge new">NOU</span>`);
  for (const f of (flags || "").split(",").filter(Boolean)) {
    const x = FLAGS[f];
    if (x) out.push(`<span class="badge${x.hot ? " hot" : ""}">${x.icon} ${x.label}</span>`);
  }
  return out.join("");
}

/* ---------- pasageri: adulți, copii, bebeluși (ca pe site-urile companiilor) ---------- */
function seats() { return (state.adults || 1) + (state.children || 0); }  // cei care au nevoie de loc
function paxLabel() {
  const a = state.adults, c = state.children, i = state.infants;
  const parts = [`${a} ${a === 1 ? "adult" : "adulți"}`];
  if (c) parts.push(`${c} ${c === 1 ? "copil" : "copii"}`);
  if (i) parts.push(`${i} ${i === 1 ? "bebeluș" : "bebeluși"}`);
  return parts.join(", ");
}
/* ---------- Google Flights: link direct pe rezultatele pentru ruta, datele și pasagerii exacți ---------- */
const CITY_AIRPORTS = { BJS: "PEK,PKX", SHA: "PVG,SHA", TYO: "NRT,HND", OSA: "KIX,ITM", SEL: "ICN,GMP", BKK: "BKK,DMK",
  NYC: "JFK,EWR,LGA", WAS: "IAD,DCA,BWI", CHI: "ORD,MDW", LON: "LHR,LGW,STN,LTN", PAR: "CDG,ORY", ROM: "FCO,CIA",
  MIL: "MXP,LIN,BGY", MOW: "SVO,DME,VKO", STO: "ARN,BMA", BUH: "OTP", IST: "IST,SAW", DXB: "DXB,DWC", TCI: "TFS,TFN",
  RIO: "GIG,SDU", SAO: "GRU,CGH,VCP", BUE: "EZE,AEP", YTO: "YYZ,YTZ", YMQ: "YUL", JKT: "CGK,HLP", KUL: "KUL,SZB", TPE: "TPE,TSA" };
function pbVarint(n) { const o = []; do { let b = n & 0x7f; n = Math.floor(n / 128); o.push(b | (n ? 0x80 : 0)); } while (n); return o; }
function pb(field, v) {
  if (typeof v === "number") return [...pbVarint(field << 3), ...pbVarint(v)];
  const data = typeof v === "string" ? [...new TextEncoder().encode(v)] : v;
  return [...pbVarint(field << 3 | 2), ...pbVarint(data.length), ...data];
}
function gfAirports(field, code) { return (CITY_AIRPORTS[code] || code).split(",").flatMap(a => pb(field, [...pb(1, 1), ...pb(2, a)])); }
function gfPax(a, c, i) { return [...Array(a).fill(1), ...Array(c).fill(2), ...Array(i).fill(4)].flatMap(k => pb(8, k)); }
function b64url(bytes) { return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
window.gfLink = function (o, d, dep, ret, a = 1, c = 0, i = 0) {
  const legs = [[dep, o, d], ...(ret ? [[ret, d, o]] : [])];
  const t = [...pb(1, 28), ...pb(2, 2), ...legs.flatMap(([day, x, y]) => pb(3, [...pb(2, day), ...gfAirports(13, x), ...gfAirports(14, y)])),
    ...gfPax(a, c, i), ...pb(9, 1), ...pb(14, 1), ...pb(19, ret ? 1 : 2)];
  return `https://www.google.com/travel/flights/search?tfs=${b64url(t)}&hl=ro&gl=ro&curr=EUR`;
};
// schimbă pasagerii într-un link Google Flights existent (câmpul 8 din „tfs”)
function gfWithPax(url, a, c, i) {
  try {
    const u = new URL(url), t = u.searchParams.get("tfs");
    if (!t) return url;
    const b = Uint8Array.from(atob(t.replace(/-/g, "+").replace(/_/g, "/")), ch => ch.charCodeAt(0));
    const out = [];
    let p = 0, paxAt = -1;
    const varint = () => { let n = 0, m = 1, x; do { x = b[p++]; n += (x & 0x7f) * m; m *= 128; } while (x & 0x80); return n; };
    while (p < b.length) {
      const start = p, key = varint(), wt = key & 7;
      if (wt === 0) varint(); else if (wt === 2) { const len = varint(); p += len; } else return url;
      if (key >> 3 === 8) { if (paxAt < 0) paxAt = out.length; continue; }
      if (paxAt < 0 && key >> 3 === 9) paxAt = out.length;
      out.push(...b.slice(start, p));
    }
    out.splice(paxAt < 0 ? out.length : paxAt, 0, ...gfPax(a, c, i));
    u.searchParams.set("tfs", b64url(out));
    return u.toString();
  } catch (e) { return url; }
}
function paxLink(url) {
  const a = state.adults || 1, c = state.children || 0, i = state.infants || 0;
  if (!url || (a === 1 && !c && !i)) return url;
  if (/wizzair\.com\/.+\/booking\//.test(url)) return url.replace(/\/1\/0\/0\/null$/, `/${a}/${c}/${i}/null`);
  if (/flypgs\.com/.test(url)) return url.replace(/adultCount=\d+&childCount=\d+&infantCount=\d+/, `adultCount=${a}&childCount=${c}&infantCount=${i}`);
  if (/ryanair\.com/.test(url)) return url.replace(/([?&])adults=1&teens=0&children=0&infants=0/, `$1adults=${a}&teens=0&children=${c}&infants=${i}`);
  if (/skyscanner\./.test(url)) return url.replace(/adults=1/, `adults=${a}`) + (c || i ? `&childrenv2=${[...Array(c).fill(8), ...Array(i).fill(1)].join("|")}` : "");
  if (/kayak\.com|momondo\./.test(url)) {
    const kids = [...Array(c).fill("11"), ...Array(i).fill("1S")];
    return url.replace(/\?sort=/, `/${a}adults${kids.length ? "/children-" + kids.join("-") : ""}?sort=`);
  }
  if (/kiwi\.com/.test(url)) return url + `&adults=${a}&children=${c}&infants=${i}`;
  if (/google\.com\/travel\/flights/.test(url) && /[?&]tfs=/.test(url)) return gfWithPax(url, a, c, i);
  if (/flighthub\.com/.test(url)) return url.replace(/num_adults=1&num_children=0&num_infants=0&num_infants_lap=0/, `num_adults=${a}&num_children=${c}&num_infants=0&num_infants_lap=${i}`);
  return url;
}
function paxTotal(r) {
  const n = seats(), inf = state.infants || 0;
  if (n === 1 && !inf) return "";
  const lei = (r.price_ron ?? r.price_eur * (state.status?.eur_ron || 5)) * n;
  return `<div class="pax-total">👥 ${esc(paxLabel())}: <b>${eur(r.price_eur * n)}</b> · ${fmtLei(lei)}${inf ? ` <span class="muted">+ taxa bebeluș</span>` : ""}</div>`;
}
function renderPax() {
  $("#pax-btn").textContent = `👤 ${paxLabel()} ▾`;
  for (const row of $$(".pax-row")) {
    const k = row.dataset.k, v = state[k];
    row.querySelector("output").textContent = v;
    const [minus, plus] = row.querySelectorAll("button");
    minus.disabled = k === "adults" ? v <= 1 : v <= 0;
    plus.disabled = k === "infants" ? v >= state.adults : seats() >= 9;
  }
}
function setPax(k, d) {
  state[k] = Math.max(k === "adults" ? 1 : 0, (state[k] || 0) + d);
  if (seats() > 9) state[k] -= seats() - 9;
  if (state.infants > state.adults) state.infants = state.adults;
  state.pax = seats();
  try { localStorage.setItem("paxv2", JSON.stringify({ a: state.adults, c: state.children, i: state.infants })); } catch (e) { /* ignorat */ }
  renderPax();
  renderAll();
}

/* ---------- butoanele „Rezervă la <companie>” ---------- */
function carrierOf(link, airline) {
  if (/wizzair\.com/.test(link || "")) return "Wizz Air";
  if (/ryanair\.com/.test(link || "")) return "Ryanair";
  if (/flypgs\.com/.test(link || "")) return "Pegasus";
  return (airline || "").split(" · ")[0].split(" + ")[0].trim();
}
function isDeepLink(link) { return /wizzair\.com\/.+\/booking\/|ryanair\.com\/.+\/trip\/flights|flypgs\.com\/booking/.test(link || ""); }
function gfBooking(link) {
  if (!/^gfpost:/.test(link || "")) return null;
  try { return JSON.parse(link.slice(7)); } catch (e) { return null; }
}
/* ---------- statistici (GoatCounter, doar pe site-ul public, fără cookie-uri) ---------- */
function gcEvent(path) {
  try { if (STATIC && window.goatcounter && goatcounter.count) goatcounter.count({ path, title: path, event: true }); } catch (e) { /* ignorat */ }
}
document.addEventListener("click", e => {
  const b = e.target.closest(".book, #btn-surprise");
  if (!b) return;
  if (b.id === "btn-surprise") return gcEvent("surprinde-ma");
  const c = b.closest(".card");
  const r = c && c.querySelector(".fc-route");
  gcEvent("rezerva: " + (r ? r.textContent.trim().replace(/\s+/g, " ") : "zbor"));
}, true);
function bookBtn(link, airline, prefix = "Rezervă") {
  if (!link) return "";
  const g = gfBooking(link);
  if (g) {
    // rezervarea exactă a zborului, prin Google Flights, la vânzătorul cu cel mai bun preț
    const inputs = [...new URLSearchParams(g.post || "")].map(([k, v]) => `<input type="hidden" name="${esc(k)}" value="${esc(v)}">`).join("");
    const who = g.with || carrierOf("", airline);
    return `<form class="book-form" action="${esc(g.url)}" method="post" target="_blank" rel="noopener">${inputs}` +
      `<button type="submit" class="btn small book" title="${esc(`Se deschide rezervarea pentru exact acest zbor${who ? " la " + who : ""}, la prețul real`)}">${esc(prefix)} ↗</button></form>`;
  }
  link = paxLink(link);
  const who = carrierOf(link, airline);
  const title = isDeepLink(link) ? `Se deschide exact acest zbor pe site-ul ${who}, la prețul real`
    : "Se deschide Google Flights pe ruta și data exactă: prețul real de acum și cea mai bună ofertă";
  return `<a class="btn small book" href="${esc(link)}" target="_blank" rel="noopener" title="${esc(title)}">${esc(prefix)} ↗</a>`;
}

/* ---------- verificare live și ora verificării ---------- */
function checkedLabel(ts) {
  if (!ts) return "";
  const d = ts.slice(0, 10), t = ts.slice(11, 16);
  const day = d === todayIso() ? "azi" : d === isoAdd(todayIso(), -1) ? "ieri" : fmtDate(d, false);
  return `🕒 verificat ${day} la ${t}`;
}
function legsFor(r) {
  if (r.out) {
    const legs = [{ source: r.out.source, origin: r.origin, dest: r.dest, date: r.out.date }];
    if (r.back) legs.push({ source: r.back.source, origin: r.dest, dest: r.origin, date: r.back.date });
    return legs;
  }
  const legs = [{ source: r.source, origin: r.origin, dest: r.dest, date: r.dep_date }];
  if (r.ret_date) legs.push({ source: r.source, origin: r.dest, dest: r.origin, date: r.ret_date });
  return legs;
}
function verifyBtn(r, icon = false) {
  if (!STATIC && unverified(r) && state.status?.serpapi?.enabled) {
    const q = { origin: r.origin, dest: r.dest, dep: r.dep_date, ret: r.ret_date || "", adults: state.adults, children: state.children, infants: state.infants };
    return `<button class="btn small ghost verify${icon ? " fc-icon" : ""}" data-gfcheck="${esc(JSON.stringify(q))}" title="Verifică prețul real pe Google Flights (1 din căutările lunare SerpApi)" aria-label="Verifică prețul real">✅${icon ? "" : `<span class="lbl-long"> Verifică prețul real</span><span class="lbl-short"> Real</span>`}</button>`;
  }
  const legs = legsFor(r);
  // pe site-ul public se poate verifica doar Ryanair (Wizz Air nu permite cereri din alte site-uri)
  if (!legs.every(l => STATIC ? l.source === "ryanair" : (l.source === "wizzair" || l.source === "ryanair"))) return "";
  return `<button class="btn small ghost verify${icon ? " fc-icon" : ""}" data-verify="${esc(JSON.stringify(legs))}" title="Verifică prețul acum, direct la companie (și câte locuri mai sunt)" aria-label="Verifică prețul acum">🔄${icon ? "" : `<span class="lbl-long"> Verifică prețul acum</span><span class="lbl-short"> Verifică</span>`}</button>`;
}
function srcName(src) {
  return src === "google" ? "Google Flights" : src === "wizzair" ? "Wizz Air" : src === "ryanair" ? "Ryanair" : src === "mixed" ? "companii" : "companie";
}
function compareLinks(r) {
  const o = r.origin, d = r.dest, dep = r.dep_date, ret = r.ret_date || "";
  const yymmdd = s => s.slice(2).replace(/-/g, "");
  const dmy = s => s.split("-").reverse().join("-");
  const links = [
    ["Google Flights", r.gf_link],
    ["Skyscanner", `https://www.skyscanner.ro/transport/zboruri/${o.toLowerCase()}/${d.toLowerCase()}/${yymmdd(dep)}/${ret ? yymmdd(ret) + "/" : ""}?adults=1&currency=EUR`],
    ["Kayak", `https://www.kayak.com/flights/${o}-${d}/${dep}${ret ? "/" + ret : ""}?sort=price_a`],
    ["Momondo", `https://www.momondo.ro/flight-search/${o}-${d}/${dep}${ret ? "/" + ret : ""}?sort=price_a`],
    ["Kiwi", `https://www.kiwi.com/deep?from=${o}&to=${d}&departure=${dmy(dep)}${ret ? "&return=" + dmy(ret) : ""}&lang=ro&currency=EUR`],
    ["FlightHub", `https://www.flighthub.com/flight/search?seg0_from=${o}&seg0_to=${d}&seg0_date=${dep}` +
      (ret ? `&seg1_from=${d}&seg1_to=${o}&seg1_date=${ret}&type=roundtrip` : "&type=oneway") +
      "&num_adults=1&num_children=0&num_infants=0&num_infants_lap=0&seat_class=Economy"],
  ];
  return `<div class="compare"><button class="cmp-toggle" type="button">🔎 Compară prețul live</button><span class="cmp-links"> ${links.map(([n, u]) => `<a href="${esc(paxLink(u))}" target="_blank" rel="noopener">${n}</a>`).join(" · ")}</span></div>`;
}
function freshness(r) {
  const src = r.source || r.out?.source;
  if (src === "aviasales" || r.out?.source === "aviasales") {
    const who = carrierOf(r.link, r.airline);
    const how = isDeepLink(r.link) ? `„Rezervă” deschide exact acest zbor pe site-ul ${who}, la prețul real`
      : "„Rezervă” îți arată prețul real de acum și cea mai bună ofertă pentru acest zbor";
    return `<div class="fresh warn" title="Preț găsit recent în căutările altor călători. Confirmă prețul exact înainte de plată.">ℹ️ Preț găsit recent · ${esc(how)}</div>`;
  }
  const ts = r.last_seen || r.checked_at;
  if (src === "google") {
    const g = gfBooking(r.link);
    return ts ? `<div class="fresh">✅ ${checkedLabel(ts).replace("🕒 verificat", "confirmat")} · „Rezervă” deschide exact acest zbor${g?.with ? " la " + esc(g.with) : ""}</div>` : "";
  }
  return ts ? `<div class="fresh">${checkedLabel(ts)} direct la ${esc(srcName(src))}</div>` : "";
}
// rezultatul verificării — modelul „card cu iconiță”: antet (iconiță + titlu + sursă/oră), preț mare, locuri rămase
const VR_ICONS = {
  good: '<path d="M5 12.5l4.2 4.2L19 7"/>',
  down: '<path d="M12 5v14M6 13l6 6 6-6"/>',
  up: '<path d="M12 19V5M6 11l6-6 6 6"/>',
  bad: '<path d="M7 7l10 10M17 7L7 17"/>',
  warn: '<path d="M12 7.5v6"/><path d="M12 16.8v.2"/>',
};
function vrIcon(kind) {
  if (kind === "loading") return `<span class="vr-ico loading"><span class="vr-spin"></span></span>`;
  return `<span class="vr-ico ${kind}"><svg viewBox="0 0 24 24" aria-hidden="true">${VR_ICONS[kind] || VR_ICONS.warn}</svg></span>`;
}
function vrBox(res, kind, title, sub = "", body = "") {
  const tone = kind === "down" ? "good" : kind === "up" ? "warn" : kind;
  res.className = `verify-res vr ${tone}`;
  res.innerHTML = `<div class="vr-head">${vrIcon(kind)}<div class="vr-hd"><div class="vr-title">${esc(title)}</div>` +
    `${sub ? `<div class="vr-sub">${esc(sub)}</div>` : ""}</div></div>${body}`;
}
function vrPrice(eurV, ronV, old, note = "") {
  let delta = "";
  if (old != null && Math.abs(eurV - old) >= 0.01) {
    const d = eurV - old;
    delta = `<span class="vr-delta ${d > 0 ? "up" : "down"}">${d > 0 ? "+" : "−"}${eur(Math.abs(d))}</span>`;
  }
  return `<div class="vr-price"><span class="vr-amount">${eur(eurV)}</span>${ronV != null ? `<span class="vr-lei">${fmtLei(ronV)}</span>` : ""}` +
    `${old != null ? `<s class="vr-old">${eur(old)}</s>` : ""}${delta}</div>${note ? `<div class="vr-note">${note}</div>` : ""}`;
}
function verifyExtra(r) {
  const out = [];
  if (r.seats != null) {
    const max = r.seats_max || 9, n = Math.min(r.seats, max), few = r.seats <= 3;
    const txt = r.seats >= max ? `${max}+ locuri la acest preț` : r.seats === 1 ? "Ultimul loc la acest preț" : `Doar ${r.seats} locuri la acest preț`;
    const bars = Array.from({ length: max }, (_, i) => `<i class="${i < n ? "on" : ""}"></i>`).join("");
    out.push(`<div class="vr-seats${few ? " few" : ""}" title="${r.seats < max ? "După ce se ocupă aceste locuri, prețul crește" : "Sunt suficiente locuri la acest preț"}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 11V6.5A2.5 2.5 0 0 1 9.5 4h5A2.5 2.5 0 0 1 17 6.5V11"/><path d="M4 12.5a2 2 0 0 1 4 0V15h8v-2.5a2 2 0 0 1 4 0V19H4z"/><path d="M6 19v2M18 19v2"/></svg>` +
      `<span class="vr-seats-t">${txt}</span><span class="vr-meter" title="${r.seats >= max ? max + "+" : r.seats} din ${max}">${bars}</span></div>`);
  }
  if ((r.pax || 1) > 1 && r.pax_total_eur != null) {
    const more = r.pax_price_eur > r.price_eur + 0.01;
    out.push(`<div class="vr-group${more ? " few" : ""}"><span>Total pentru ${r.pax} persoane</span><b>${eur(r.pax_total_eur)}</b><span class="vr-lei">${fmtLei(r.pax_total_ron)}</span>` +
      `${more ? `<div class="vr-note">La ${eur(r.price_eur)} nu mai sunt ${r.pax} locuri: pentru grup prețul e ${eur(r.pax_price_eur)} de persoană.</div>` : ""}</div>`);
  }
  return out.join("");
}
// unde apare rezultatul verificării: în card, sau pe un rând propriu sub zborul din tabel
function resBox(btn) {
  const tr = btn.closest("tr");
  if (tr) {
    let next = tr.nextElementSibling;
    if (!next || !next.classList.contains("vr-row")) {
      next = document.createElement("tr");
      next.className = "vr-row";
      next.innerHTML = `<td colspan="${tr.children.length}"><div class="verify-res"></div></td>`;
      tr.after(next);
    }
    return next.querySelector(".verify-res");
  }
  const box = btn.closest(".card, .list-row");
  let res = box.querySelector(".verify-res");
  if (!res) { res = document.createElement("div"); res.className = "verify-res"; box.appendChild(res); }
  return res;
}
async function runGfCheck(btn) {
  const res = resBox(btn);
  const iconBtn = btn.classList.contains("fc-icon"), iconTxt = btn.textContent;
  btn.disabled = true; btn.textContent = iconBtn ? "…" : "Caut pe Google Flights…";
  vrBox(res, "loading", "Se verifică prețul", "pe Google Flights…");
  try {
    const r = await fetch("/api/gfcheck", { method: "POST", headers: { "X-Zboruri": "1", "Content-Type": "application/json" },
      body: btn.dataset.gfcheck }).then(x => x.json());
    const now = new Date().toTimeString().slice(0, 5);
    if (!r.ok) vrBox(res, "warn", "Nu am putut verifica acum", r.error === "no_key" ? "Adaugă cheia SerpApi în config.json" : "Încearcă din nou peste un minut");
    else if (!r.found) vrBox(res, "bad", "Zbor indisponibil", `Google Flights · acum ${now}`, `<div class="vr-note">Nu există zboruri pe această rută și dată.</div>`);
    else {
      vrBox(res, "good", "Preț real confirmat", `Google Flights · acum ${now}`,
        vrPrice(r.price_eur, null, null, `de persoană${r.airline ? " · " + esc(r.airline) : ""} · căutări folosite: ${r.used}/${r.limit}`) +
        `<a class="btn small book vr-book" href="${esc(r.url)}" target="_blank" rel="noopener">Rezervă ↗</a>`);
      setTimeout(loadData, 2500);
    }
  } catch (e) { vrBox(res, "warn", "Aplicația nu a răspuns", "Verifică dacă e pornită"); }
  btn.disabled = false; btn.textContent = iconBtn ? iconTxt : "✅ Verifică din nou";
}
async function runVerify(btn) {
  const box = btn.closest(".card, tr, .list-row");
  const res = resBox(btn);
  const legs = JSON.parse(btn.dataset.verify);
  const who = legs.every(l => l.source === legs[0].source) ? srcName(legs[0].source) : "companii";
  const iconBtn = btn.classList.contains("fc-icon"), iconTxt = btn.textContent;
  btn.disabled = true; btn.textContent = iconBtn ? "…" : "Se verifică…";
  vrBox(res, "loading", "Se verifică prețul", `direct la ${who}…`);
  try {
    const r = STATIC ? await window.staticVerify(legs, seats()) : await fetch("/api/verify", {
      method: "POST", headers: { "X-Zboruri": "1", "Content-Type": "application/json" },
      body: JSON.stringify({ legs, pax: seats() }),
    }).then(x => x.json());
    const now = new Date().toTimeString().slice(0, 5);
    const sub = `la ${who} · acum ${now}`;
    if (!r.ok) {
      vrBox(res, "warn", "Nu am putut verifica acum", "Încearcă din nou peste un minut");
    } else if (!r.available) {
      vrBox(res, "bad", "Zbor indisponibil", sub, `<div class="vr-note">Nu mai sunt locuri la această dată.</div>`);
    } else {
      const pEl = box.querySelector(".price, .strong, .list-row .p");
      const leiEl = box.querySelector(".lei");
      if (pEl && pEl.classList.contains("p")) pEl.innerHTML = `${eur(r.price_eur)}<br><span class="muted" style="font-size:12px;font-weight:600">${fmtLei(r.price_ron)}</span>`;
      else if (pEl) pEl.textContent = eur(r.price_eur);
      if (leiEl) leiEl.textContent = fmtLei(r.price_ron) + (r.lei_exact ? " ✓" : "");
      const fresh = box.querySelector(".fresh");
      if (fresh) fresh.textContent = `✓ verificat acum la ${now}`;
      const extra = verifyExtra(r);
      if (r.changed && r.old_price_eur != null) {
        const up = r.price_eur > r.old_price_eur;
        vrBox(res, up ? "up" : "down", up ? "Prețul a crescut" : "Prețul a scăzut", sub, vrPrice(r.price_eur, r.price_ron, r.old_price_eur) + extra);
      } else {
        vrBox(res, "good", "Preț confirmat", sub, vrPrice(r.price_eur, r.price_ron, null, "Prețul e același ca pe platformă") + extra);
      }
    }
  } catch (e) {
    vrBox(res, "warn", "Aplicația nu a răspuns", "Verifică dacă e pornită");
  }
  btn.disabled = false; btn.textContent = iconBtn ? iconTxt : "🔄 Verifică din nou";
}

/* ---------- filtre ---------- */
function applyFilters(rows, ignoreDates = false, ignoreTrip = false) {
  const q = state.q.trim().toLowerCase();
  const max = parseFloat(state.max);
  const w = ignoreDates || datesInvalid() ? null : dateWindow();
  return rows.filter(r =>
    (state.origin === "ALL" || r.origin === state.origin || state.tab === "exotic") &&
    (ignoreTrip || (w ? (w.retFrom ? r.trip === "RT" : true) : (state.trip === "ALL" || r.trip === state.trip))) &&
    (!max || r.price_eur <= max) &&
    (!q || `${r.dest_name} ${r.country} ${r.dest}`.toLowerCase().includes(q)) &&
    (!w || (r.dep_date >= w.depFrom && r.dep_date <= w.depTo &&
            (!w.retFrom || (r.ret_date >= w.retFrom && r.ret_date <= w.retTo)))));
}
function datesBanner(what) {
  if (!state.dep || datesInvalid()) return "";
  return `<div class="banner">📅 <div>${what} filtrate pe datele tale: <b>${datesLabel()}</b>. <button class="linkish" data-clear-dates>Arată toate datele</button></div></div>`;
}

/* ---------- randare: căutare pe date ---------- */
function sortByChoice(rows, mode = state.sort) {
  const price = r => r.price_eur ?? r.best ?? 9e9;
  const name = r => (r.dest_name || "").toLocaleLowerCase("ro");
  const newest = r => r.first_seen || r.newest || "";
  const by = {
    best: (a, b) => (b.score ?? -1) - (a.score ?? -1) || price(a) - price(b),
    price_asc: (a, b) => price(a) - price(b),
    price_desc: (a, b) => price(b) - price(a),
    newest: (a, b) => newest(b).localeCompare(newest(a)) || price(a) - price(b),
    date_asc: (a, b) => (a.dep_date || "").localeCompare(b.dep_date || "") || price(a) - price(b),
    date_desc: (a, b) => (b.dep_date || "").localeCompare(a.dep_date || "") || price(a) - price(b),
    discount: (a, b) => (b.discount_pct ?? -99) - (a.discount_pct ?? -99) || price(a) - price(b),
    name: (a, b) => name(a).localeCompare(name(b), "ro") || price(a) - price(b),
  }[mode] || ((a, b) => price(a) - price(b));
  return [...rows].sort(by);
}
function renderSearch() {
  const el = $("#tab-search");
  if (datesInvalid()) { el.innerHTML = `<div class="empty">Data întoarcerii trebuie să fie după data plecării.</div>`; return; }
  if (state.searchLoading && !state.search.length) { el.innerHTML = `<div class="empty">Caut zborurile…</div>`; return; }
  if (!state.search.length && !state.dep) { $("#c-search").textContent = ""; el.innerHTML = emptyState(); return; }
  const minDisc = state.status?.settings?.rules?.min_discount_pct ?? 40;
  // Fără date se aplică filtrul Dus / Dus-întors; cu date, tipul rezultă din datele alese
  const rows = sortByChoice(applyFilters(state.search, true, !!state.dep));
  $("#c-search").textContent = rows.length;
  const head = state.dep
    ? `<div class="banner">📅 <div><b>${datesLabel()}</b>: cel mai ieftin zbor ${state.ret ? "dus-întors" : "dus"} spre fiecare destinație.
        ${state.ret ? "Dusul și întorsul pot fi cu companii diferite (bilete separate)." : "Adaugă o dată de întoarcere pentru prețuri dus-întors."}
        <button class="linkish" data-clear-dates>Arată toate datele</button></div></div>`
    : `<div class="banner info">✈️ <div>Cel mai ieftin zbor spre fiecare destinație, pe <b>oricare dată</b> din următoarele ${state.status?.settings?.months_ahead ?? 4} luni.
        Dacă ai date fixe, alege-le în chenarul de mai sus și lista se filtrează.</div></div>`;
  if (!rows.length) {
    el.innerHTML = head + `<div class="empty">Nu am găsit zboruri${state.dep ? " pe aceste date" : ""}${state.origin !== "ALL" ? " din " + ORIGIN_NAMES[state.origin] : ""}.${state.dep ? " Încearcă „Flexibil ± 3 zile”." : ""}</div>`;
    return;
  }
  el.innerHTML = head + shelves("search", rows, r => searchCard(r, minDisc), ["origin", "month", "country"], "destinații");
  initShelves(el);
}
function legLine(icon, leg) {
  return `<div class="leg"><span>${icon}</span><span>${fmtDate(leg.date)}${leg.time ? " · " + leg.time : ""}</span>
    <span class="muted">${esc(leg.airline)}</span>${leg.price_eur != null ? `<span class="lp">${eur(leg.price_eur)} · ${fmtLei(leg.price_ron)}</span>` : ""}</div>`;
}
function searchCard(r) { return flightCard(r); }
function exactQ(sep = "?") { return state.exact ? `${sep}exact=1` : ""; }
function dateQuery() {
  const w = datesInvalid() ? null : dateWindow();
  const qs = new URLSearchParams();
  if (state.exact) qs.set("exact", "1");
  if (w) {
    qs.set("dep_from", w.depFrom); qs.set("dep_to", w.depTo);
    if (w.retFrom) { qs.set("ret_from", w.retFrom); qs.set("ret_to", w.retTo); }
  }
  return qs;
}
let searchSeq = 0;
async function loadSearch() {
  if (datesInvalid()) { renderSearch(); renderDest(); return; }
  const seq = ++searchSeq;
  state.searchLoading = true; renderSearch();
  try {
    const res = await api(`/api/search?${dateQuery()}`);
    if (seq !== searchSeq) return;
    state.search = res;
  } catch (e) { if (seq === searchSeq) state.search = []; }
  state.searchLoading = false;
  renderSearch(); renderDest();
}
let exoticSeq = 0;
async function loadExotic() {
  if (datesInvalid()) { renderExotic(); return; }
  const seq = ++exoticSeq;
  try {
    const res = await api(`/api/exotic?${dateQuery()}`);
    if (seq === exoticSeq) state.exotic = res;
  } catch (e) { /* ignorat */ }
  renderExotic();
}

/* ---------- randare: exotice ---------- */
function renderExotic() {
  const el = $("#tab-exotic");
  const ex = state.exotic;
  if (!ex) { el.innerHTML = `<div class="empty">Se încarcă…</div>`; return; }
  const regions = ex.regions || {};
  const minDisc = state.status?.settings?.rules?.min_discount_pct ?? 40;
  const all = applyFilters(ex.fares, true, !!state.dep).filter(r => state.exRegion === "ALL" || r.region === state.exRegion);
  // câte un rând pe destinație (dus-întors înaintea lui „doar dus” când ambele există)
  const rows = sortByChoice(all);
  const present = new Set(ex.fares.map(r => r.region));
  $("#c-exotic").textContent = ex.fares.length ? new Set(all.map(r => r.dest)).size : "";
  const chips = `<div class="chips" style="margin-bottom:12px">${["ALL", ...Object.keys(regions)].filter(k => k === "ALL" || present.has(k))
    .map(k => `<button class="chip${state.exRegion === k ? " on" : ""}" data-exregion="${k}">${k === "ALL" ? "🌍 Toate regiunile" : esc(regions[k])}</button>`).join("")}</div>`;
  const head = `<div class="banner${state.dep ? "" : " info"}">🌴 <div>Destinații <b>din afara Europei</b> cu plecare din <b>${esc(ex.origin_name)}</b>: orice companie, direct sau cu escală, sejururi de ${state.status?.settings?.exotic?.min_nights ?? 5}–${state.status?.settings?.exotic?.max_nights ?? 28} nopți la dus-întors.
    ${state.dep ? `Filtrate pe datele tale: <b>${datesLabel()}</b>.` : "Cel mai ieftin preț găsit pe oricare dată."}</div></div>`;
  const cards = rows.length
    ? shelves("exotic", rows, r => exoticCard(r, minDisc), state.exRegion === "ALL" ? ["region", "month"] : ["month", "country"], "destinații", regions)
    : `<div class="empty">Niciun zbor exotic pentru filtrele alese.</div>`;
  const posts = ex.posts.filter(p => !state.q || `${p.title} ${p.summary}`.toLowerCase().includes(state.q.toLowerCase()));
  const postsHtml = `<h3 style="font-size:15px;margin:22px 0 10px">📰 Oferte exotice din ${esc(ex.origin_name)} pe site-urile de specialitate <span class="count">${posts.length}</span></h3>` +
    (posts.length ? `<div class="posts">${posts.map(postHtml).join("")}</div>`
      : `<div class="empty">Încă nu au apărut articole cu destinații exotice din ${esc(ex.origin_name)}. Site-urile sunt verificate la ${state.status?.settings?.feeds_interval_minutes || 30} de minute.</div>`);
  el.innerHTML = head + chips + cards + postsHtml;
  initShelves(el);
}
function exoticCard(r) { return flightCard(r, { region: r.region_label }); }
function postHtml(p) {
  return `<article class="post">
    <div class="meta">${esc(p.feed)} · din ${(p.cities || "").split(",").map(c => ORIGIN_NAMES[c] || c).join(", ")} · ${esc(p.published || p.first_seen)}</div>
    <a class="title" href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)} ↗</a>
    ${p.summary ? `<div class="summary">${esc(p.summary)}</div>` : ""}
  </article>`;
}
function onDatesChanged() {
  filtersSummary();
  const hint = $("#f-dates-hint");
  $("#f-dates-clear").hidden = !state.dep && !state.ret;
  hint.classList.remove("err");
  if (datesInvalid()) { hint.textContent = "Data întoarcerii trebuie să fie după data plecării."; hint.classList.add("err"); }
  else if (!state.dep && state.ret) hint.textContent = "Alege și data plecării.";
  else if (state.dep) hint.textContent = `Rezultate pentru ${datesLabel()}.`;
  else hint.textContent = "Opțional: dacă ai date fixe, alege-le și toate listele se filtrează pe ele.";
  $("#f-trip").style.opacity = state.dep ? ".45" : "";
  $("#f-trip").title = state.dep ? "Tipul biletului rezultă din date (cu sau fără întoarcere)" : "";
  loadSearch();
  loadExotic();
  renderDeals(); renderLM(); renderDest();
}


/* ---------- așezare pe secțiuni: rânduri derulabile orizontal, ca în aplicații ---------- */
const MONTHS_FULL = ["Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie", "Iulie", "August", "Septembrie", "Octombrie", "Noiembrie", "Decembrie"];
const SHELF_PEEK = 16;   // câte carduri are un rând înainte de „Vezi toate”
function shelfKey(lv, r) {
  if (lv === "origin") return r.origin;
  if (lv === "month") return (r.dep_date || "").slice(0, 7);
  if (lv === "region") return r.region || "";
  return r.country || r.dest_name || r.dest;
}
function shelfTitle(lv, k, regions) {
  if (lv === "origin") return `<span class="pre">din</span> ${esc(ORIGIN_NAMES[k] || k)}`;
  if (lv === "month") {
    const [y, m] = k.split("-").map(Number);
    return `${MONTHS_FULL[m - 1] || k}${y !== new Date().getFullYear() ? ` <span class="yr">${y}</span>` : ""}`;
  }
  if (lv === "region") return esc(regions?.[k] || k || "Alte destinații");
  return esc(k);
}
function shelfGroups(rows, levels) {
  const originOrder = (state.status?.origins || []).map(o => o.code);
  let first = null;
  for (const lv of levels) {
    const map = new Map();
    for (const r of rows) {
      const k = shelfKey(lv, r);
      if (!map.has(k)) map.set(k, []);
      map.get(k).push(r);
    }
    const groups = [...map].map(([key, items]) => ({ lv, key, items }));
    if (lv === "origin") groups.sort((a, b) => originOrder.indexOf(a.key) - originOrder.indexOf(b.key));
    if (lv === "month") groups.sort((a, b) => a.key.localeCompare(b.key));
    if (groups.length > 1) return groups;
    first = first || groups;
  }
  return first || [];
}
function shelves(tab, rows, card, levels, noun, regions) {
  return shelfGroups(rows, levels).map(g => {
    const id = `${tab}:${g.lv}:${g.key}`;
    const open = state.openShelves.has(id);
    const shown = open ? g.items.slice(0, 300) : g.items.slice(0, SHELF_PEEK);
    const rest = g.items.length - shown.length;
    const min = Math.min(...g.items.map(r => r.price_eur));
    const many = g.items.length > 2;
    return `<section class="shelf${open ? " open" : ""}" data-shelf="${esc(id)}">
      <header class="shelf-h">
        <div class="shelf-t"><h3 title="${g.items.length} ${esc(noun)} · de la ${eur(min)}">${shelfTitle(g.lv, g.key, regions)}</h3></div>
        <div class="shelf-nav">
          ${open ? "" : `<button class="shelf-btn" type="button" data-shelf-nav="-1" aria-label="Înapoi">‹</button><button class="shelf-btn" type="button" data-shelf-nav="1" aria-label="Înainte">›</button>`}
          ${many ? `<button class="shelf-all" type="button" data-shelf-toggle="${esc(id)}">${open ? "Restrânge" : `Vezi toate <span class="muted">${g.items.length}</span>`}</button>` : ""}
        </div>
      </header>
      <div class="shelf-row">${shown.map(card).join("")}${rest > 0 && !open
        ? `<button class="shelf-more" type="button" data-shelf-toggle="${esc(id)}"><b class="num">+${rest}</b><span>Vezi toate</span></button>` : ""}</div>
    </section>`;
  }).join("");
}
function initShelves(root) {
  for (const row of root.querySelectorAll(".shelf-row")) {
    const sec = row.closest(".shelf");
    const upd = () => {
      const fits = row.scrollWidth <= row.clientWidth + 4;
      sec.classList.toggle("fits", fits);
      sec.classList.toggle("at-start", row.scrollLeft < 4);
      sec.classList.toggle("at-end", fits || row.scrollLeft + row.clientWidth >= row.scrollWidth - 4);
    };
    row.addEventListener("scroll", upd, { passive: true });
    upd();
  }
}
addEventListener("resize", () => { for (const id of ["#tab-deals", "#tab-search", "#tab-exotic", "#tab-escale"]) { const el = $(id); if (el) initShelves(el); } });
function toggleShelf(id) {
  const tab = id.split(":")[0];
  const wasOpen = state.openShelves.has(id);
  if (wasOpen) state.openShelves.delete(id); else state.openShelves.add(id);
  ({ deals: renderDeals, search: renderSearch, exotic: renderExotic, escale: renderEscale })[tab]?.();
  if (wasOpen) {
    const sec = [...$$(".shelf")].find(s => s.dataset.shelf === id);
    if (sec && sec.getBoundingClientRect().top < 0) sec.scrollIntoView({ block: "start" });
  }
}


/* ---------- favorite: zborurile salvate (pe acest dispozitiv) ---------- */
function favKey(r) { return `${r.origin}|${r.dest}|${r.dep_date}|${r.ret_date || ""}`; }
function loadFavs() {
  try { return JSON.parse(localStorage.getItem("favs1") || "{}") || {}; } catch (e) { return {}; }
}
function saveFavs() {
  try { localStorage.setItem("favs1", JSON.stringify(state.favs)); } catch (e) { /* ignorat */ }
  const n = Object.keys(state.favs).length;
  const c = $("#c-favs"); if (c) c.textContent = n || "";
}
function favSnapshot(r) {
  const pick = x => x && { date: x.date, time: x.time, airline: x.airline, price_eur: x.price_eur, link: x.link, source: x.source };
  return { origin: r.origin, dest: r.dest, origin_name: r.origin_name, dest_name: r.dest_name, country: r.country,
    dep_date: r.dep_date, ret_date: r.ret_date || "", trip: r.trip || (r.ret_date ? "RT" : "OW"), nights: r.nights,
    dep_time: r.dep_time, price_eur: r.price_eur, price_ron: r.price_ron, airline: r.airline, source: r.source,
    link: r.link, gf_link: r.gf_link, out: pick(r.out), back: pick(r.back), region_label: r.region_label,
    saved_at: new Date().toISOString().slice(0, 16).replace("T", " ") };
}
function favBtn(r) {
  const k = favKey(r), on = !!state.favs[k];
  return `<button class="fav-btn${on ? " on" : ""}" type="button" data-fav="${esc(k)}" aria-pressed="${on}"
    title="${on ? "Scoate de la favorite" : "Adaugă la favorite"}" aria-label="${on ? "Scoate de la favorite" : "Adaugă la favorite"}">${on ? "♥" : "♡"}</button>`;
}
const favRows = new Map();   // cheie -> zborul afișat (pentru salvare la click)
function toggleFav(k) {
  if (state.favs[k]) delete state.favs[k];
  else { const r = favRows.get(k); if (!r) return; state.favs[k] = favSnapshot(r); }
  saveFavs();
  for (const b of $$(`[data-fav="${CSS.escape(k)}"]`)) {
    const on = !!state.favs[k];
    b.classList.toggle("on", on); b.textContent = on ? "♥" : "♡"; b.setAttribute("aria-pressed", on);
    b.title = on ? "Scoate de la favorite" : "Adaugă la favorite";
  }
  if (state.tab === "favs") renderFavs();
}
let favSeq = 0;
async function renderFavs() {
  const el = $("#tab-favs");
  const favs = Object.entries(state.favs);
  saveFavs();
  const today = todayIso();
  if (!favs.length) {
    el.innerHTML = `<div class="empty"><div class="big">♡</div><p><b>Încă nu ai zboruri favorite.</b></p>
      <p>Apasă ♡ pe orice zbor care îți place: îl găsești aici, cu prețul de acum și cât s-a schimbat de când l-ai salvat.</p></div>`;
    return;
  }
  const seq = ++favSeq;
  if (!el.innerHTML || !el.querySelector(".fav-list")) el.innerHTML = `<div class="empty">Se încarcă prețurile de acum…</div>`;
  let now = {};
  try { now = await api(`/api/favorites?k=${encodeURIComponent(favs.map(([k]) => k).join(","))}${exactQ("&")}`); } catch (e) { /* offline */ }
  if (seq !== favSeq) return;
  const rows = favs.map(([k, f]) => ({ k, f, cur: now[k] })).sort((a, b) => a.f.dep_date.localeCompare(b.f.dep_date));
  const cards = rows.map(({ k, f, cur }) => {
    const past = f.dep_date < today;
    const r = cur ? { ...f, ...cur, region_label: f.region_label } : f;
    let note;
    if (past) note = `<div class="fav-note muted">Zborul a trecut (${fmtDate(f.dep_date)}).</div>`;
    else if (!cur) note = `<div class="fav-note warn">Nu mai găsim acest zbor pe aceste date: probabil s-a epuizat sau s-a scumpit mult. Ultimul preț: ${eur(f.price_eur)}.</div>`;
    else {
      const diff = Math.round((cur.price_eur - f.price_eur) * 100) / 100;
      note = Math.abs(diff) < 0.01 ? `<div class="fav-note">Același preț ca la salvare (${eur(f.price_eur)})</div>`
        : diff < 0 ? `<div class="fav-note good">▼ S-a ieftinit cu ${eur(-diff)} de când l-ai salvat (era ${eur(f.price_eur)})</div>`
        : `<div class="fav-note bad">▲ S-a scumpit cu ${eur(diff)} de când l-ai salvat (era ${eur(f.price_eur)})</div>`;
    }
    return flightCard({ ...r, dep_date: f.dep_date, ret_date: f.ret_date }, { region: r.region_label, favNote: note, dim: past || !cur, favDel: true });
  });
  el.innerHTML = `<div class="fav-tools"><span><b>${favs.length}</b> ${favs.length === 1 ? "zbor salvat" : "zboruri salvate"} · prețul de acum, pe acest dispozitiv</span>
      <button class="btn small ghost" type="button" data-fav-clear>🗑 Șterge toate</button></div>
    <div class="grid fav-list">${cards.join("")}</div>`;
}

/* ---------- randare: oferte ---------- */
function renderDeals() {
  const el = $("#tab-deals");
  const rows = sortByChoice(applyFilters(state.deals));
  $("#c-deals").textContent = state.deals.length ? rows.length : "";
  if (!state.deals.length) { el.innerHTML = emptyState(); return; }
  if (!rows.length) {
    el.innerHTML = datesBanner("Ofertele sunt") + `<div class="empty">Nicio ofertă pentru filtrele alese.${state.dep ? ` Vezi toate zborurile pe datele tale în tab-ul <button class="linkish" data-tab="search">📅 Caută pe date</button>.` : ""}</div>`;
    return;
  }
  el.innerHTML = datesBanner("Ofertele sunt") + shelves("deals", rows, dealCard, ["origin", "month", "country"], "oferte");
  initShelves(el);
}
function cardTags(r) {
  const f = r.flags || "", t = [];
  if (r.is_new) t.push(`<span class="fc-tag new">Nou</span>`);
  if (r.source === "google") t.push(`<span class="fc-tag real" title="Preț real confirmat pe Google Flights">✓ Preț real</span>`);
  else if (unverified(r)) t.push(`<span class="fc-tag unv" title="Preț găsit în căutările altor călători; confirmă-l la „Rezervă”">De verificat</span>`);
  if (f.includes("MINIM")) t.push(`<span class="fc-tag">Cel mai mic preț</span>`);
  if (f.includes("LAST_MINUTE")) t.push(`<span class="fc-tag lm">Last minute</span>`);
  if (f.includes("SCADERE") && t.length < 2) t.push(`<span class="fc-tag">Preț scăzut</span>`);
  return t.length ? t[0] : "";
}
function freshShort(r) {
  const src = r.source || r.out?.source, ts = r.last_seen || r.checked_at;
  if (src === "google") return `<span class="fresh" title="Confirmat pe Google Flights">✓ Google Flights${ts ? " · " + ts.slice(11, 16) : ""}</span>`;
  if (unverified(r)) return "";
  return ts ? `<span class="fresh" title="${esc(checkedLabel(ts))} direct la ${esc(srcName(src))}">✓ ${ts.slice(0, 10) === todayIso() ? "" : fmtDate(ts, false) + " "}${ts.slice(11, 16)}</span>` : "";
}
function whenLine(r) {
  const kind = r.trip === "RT" ? "Dus-întors" : "Dus";
  const when = r.trip === "RT"
    ? `${fmtDate(r.dep_date)} → ${fmtDate(r.ret_date)} · ${r.nights} ${r.nights === 1 ? "noapte" : "nopți"}`
    : `${fmtDate(r.dep_date)}${r.dep_time ? ", " + r.dep_time : ""}`;
  return `<div class="fc-when" title="${esc(inDays(r.days_to_dep))}"><span class="kind-lbl">${kind}</span> · ${when}</div>`;
}
function legShort(icon, leg) {
  return `<div class="fc-leg"><span>${icon} ${fmtDate(leg.date)}${leg.time ? ", " + leg.time : ""}</span><span class="muted">${esc((leg.airline || "").split(" · ")[0])}${leg.price_eur != null ? " · " + eur(leg.price_eur) : ""}</span></div>`;
}
function flightCard(r, opts = {}) {
  const place = [r.country, opts.region].filter(Boolean).join(" · ");
  const book = r.link || !r.out ? bookBtn(r.link || r.gf_link, r.airline)
    : `${bookBtn(r.out.link, r.out.airline, "Rezervă dus")}${bookBtn(r.back.link, r.back.airline, "Rezervă întors")}`;
  const mixed = r.out && r.back && r.out.airline && r.back.airline && r.out.airline !== r.back.airline;
  const airline = mixed ? "" : esc((r.airline || r.out?.airline || "").replace(/ · direct$/, ""));
  const sub = [r.typical_eur && r.discount_pct > 0 ? `de obicei ${eur(r.typical_eur)}` : "",
               r.prev_price_eur ? `era ${eur(r.prev_price_eur)}` : ""].filter(Boolean).join(" · ");
  favRows.set(favKey(r), r);
  return `<article class="card fc${opts.dim ? " dim" : ""}">
    ${fcPhoto(r)}
    <div class="fc-head">
      <div class="fc-route">${esc(r.origin_name)}<span class="arrow">→</span>${esc(r.dest_name)}</div>
      <div class="fc-head-r">${r.discount_pct >= 5 ? `<span class="fc-disc num" title="${esc(sub)}">−${Math.round(r.discount_pct)}%</span>` : ""}${favBtn(r)}</div>
    </div>
    ${place ? `<div class="fc-place">${esc(place)}</div>` : ""}
    <div class="fc-price"><span class="price num">${eur(r.price_eur)}</span>${leiSpan(r)}</div>
    ${wizzFee(r)}
    ${whenLine(r)}
    ${fcWeather(r)}
    ${opts.favNote || ""}
    ${mixed ? `<div class="fc-legs">${legShort("🛫", r.out)}${legShort("🛬", r.back)}</div>` : ""}
    <div class="fc-meta">${airline ? `<span>${airline}</span>` : ""}${cardTags(r)}</div>
    ${paxTotal(r)}
    <div class="fc-actions${r.link || !r.out ? "" : " two"}">
      ${book}
      <button class="btn small ghost fc-icon" data-route="${r.origin}|${r.dest}|${r.trip}" title="Calendarul prețurilor${r.other_dates ? ` · încă ${r.other_dates} date bune` : ""}" aria-label="Calendarul prețurilor">📅</button>
      ${verifyBtn(r, true)}
      ${opts.favDel ? `<button class="btn small ghost fc-icon fav-del" type="button" data-fav-del="${esc(favKey(r))}" title="Șterge din favorite" aria-label="Șterge din favorite">🗑</button>` : ""}
    </div>
  </article>`;
}
function dealCard(r) { return flightCard(r); }
// Wizz Air adaugă la plată o taxă de administrare obligatorie (8–13 € pe zbor, de persoană), care nu apare în prețul zborului
function wizzFee(r) {
  const legs = r.out ? [r.out, r.back].filter(Boolean) : [r];
  const n = legs.filter(l => l.source === "wizzair" || /wizzair\.com/.test(l.link || "") || /^Wizz Air/.test(l.airline || "")).length
    * (r.out ? 1 : (r.ret_date ? 2 : 1));
  if (!n) return "";
  return `<div class="fc-fee" title="Taxa de administrare Wizz Air: 8–13 € pe zbor, pentru fiecare pasager (wizzair.com → Toate serviciile și taxele)">+ taxa Wizz Air la plată: ${8 * n}–${13 * n} € de persoană</div>`;
}
function emptyState() {
  const st = state.status;
  if (st?.running) return `<div class="empty"><div class="big">🔎</div><p><b>Prima scanare e în curs…</b></p><p>Caut prețuri la Ryanair și Wizz Air pentru toate cele 4 orașe. Durează 10–20 de minute; pagina se actualizează singură.</p></div>`;
  return `<div class="empty"><div class="big">✈️</div><p>Încă nu există oferte. Apasă <b>Scanează acum</b>.</p></div>`;
}

/* ---------- randare: last minute ---------- */
function renderLM() {
  const el = $("#tab-lm");
  const rows = sortByChoice(applyFilters(state.lm), state.sort === "best" ? "price_asc" : state.sort);
  $("#c-lm").textContent = state.lm.length ? rows.length : "";
  if (!state.lm.length) { el.innerHTML = emptyState(); return; }
  if (!rows.length) { el.innerHTML = datesBanner("Zborurile sunt") + `<div class="empty">Niciun zbor pentru filtrele alese.</div>`; return; }
  el.innerHTML = datesBanner("Zborurile sunt") + `<div class="banner info">⏰ <div>Zboruri cu plecare în următoarele <b>${state.days} zile</b>, de la cel mai ieftin. Ideal pentru escapade spontane.</div></div>
  <div class="table-wrap stack"><table>
    <thead><tr><th>Plecare</th><th>Destinație</th><th>Când</th><th>Tip</th><th class="r">Preț</th><th class="r">vs. obișnuit</th><th>Companie</th><th></th></tr></thead>
    <tbody>${rows.slice(0, 400).map(r => `<tr>
      <td class="m-hide" data-label="Plecare">${esc(r.origin_name)}</td>
      <td class="m-title"><span class="m-only">${esc(r.origin_name)} → </span><button class="cell-btn" data-route="${r.origin}|${r.dest}|${r.trip}"><b>${esc(r.dest_name)}</b></button> <span class="muted">${esc(r.country)}</span></td>
      <td data-label="Când">${whenText(r)} <span class="muted">(${inDays(r.days_to_dep)})</span></td>
      <td data-label="Tip">${tripLabel(r)}</td>
      <td class="r num m-price" data-label="Preț"><span class="strong">${eur(r.price_eur)}</span><br><span class="muted" style="font-size:12px">${fmtLei(r.price_ron)}</span>${seats() > 1 ? `<br><span style="font-size:12px">👥 ${seats()} locuri: <b>${eur(r.price_eur * seats())}</b></span>` : ""}</td>
      <td class="r num" data-label="vs. obișnuit">${r.discount_pct == null ? "–" : r.discount_pct > 0 ? `<span style="color:var(--good-text);font-weight:700">−${Math.round(r.discount_pct)}%</span>` : `<span class="muted">+${Math.round(-r.discount_pct)}%</span>`}</td>
      <td class="muted" data-label="Companie">${esc(r.airline || "")}${unverified(r) ? ` · <span class="unv-text">🔎 de verificat</span>` : ""}</td>
      <td class="m-actions"><div class="row-actions">${(favRows.set(favKey(r), r), favBtn(r))}${bookBtn(r.link || r.gf_link, r.airline)}${verifyBtn(r)}</div>
        <div class="fresh row-checked">${r.source === "aviasales" ? "🔎 preț găsit recent, de verificat" : checkedLabel(r.last_seen)}</div></td>
    </tr>`).join("")}</tbody></table></div>`;
}

/* ---------- randare: destinații ---------- */
function renderDest() {
  const el = $("#tab-dest");
  const origins = (state.status?.origins || []).map(o => o.code).filter(c => state.origin === "ALL" || c === state.origin);
  const q = state.q.trim().toLowerCase();
  const max = parseFloat(state.max);
  const byDates = !!state.dep && !datesInvalid();
  const tripKey = byDates ? (state.ret ? "RT" : "OW") : (state.trip === "RT" ? "RT" : "OW");
  let rows = (byDates ? destFromSearch() : state.dest)
    .filter(d => !q || `${d.dest_name} ${d.country} ${d.dest}`.toLowerCase().includes(q));
  rows = rows.map(d => {
    const cells = origins.map(o => d[tripKey][o]);
    const vals = cells.filter(Boolean).map(c => c.min_eur);
    return { ...d, cells, best: vals.length ? Math.min(...vals) : null };
  }).filter(d => d.best != null && (!max || d.best <= max));
  rows = sortByChoice(rows, ["price_desc", "newest", "name"].includes(state.sort) ? state.sort : "price_asc");
  $("#c-dest").textContent = state.dest.length ? rows.length : "";
  if (!state.dest.length) { el.innerHTML = emptyState(); return; }
  const head = byDates
    ? `<div class="banner">📅 <div>Cel mai mic preț <b>${tripKey === "RT" ? "dus-întors" : "doar dus"}</b> pe datele tale (<b>${datesLabel()}</b>), spre fiecare destinație, din fiecare oraș. <button class="linkish" data-clear-dates>Arată toate datele</button></div></div>`
    : `<div class="banner info">🌍 <div>Vedere de ansamblu: cel mai mic preț <b>${tripKey === "RT" ? "dus-întors" : "doar dus"}</b> spre fiecare destinație, din fiecare oraș, cu data zborului. <b>„Rezervă”</b> te duce direct la companie pentru cea mai ieftină variantă; apasă pe un preț pentru calendarul complet al acelei rute.</div></div>`;
  if (!rows.length) { el.innerHTML = head + `<div class="empty">Nicio destinație pentru filtrele alese.</div>`; return; }
  el.innerHTML = head + `<div class="table-wrap stack"><table>
    <thead><tr><th>Destinație</th>${origins.map(o => `<th class="r">din ${ORIGIN_NAMES[o] || o}</th>`).join("")}<th class="r">Cea mai ieftină</th></tr></thead>
    <tbody>${rows.map(d => `<tr>
      <td class="m-title"><b>${esc(d.dest_name)}</b> <span class="muted">${esc(d.country)} · ${d.dest}</span></td>
      ${d.cells.map((c, i) => `<td class="r" data-label="din ${ORIGIN_NAMES[origins[i]] || origins[i]}">${c ? `<button class="cell-btn${c.min_eur === d.best ? " best" : ""}" data-route="${origins[i]}|${d.dest}|${tripKey}" title="Calendarul prețurilor pe această rută · ${lei(c.min_eur)} · Prețul obișnuit: ${eur(c.typical_eur)}">${eur(c.min_eur)}${c.source === "aviasales" ? ` <span class="unv-text" title="Preț găsit recent în căutările altor călători, de verificat">🔎</span>` : ""}</button>${c.date ? `<div class="cell-date">${fmtDate(c.date, false)}${c.ret ? " → " + fmtDate(c.ret, false) : ""}</div>` : ""}` : `<span class="muted">–</span>`}</td>`).join("")}
      <td class="r m-actions">${destBook(d, origins)}</td>
    </tr>`).join("")}</tbody></table></div>`;
}
function destBook(d, origins) {
  const i = d.cells.findIndex(c => c && c.min_eur === d.best);
  const c = d.cells[i];
  if (!c) return "";
  const from = ORIGIN_NAMES[origins[i]] || origins[i];
  if (c.link) return bookBtn(c.link, "");
  if (c.out_link && c.back_link) return `${bookBtn(c.out_link, "", "Rezervă dus")} ${bookBtn(c.back_link, "", "Rezervă întors")}`;
  return "";
}
function destFromSearch() {
  const out = {};
  for (const r of state.search) {
    const d = out[r.dest] || (out[r.dest] = { dest: r.dest, dest_name: r.dest_name, country: r.country, OW: {}, RT: {} });
    const cur = d[r.trip][r.origin];
    if (!cur || r.price_eur < cur.min_eur) {
      d[r.trip][r.origin] = { min_eur: r.price_eur, typical_eur: r.typical_eur, date: r.dep_date, ret: r.ret_date,
        link: r.link || "", out_link: r.out?.link || "", back_link: r.back?.link || "", source: r.source };
    }
  }
  return Object.values(out);
}

/* ---------- randare: articole ---------- */
function renderPosts() {
  const el = $("#tab-posts");
  const rows = state.posts.filter(p => state.origin === "ALL" || (p.cities || "").split(",").includes(state.origin))
    .filter(p => !state.q || `${p.title} ${p.summary}`.toLowerCase().includes(state.q.toLowerCase()));
  $("#c-posts").textContent = state.posts.length ? rows.length : "";
  const fl = state.status?.feeds_last;
  const head = `<div class="banner">📰 <div>Oferte publicate de site-uri de specialitate (Fly4free, TravelFree, Utazómajom, Piraten etc.) care pleacă din orașele tale — inclusiv pachete și last minute.
    ${fl ? `Ultima verificare: <b>${ago(fl.at)}</b>.` : ""} ${STATIC ? "" : `<button class="linkish" id="btn-feeds">Verifică acum</button>`}</div></div>`;
  if (!rows.length) { el.innerHTML = head + `<div class="empty">Încă nu au apărut articole cu plecare din orașele tale. Site-urile sunt verificate la fiecare ${state.status?.settings?.feeds_interval_minutes || 30} de minute.</div>`; return; }
  el.innerHTML = head + `<div class="posts">${rows.map(p => `<article class="post">
    <div class="meta">${esc(p.feed)} · din ${(p.cities || "").split(",").map(c => ORIGIN_NAMES[c] || c).join(", ")} · ${esc(p.published || p.first_seen)}</div>
    <a class="title" href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)} ↗</a>
    ${p.summary ? `<div class="summary">${esc(p.summary)}</div>` : ""}
  </article>`).join("")}</div>`;
}

/* ---------- ajutor ---------- */
function renderHelp() {
  const s = state.status?.settings || {};
  const r = s.rules || {};
  $("#tab-help").innerHTML = `
  <h2>Datele călătoriei (opțional)</h2>
  <p>Fără date, fiecare tab arată toate zborurile. Dacă ai date fixe, alege-le în chenarul 📅 și toate listele se filtrează pe ele. Cu „Flexibil ±” prinzi și zilele vecine. Cu dată de întoarcere, „Caută pe date” și „Toate destinațiile” combină cel mai ieftin dus cu cel mai ieftin întors, chiar dacă sunt companii diferite.</p>
  <h2>👥 Persoane și locuri</h2>
  <p>Alege numărul de persoane (1–9) în filtre: vezi prețul total pentru grup, iar „Rezervă” și „Compară” se deschid direct cu toți pasagerii. Apasă <b>🔄 Verifică</b> pe un bilet Wizz Air sau Ryanair ca să afli <b>câte locuri mai sunt la acel preț</b> (de exemplu „mai sunt doar 3 locuri”) și dacă prețul crește pentru grupul tău. Companiile nu publică numărul exact de locuri din avion; aplicația îl află din prețul pentru 1–9 persoane.</p>
  <h2>🔀 Escale făcute de tine</h2>
  <p>Două bilete low-cost separate, prin aeroporturile mari Ryanair (de exemplu Cluj → Bergamo, apoi Bergamo → Sevilla), când ies mai ieftine decât zborul direct sau când nu există zbor direct. Arătăm doar combinații cu peste 3 ore între zboruri sau cu o noapte la escală. Atenție: fiind bilete separate, dacă primul zbor întârzie, al doilea nu te așteaptă.</p>
  <h2>☀️ Vremea și 🎲 Surprinde-mă</h2>
  <p>Pe fiecare zbor vezi temperatura medie și cât plouă de obicei în luna călătoriei (media 2001–2020, date NASA POWER; nu e o prognoză). Butonul <b>🎲 Surprinde-mă</b> alege la întâmplare o destinație în bugetul tău, din orașul selectat.</p>
  <h2>🌴 Exotice din Budapesta și București</h2>
  <p>Destinații din afara Europei (Asia, insulele din Oceanul Indian, Orientul Mijlociu, Africa, America, Oceania), orice companie, direct sau cu escală, dus-întors cu sejururi de ${s.exotic?.min_nights ?? 5}–${s.exotic?.max_nights ?? 28} nopți, pe următoarele ${s.exotic?.months_ahead ?? 8} luni. Pentru ele, pragul de ofertă e mai mare: până la ${s.exotic?.max_price_rt_eur ?? 1400} € dus-întors, iar sub ${s.exotic?.super_cheap_rt_eur ?? 400} € e „super ieftin”.</p>
  <h2>Cum se decide că e o ofertă</h2>
  <p>Pentru fiecare rută se salvează zilnic prețul minim și cel median. <b>Prețul obișnuit</b> este mediana ultimelor zile/luni. Un bilet apare la Oferte dacă:</p>
  <ul>
    <li>📉 e cu cel puțin <b>${r.min_discount_pct ?? 40}%</b> sub prețul obișnuit al rutei;</li>
    <li>🏆 e cel mai mic preț văzut vreodată pe rută (după minim 2 zile de istoric);</li>
    <li>⬇️ prețul a scăzut cu cel puțin <b>${r.drop_pct ?? 20}%</b> de la verificarea anterioară;</li>
    <li>🔥 costă sub <b>${r.super_cheap_ow_eur ?? 20} €</b> dus sau <b>${r.super_cheap_rt_eur ?? 50} €</b> dus-întors;</li>
    <li>⏰ pleacă în maxim ${s.last_minute_days ?? 10} zile și e ieftin (last minute).</li>
  </ul>
  <p>În prima zi comparația se face cu celelalte zile din calendarul rutei. Cu cât aplicația rulează mai mult, cu atât istoricul devine mai precis.</p>
  <h2>Când se verifică</h2>
  <p>Prețurile se verifică complet la fiecare <b>${s.scan_interval_hours ?? 4} ore</b>, pe următoarele <b>${s.months_ahead ?? 4} luni</b>. Dus-întors înseamnă ${s.round_trip?.min_nights ?? 2}–${s.round_trip?.max_nights ?? 10} nopți la destinație. Verificările mai dese riscă blocarea de către companii.</p>
  ${STATIC ? `<h2>Despre această pagină</h2>
  <p>Aceasta este pagina publică <b>FlyCenterHub S.R.</b>. Prețurile sunt căutate automat și publicate aici după fiecare verificare. Sus vezi când au fost actualizate ultima dată.</p>` : `
  <h2>Notificări Telegram</h2>
  <p>${state.status?.telegram ? "✅ Active." : "Inactive."} Pentru configurare rulează <code>Configurare-Telegram.bat</code> din folderul aplicației.
  ${state.status?.telegram ? `<button class="btn small ghost" id="btn-tg-test">Trimite un mesaj de test</button>` : ""}</p>
  <h2>Setări</h2>
  <p>Toate pragurile (reduceri, prețuri maxime, orașe, interval) sunt în <code>config.json</code>. După modificare, repornește aplicația.</p>`}
  <p class="muted">Prețurile sunt pentru 1 adult, fără bagaj de cală, și pot varia la rezervare. Verifică întotdeauna prețul final pe site-ul companiei.</p>`;
}

/* ---------- status ---------- */
function renderStatus() {
  const st = state.status;
  const el = $("#status");
  const btn = $("#btn-scan");
  if (!st) return;
  el.classList.toggle("busy", st.running);
  const last = st.last_scan;
  el.classList.toggle("err", !st.running && last?.status === "error");
  const bar = $("#scanbar");
  bar.hidden = !st.running;
  if (st.running) {
    const p = st.progress.length ? st.progress.join(" · ") : "pornesc…";
    const kind = st.scan_kind === "quick" ? "Verificare rapidă" : "Scanare";
    const pct = st.progress_pct != null ? ` ${st.progress_pct}%` : "";
    const eta = st.eta_min != null ? ` · ~${st.eta_min < 1 ? "sub 1" : st.eta_min} min rămase` : "";
    el.innerHTML = `<span class="dot"></span><b>${kind}${pct}</b>${eta}<span class="m-extra"> · ${esc(p)}</span>`;
    $(".fill", bar).style.width = (st.progress_pct || 2) + "%";
  } else if (last && STATIC) {
    const upd = st.updated_at || last.finished_at;
    const hours = (Date.now() - new Date(upd.replace(" ", "T")).getTime()) / 36e5;
    el.innerHTML = `<span class="dot"></span>Prețuri actualizate ${ago(upd)}` +
      `<span class="m-extra">${hours > 6 ? " · se reactualizează automat când pornește căutarea" : " · se actualizează automat"}</span>`;
  } else if (last) {
    const lab = last.status === "ok" ? "Actualizat" : last.status === "partial" ? "Actualizat parțial" : "Eroare la scanare";
    el.innerHTML = `<span class="dot"></span>${lab} ${ago(st.updated_at || last.finished_at)}<span class="m-extra"> · următoarea verificare la ${hhmm(st.next_check_at || st.next_scan_at)}${st.telegram ? " · Telegram ✓" : ""}</span>`;
    el.title = JSON.stringify(last.info?.sources || last.info || {}, null, 1);
  } else {
    el.innerHTML = `<span class="dot"></span>Nicio scanare încă`;
  }
  if (st.origins?.length) {
    const codes = st.origins.map(o => o.code);
    if (state.origin !== "ALL" && !codes.includes(state.origin)) state.origin = "ALL";
    renderOriginChips(codes);
  }
  const f = st.fx;
  $("#fx-line").innerHTML = f?.eur_ron
    ? `<span class="fx-lbl" title="${f.source === "BNR" ? "Cursul oficial BNR în vigoare. BNR publică cursul nou în fiecare zi lucrătoare pe la ora 13:00; site-ul îl preia automat." : ""}">Curs ${f.source}${f.date ? " · " + (f.date === todayIso() ? "azi" : "în vigoare, din " + fmtDate(f.date, false)) : ""}</span> 1 € = ${f.eur_ron.toLocaleString("ro-RO", { minimumFractionDigits: 4 })} lei` +
      (f.huf100_ron ? `<span class="m-extra"> · 100 Ft = ${f.huf100_ron.toLocaleString("ro-RO", { minimumFractionDigits: 4 })} lei</span>` : "")
    : "";
  const ps = st.public_site;
  $("#public-line").innerHTML = !STATIC && ps?.url
    ? `🌐 <span class="m-extra">Site public: <a href="${esc(ps.url)}" target="_blank" rel="noopener">${esc(ps.url.replace("https://", ""))}</a> </span>
       <button class="linkish" id="btn-copy-link" data-url="${esc(ps.url)}">Copiază linkul site-ului</button>${ps.error ? ` · <span style="color:var(--hot-text)">${esc(ps.error)}</span>` : ""}`
    : "";
  btn.disabled = st.running;
  btn.textContent = st.running ? "Se scanează…" : "Scanează acum";
  $("#btn-quick").disabled = st.running;
  if (st.settings?.months_ahead) {
    $("#f-dep").max = $("#f-ret").max = isoAdd(todayIso(), Math.round(st.settings.months_ahead * 30.5) + 10);
  }

  const h = st.counts?.history_days || 0;
  $("#banner").innerHTML = (h > 0 && h < 3 && !st.running)
    ? `<div class="banner info">📈 <div><b>Istoricul prețurilor abia începe (${h} ${h === 1 ? "zi" : "zile"}).</b> Deocamdată prețurile sunt comparate cu celelalte zile din calendarul fiecărei rute. De la 3 zile de istoric, comparațiile cu „ultimele zile și luni” devin tot mai precise.</div></div>`
    : "";
}

/* ---------- încărcare ---------- */
async function loadStatus() {
  try {
    state.status = await api("/api/status");
    renderStatus();
    const id = state.status.last_scan?.id;
    const ver = state.status.data_version;
    if ((id && id !== state.lastScanId) || (state.wasRunning && !state.status.running) ||
        (state.dataVersion != null && ver !== state.dataVersion)) {
      state.lastScanId = id;
      state.dataVersion = ver;
      await loadData();
    }
    state.dataVersion = ver;
    state.wasRunning = state.status.running;
  } catch (e) {
    $("#status").innerHTML = `<span class="dot"></span>Aplicația nu răspunde — e pornită?`;
    $("#status").classList.add("err");
  }
}
// Poze cu orașele (Wikimedia Commons): {cod aeroport: fișier}
let PHOTOS = {};
const photosP = api("/api/photos").then(p => { PHOTOS = p || {}; }).catch(() => {});
function photoOf(code) { return PHOTOS[code]; }
function fcPhoto(r) {
  const f = photoOf(r.dest);
  if (!f) return "";
  if (f.startsWith("local:")) {  // poză încărcată de pe laptop (în folderul photos/ al site-ului)
    return `<div class="fc-photo"><img src="photos/${esc(f.slice(6))}" alt="${esc(r.dest_name)}" loading="lazy" decoding="async" onerror="this.parentNode.remove()"></div>`;
  }
  const src = `https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(f)}?width=500`;
  return `<div class="fc-photo"><img src="${src}" alt="${esc(r.dest_name)}" loading="lazy" decoding="async" onerror="this.parentNode.remove()">` +
    `<a class="fc-credit" href="https://commons.wikimedia.org/wiki/File:${encodeURIComponent(f)}" target="_blank" rel="noopener" title="Foto: Wikimedia Commons (licență liberă) — vezi autorul">©</a></div>`;
}
/* ---------- vremea medie în luna zborului (NASA POWER, 2001–2020) ---------- */
let CLIMATE = {};
const climateP = api("/api/climate").then(c => { CLIMATE = c || {}; }).catch(() => {});
function fcWeather(r, date = r.dep_date) {
  const c = CLIMATE[r.dest];
  if (!c || !date) return "";
  const m = +date.slice(5, 7) - 1, [t, mm] = c[m] || [];
  if (t == null) return "";
  const [ico, rain] = mm < 20 ? ["☀️", "fără ploaie"] : mm < 60 ? ["🌤️", "puțină ploaie"] : mm < 110 ? ["🌦️", "ploi moderate"] : ["🌧️", "ploios"];
  return `<div class="fc-wx" title="Media lunii ${MONTHS_FULL[m].toLowerCase()} (zi și noapte), pe 2001–2020, după NASA POWER: ${t}°C și ${mm} mm de ploaie. Nu e o prognoză meteo.">` +
    `<span aria-hidden="true">${t < 3 ? "❄️" : ico}</span><span>${MONTHS[m]}: ~${String(Math.round(t)).replace("-", "−")}°C medie · ${rain}</span></div>`;
}
async function loadData() {
  await Promise.all([photosP, climateP]);
  const [deals, lm, dest, posts] = await Promise.all([
    api(`/api/deals${exactQ()}`), api(`/api/lastminute?days=${state.days}${exactQ("&")}`), api(`/api/destinations${exactQ()}`), api("/api/posts"),
  ]);
  Object.assign(state, { deals, lm, dest, posts });
  renderAll();
  loadSearch();
  loadExotic();
}
function filtersSummary() {
  const n = [state.dep, state.origin !== "ALL", state.trip !== "ALL" && !state.dep, state.max, state.q.trim(), seats() > 1 || state.infants > 0, !state.exact].filter(Boolean).length;
  $("#filters-sum").textContent = n ? `${n} ${n === 1 ? "activ" : "active"}` : "";
}
/* ---------- randare: harta cu prețuri ---------- */
const MAP = { region: "eu", max: null, lib: null, world: null, coords: null };
function loadScript(src) {
  return new Promise((ok, bad) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = bad; document.head.appendChild(s); });
}
async function mapLibs() {
  if (!MAP.lib) MAP.lib = (async () => {
    if (!window.d3) await loadScript("https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js");
    if (!window.topojson) await loadScript("https://cdnjs.cloudflare.com/ajax/libs/topojson/3.0.2/topojson.min.js");
    const [world, coords] = await Promise.all([
      fetch("https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json").then(r => r.json()),
      api("/api/coords"),
    ]);
    MAP.world = topojson.feature(world, world.objects.countries);
    MAP.coords = coords || {};
  })();
  return MAP.lib;
}
// cel mai mic preț spre fiecare destinație, din orașul ales (sau din oricare), pe tipul de călătorie ales
function mapRows() {
  // Europa: dus (sau ce ai ales la filtre); toată lumea: dus-întors, cum se caută de obicei zborurile lungi
  const tripKey = state.trip === "RT" || (MAP.region === "world" && state.trip !== "OW") ? "RT" : "OW";
  const origins = (state.status?.origins || []).map(o => o.code).filter(c => state.origin === "ALL" || c === state.origin);
  const q = state.q.trim().toLowerCase();
  const out = [];
  for (const d of state.dest || []) {
    if (q && !`${d.dest_name} ${d.country} ${d.dest}`.toLowerCase().includes(q)) continue;
    let best = null;
    for (const o of origins) {
      const c = (d[tripKey] || {})[o];
      if (c && (!best || c.min_eur < best.min_eur)) best = { ...c, origin: o };
    }
    if (best) out.push({ ...d, best, tripKey });
  }
  // pe harta lumii intră și destinațiile exotice (Asia, America, Africa...)
  if (MAP.region === "world") {
    const byDest = new Map(out.map(r => [r.dest, r]));
    for (const f of state.exotic?.fares || []) {
      const trip = f.trip || (f.ret_date ? "RT" : "OW");
      if (trip !== tripKey || !origins.includes(f.origin)) continue;
      if (q && !`${f.dest_name} ${f.country} ${f.dest}`.toLowerCase().includes(q)) continue;
      const cur = byDest.get(f.dest);
      if (cur && cur.best.min_eur <= f.price_eur) continue;
      const row = { dest: f.dest, dest_name: f.dest_name, country: f.country, tripKey,
        best: { min_eur: f.price_eur, typical_eur: f.typical_eur, date: f.dep_date, ret: f.ret_date, origin: f.origin, source: f.source } };
      byDest.set(f.dest, row);
    }
    return [...byDest.values()];
  }
  return out;
}
function mapCount() { const el = $("#c-map"); if (el) el.textContent = state.dest?.length ? mapRows().length || "" : ""; }
async function renderMap() {
  const el = $("#tab-map");
  mapCount();
  if (!state.dest?.length) { el.innerHTML = emptyState(); return; }
  if (!el.querySelector(".map-wrap")) {
    el.innerHTML = `<div class="map-head">
        <div class="seg map-region"><button data-mreg="eu" class="${MAP.region === "eu" ? "on" : ""}">Europa</button><button data-mreg="world" class="${MAP.region === "world" ? "on" : ""}">Toată lumea</button></div>
        <label class="map-budget">Buget maxim <input type="range" id="map-max" min="10" max="500" step="5"> <b id="map-max-v"></b></label>
        <span class="map-count" id="map-count"></span>
      </div>
      <div class="map-wrap"><svg id="map-svg" viewBox="0 0 960 560" role="img" aria-label="Harta cu prețurile zborurilor"></svg><div class="map-tip" id="map-tip" hidden></div>
        <div class="map-loading" id="map-loading">Se încarcă harta…</div></div>
      <div class="map-legend" id="map-legend"></div>
      <div class="map-top" id="map-top"></div>`;
    el.querySelector(".map-region").addEventListener("click", e => {
      const b = e.target.closest("[data-mreg]"); if (!b) return;
      MAP.region = b.dataset.mreg; MAP.max = null;
      el.querySelectorAll("[data-mreg]").forEach(x => x.classList.toggle("on", x === b));
      drawMap();
    });
    $("#map-max").addEventListener("input", e => { MAP.max = +e.target.value; drawMap(false); });
  }
  try { await mapLibs(); } catch (e) { $("#map-loading").textContent = "Harta nu s-a putut încărca. Verifică conexiunea la internet."; return; }
  $("#map-loading").hidden = true;
  drawMap();
}
function drawMap(full = true) {
  const svg = d3.select("#map-svg");
  if (svg.empty() || !MAP.world) return;
  const dark = document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  const eu = MAP.region === "eu";
  const all = mapRows().map(r => ({ ...r, xy: MAP.coords[r.dest] })).filter(r => r.xy)
    .filter(r => !eu || (r.xy[0] > -26 && r.xy[0] < 46 && r.xy[1] > 27 && r.xy[1] < 72));
  // bugetul: implicit toate; sliderul merge până la cel mai scump preț din regiune
  const hi = Math.max(20, ...all.map(r => r.best.min_eur));
  const slider = $("#map-max");
  slider.max = Math.ceil(hi / 5) * 5;
  if (MAP.max == null || MAP.max > +slider.max) MAP.max = +slider.max;
  slider.value = MAP.max;
  $("#map-max-v").textContent = eur(MAP.max);
  const rows = all.filter(r => r.best.min_eur <= MAP.max).sort((a, b) => b.best.min_eur - a.best.min_eur);
  $("#map-count").textContent = `${rows.length} destinații · ${all[0]?.tripKey === "RT" ? "dus-întors" : "dus"}${state.origin !== "ALL" ? " · din " + (ORIGIN_NAMES[state.origin] || state.origin) : ""}`;
  // culori: treimi de preț (ieftin / mediu / mai scump), calculate pe destinațiile afișate
  const sorted = all.map(r => r.best.min_eur).sort((a, b) => a - b);
  const q1 = sorted[Math.floor(sorted.length / 3)] ?? 0, q2 = sorted[Math.floor(sorted.length * 2 / 3)] ?? 0;
  const tone = p => p <= q1 ? "#0F6E56" : p <= q2 ? "#5DCAA5" : "#EF9F27";
  $("#map-legend").innerHTML = sorted.length ? `<span><i style="background:#0F6E56"></i>până la ${eur(q1)}</span><span><i style="background:#5DCAA5"></i>${eur(q1)} – ${eur(q2)}</span><span><i style="background:#EF9F27"></i>peste ${eur(q2)}</span><span><i class="o"></i>orașele de plecare</span><span class="muted">Apasă pe un oraș pentru calendarul prețurilor</span>` : "";
  const proj = eu ? d3.geoConicConformal().center([11, 49]).rotate([-3, 0]).parallels([35, 62]).scale(1080).translate([480, 300])
                  : d3.geoNaturalEarth1().scale(175).translate([470, 300]);
  const path = d3.geoPath(proj);
  if (full || svg.select(".m-land").empty()) {
    svg.selectAll("*").remove();
    svg.append("g").attr("class", "m-land").selectAll("path").data(MAP.world.features).join("path").attr("d", path)
      .attr("fill", dark ? "#2a2a28" : "#ecebe6").attr("stroke", dark ? "#3d3d3a" : "#ffffff").attr("stroke-width", .6);
    svg.append("g").attr("class", "m-arcs"); svg.append("g").attr("class", "m-pins"); svg.append("g").attr("class", "m-origins");
  }
  const origins = [...new Set(rows.map(r => r.best.origin))].filter(o => MAP.coords[o]);
  const oxy = o => proj(MAP.coords[o]);
  const arc = r => { const [x0, y0] = oxy(r.best.origin), [x, y] = proj(r.xy);
    return `M${x0},${y0}Q${(x0 + x) / 2},${(y0 + y) / 2 - Math.hypot(x - x0, y - y0) * .2} ${x},${y}`; };
  svg.select(".m-arcs").selectAll("path").data(rows, r => r.dest).join("path").attr("d", arc)
    .attr("fill", "none").attr("stroke", r => tone(r.best.min_eur)).attr("stroke-width", 1).attr("opacity", .28);
  // etichete doar pentru cele mai ieftine, fără să se suprapună (cel mai ieftin are prioritate)
  const cheapest = new Set(), placed = [];
  for (const r of [...rows].sort((a, b) => a.best.min_eur - b.best.min_eur)) {
    if (cheapest.size >= (eu ? 12 : 10)) break;
    const [x, y] = proj(r.xy), w = 7 * (r.dest_name.length + 7);
    if (placed.some(p => x < p.x + p.w && x + w > p.x && Math.abs(y - p.y) < 16)) continue;
    placed.push({ x, y, w }); cheapest.add(r.dest);
  }
  const pins = svg.select(".m-pins").selectAll("g.pin").data(rows, r => r.dest).join(enter => {
    const g = enter.append("g").attr("class", "pin");
    g.append("circle").attr("class", "hit").attr("r", 12).attr("fill", "transparent");
    g.append("circle").attr("class", "dot").attr("r", 5.5).attr("stroke-width", 2);
    g.append("text").attr("x", 9).attr("y", 4);
    return g;
  });
  pins.attr("transform", r => `translate(${proj(r.xy)})`).attr("data-route", r => `${r.best.origin}|${r.dest}|${r.tripKey}`);
  pins.select(".dot").attr("fill", r => tone(r.best.min_eur)).attr("stroke", dark ? "#1a1a19" : "#fff");
  pins.select("text").text(r => cheapest.has(r.dest) ? `${r.dest_name.replace(/ \(.*\)$/, "")} ${eur(r.best.min_eur)}` : "")
    .attr("fill", dark ? "#f1efe8" : "#2c2c2a").attr("stroke", dark ? "#1a1a19" : "#fff");
  const og = svg.select(".m-origins").selectAll("g").data(origins, o => o).join(enter => {
    const g = enter.append("g"); g.append("circle").attr("r", 7.5).attr("fill", "#D85A30").attr("stroke-width", 2.5);
    g.append("text").attr("x", 11).attr("y", 4).attr("class", "o"); return g; });
  og.attr("transform", o => `translate(${oxy(o)})`);
  og.select("circle").attr("stroke", dark ? "#1a1a19" : "#fff");
  og.select("text").text(o => origins.length <= 2 ? (ORIGIN_NAMES[o] || o) : "").attr("fill", dark ? "#F0997B" : "#993C1D").attr("stroke", dark ? "#1a1a19" : "#fff");
  const tip = $("#map-tip"), wrap = $("#tab-map .map-wrap");
  pins.on("mousemove", (e, r) => {
    const b = wrap.getBoundingClientRect();
    tip.hidden = false;
    tip.style.left = Math.min(e.clientX - b.left + 14, b.width - 200) + "px";
    tip.style.top = (e.clientY - b.top - 12) + "px";
    tip.innerHTML = `<b>${esc(r.dest_name)}</b> <span class="muted">${esc(r.country)}</span><br>de la <b>${eur(r.best.min_eur)}</b> · ${r.tripKey === "RT" ? "dus-întors" : "dus"} din ${esc(ORIGIN_NAMES[r.best.origin] || r.best.origin)}` +
      `<br><span class="muted">${fmtDate(r.best.date, false)}${r.best.ret ? " → " + fmtDate(r.best.ret, false) : ""}${r.best.typical_eur ? " · de obicei " + eur(r.best.typical_eur) : ""}</span>`;
    svg.select(".m-arcs").selectAll("path").attr("opacity", a => a.dest === r.dest ? .95 : .08);
  }).on("mouseleave", () => { tip.hidden = true; svg.select(".m-arcs").selectAll("path").attr("opacity", .28); });
  // sub hartă: cele mai ieftine, ca listă scurtă (merge și pe telefon)
  const top = [...rows].sort((a, b) => a.best.min_eur - b.best.min_eur).slice(0, 12);
  $("#map-top").innerHTML = top.length ? `<div class="map-top-t">Cele mai ieftine pe hartă</div><div class="map-chips">${top.map(r =>
    `<button class="map-chip" data-route="${r.best.origin}|${r.dest}|${r.tripKey}"><b>${esc(r.dest_name.replace(/ \(.*\)$/, ""))}</b><span>${eur(r.best.min_eur)}</span><small>din ${esc(ORIGIN_NAMES[r.best.origin] || r.best.origin)}</small></button>`).join("")}</div>`
    : `<div class="empty">Nicio destinație sub acest buget.</div>`;
}
/* ---------- escale făcute de tine: două bilete low-cost separate, prin hub-urile Ryanair ---------- */
let ESC = null, escP = null;
function loadEscale() {
  if (!escP) escP = api("/api/escale").then(d => { ESC = d || { rows: [] }; }).catch(() => { ESC = { rows: [] }; escP = null; });
  return escP;
}
function escRows() {
  const P = ESC?.places || {};
  return (ESC?.rows || []).map(c => ({ ...c, trip: "OW", origin_name: ORIGIN_NAMES[c.origin] || P[c.origin]?.[0] || c.origin,
    hub_name: P[c.hub]?.[0] || c.hub, dest_name: P[c.dest]?.[0] || c.dest, country: P[c.dest]?.[1] || "" }));
}
function escCard(r) {
  const [s1, d1, t1, p1, a1, link1] = r.l1, [d2, t2, arr2, p2, link2] = r.l2;
  const save = r.direct_eur != null ? r.direct_eur - r.price_eur : null;
  return `<article class="card fc esc">
    ${fcPhoto(r)}
    <div class="fc-head">
      <div class="fc-route">${esc(r.origin_name)}<span class="arrow">→</span>${esc(r.dest_name)}</div>
      <div class="fc-head-r">${save >= 5 ? `<span class="fc-disc num" title="Mai ieftin decât cel mai ieftin zbor direct din ${esc(r.origin_name)}">−${Math.round(save)} €</span>` : ""}</div>
    </div>
    <div class="fc-place">${esc(r.country)}${r.country ? " · " : ""}prin ${esc(r.hub_name)}</div>
    <div class="fc-price"><span class="price num">${eur(r.price_eur)}</span>${leiSpan(r)}</div>
    <div class="esc-direct">${r.direct_eur != null ? `Zbor direct din ${esc(r.origin_name)}: de la <s class="num">${eur(r.direct_eur)}</s>` : `Nu există zbor direct din ${esc(r.origin_name)}`}</div>
    ${fcWeather(r, d2)}
    <ol class="esc-legs">
      <li><span class="esc-n">1</span><div class="esc-leg"><b>${esc(r.origin_name)} → ${esc(r.hub_name)}</b><span>${fmtDate(d1)}, ${t1} · ${esc(a1)} · <b class="num">${eur(p1)}</b></span></div>${bookBtn(link1, a1)}</li>
      <li class="esc-stop">${r.overnight ? `🌙 O noapte la ${esc(r.hub_name)}` : `⏱ Peste 3 ore între zboruri`}</li>
      <li><span class="esc-n">2</span><div class="esc-leg"><b>${esc(r.hub_name)} → ${esc(r.dest_name)}</b><span>${fmtDate(d2)}, ${t2}${arr2 ? "–" + arr2 : ""} · Ryanair · <b class="num">${eur(p2)}</b></span></div>${bookBtn(link2, "Ryanair")}</li>
    </ol>
    ${r.more?.length ? `<div class="esc-more">📅 Alte date, de la ${eur(r.price_eur)} în sus: ${[...new Set(r.more)].sort().map(d => fmtDate(d, false)).join(", ")}</div>` : ""}
    ${s1 === "wizzair" ? `<div class="fc-fee" title="Taxa de administrare Wizz Air, 8–13 € de persoană pe zbor">+ taxa Wizz Air la plată pe primul zbor: 8–13 €</div>` : ""}
  </article>`;
}
/* exotice: dus într-un oraș, întors din altul apropiat */
let ESC_MODE = "eu";
try { ESC_MODE = localStorage.getItem("escMode") === "ex" ? "ex" : "eu"; } catch (e) { /* ignorat */ }
function jawRows() {
  const P = ESC?.places || {};
  return (ESC?.exotic || []).map(c => ({ ...c, trip: "RT", source: "aviasales",
    origin_name: ORIGIN_NAMES[c.origin] || P[c.origin]?.[0] || c.origin, dest_name: P[c.dest]?.[0] || c.dest,
    back_name: P[c.back]?.[0] || c.back, country: P[c.dest]?.[1] || "", back_country: P[c.back]?.[1] || "" }));
}
function jawCard(r) {
  const [d1, t1, p1, a1, link1] = r.l1, [d2, t2, p2, a2, link2] = r.l2;
  const save = r.rt_eur != null ? r.rt_eur - r.price_eur : null;
  const km = r.km.toLocaleString("ro-RO");
  const between = r.km < 60 ? `Te întorci de pe alt aeroport din zonă (${esc(r.back_name)})`
    : `De la ${esc(r.dest_name)} la ${esc(r.back_name)} (~${km} km) ajungi pe cont propriu (zbor scurt, tren sau autobuz), <b>neinclus în preț</b>`;
  return `<article class="card fc esc">
    ${fcPhoto(r)}
    <div class="fc-head">
      <div class="fc-route">${esc(r.origin_name)}<span class="arrow">→</span>${esc(r.dest_name)}</div>
      <div class="fc-head-r">${save >= 5 ? `<span class="fc-disc num" title="Mai ieftin decât cel mai ieftin dus-întors clasic la ${esc(r.dest_name)}">−${Math.round(save)} €</span>` : ""}</div>
    </div>
    <div class="fc-place">${esc(r.country)}${r.country ? " · " : ""}întors din ${esc(r.back_name)}${r.back_country && r.back_country !== r.country ? ", " + esc(r.back_country) : ""}</div>
    <div class="fc-price"><span class="price num">${eur(r.price_eur)}</span>${leiSpan(r)}</div>
    <div class="esc-direct">${r.rt_eur != null ? `Dus-întors clasic la ${esc(r.dest_name)}: de la <s class="num">${eur(r.rt_eur)}</s>` : `Nu am găsit dus-întors clasic la ${esc(r.dest_name)}`}</div>
    ${fcWeather(r, d1)}
    <div class="fc-meta"><span class="fc-tag unv" title="Prețuri găsite recent în căutările altor călători; confirmă-le la „Rezervă”">De verificat</span></div>
    <ol class="esc-legs">
      <li><span class="esc-n">1</span><div class="esc-leg"><b>${esc(r.origin_name)} → ${esc(r.dest_name)}</b><span>${fmtDate(d1)}${t1 ? ", " + t1 : ""} · ${esc(a1)} · <b class="num">${eur(p1)}</b></span></div>${bookBtn(link1, a1)}</li>
      <li class="esc-stop">🧳 ${r.nights} nopți · ${between}</li>
      <li><span class="esc-n">2</span><div class="esc-leg"><b>${esc(r.back_name)} → ${esc(r.origin_name)}</b><span>${fmtDate(d2)}${t2 ? ", " + t2 : ""} · ${esc(a2)} · <b class="num">${eur(p2)}</b></span></div>${bookBtn(link2, a2)}</li>
    </ol>
    ${r.more?.length ? `<div class="esc-more">📅 Alte date, de la ${eur(r.price_eur)} în sus: ${[...new Set(r.more)].sort().map(d => fmtDate(d, false)).join(", ")}</div>` : ""}
  </article>`;
}
function escModeSeg() {
  return `<div class="esc-mode seg" role="group" aria-label="Tip escale">
    <button type="button" data-escmode="eu" class="${ESC_MODE === "eu" ? "on" : ""}">✈️ Europa · două bilete</button>
    <button type="button" data-escmode="ex" class="${ESC_MODE === "ex" ? "on" : ""}">🌴 Exotice · întors din alt oraș</button>
  </div>`;
}
function renderJaws(el) {
  const all = jawRows();
  const w = datesInvalid() ? null : dateWindow();
  const q = state.q.trim().toLowerCase(), max = parseFloat(state.max);
  const rows = all.filter(r => (state.origin === "ALL" || r.origin === state.origin) && (!max || r.price_eur <= max) &&
    (!q || `${r.dest_name} ${r.country} ${r.dest} ${r.back_name} ${r.back_country} ${r.back}`.toLowerCase().includes(q)) &&
    (!w || (r.dep_date >= w.depFrom && r.dep_date <= w.depTo && (!w.retFrom || (r.ret_date >= w.retFrom && r.ret_date <= w.retTo)))))
    .sort((a, b) => a.price_eur - b.price_eur);
  const byRoute = new Map();
  for (const r of rows) {
    const k = `${r.origin}|${r.dest}|${r.back}`;
    if (byRoute.has(k)) byRoute.get(k).more.push(r.dep_date); else byRoute.set(k, { ...r, more: [] });
  }
  const cards = [...byRoute.values()];
  const head = escModeSeg() + `<div class="banner info">🌴 <div><b>Dus într-un oraș, întors din altul:</b> zbori, de exemplu, la Hanoi și te întorci din Ho Chi Minh, sau la Bangkok și înapoi din Singapore. Vezi două locuri într-o excursie și adesea plătești mai puțin decât un dus-întors clasic. Arătăm doar orașe la cel mult 2.000 km unul de altul.</div></div>
    <div class="banner warn">⚠️ <div><b>Sunt două bilete dus separate</b>, iar prețurile sunt găsite recent în căutările altor călători: confirmă-le la „Rezervă”. Drumul dintre cele două orașe îl faci pe cont propriu și <b>nu e inclus în preț</b>.</div></div>`
    + datesBanner("Combinațiile sunt");
  if (!all.length) { el.innerHTML = head + `<div class="empty">Combinațiile apar după următoarea scanare completă.</div>`; return; }
  if (!rows.length) { el.innerHTML = head + `<div class="empty">Nicio combinație pentru filtrele alese.</div>`; return; }
  el.innerHTML = head + shelves("escale", cards, jawCard, ["origin", "month", "country"], "combinații");
  initShelves(el);
}
async function renderEscale() {
  const el = $("#tab-escale");
  if (!ESC) { el.innerHTML = `<div class="empty">Caut combinațiile…</div>`; await loadEscale(); if (state.tab !== "escale") return; }
  if (ESC_MODE === "ex") { renderJaws(el); return; }
  const all = escRows();
  const w = datesInvalid() ? null : dateWindow();
  const q = state.q.trim().toLowerCase(), max = parseFloat(state.max);
  const rows = all.filter(r => (state.origin === "ALL" || r.origin === state.origin) && (!max || r.price_eur <= max) &&
    (!q || `${r.dest_name} ${r.country} ${r.dest} ${r.hub_name}`.toLowerCase().includes(q)) &&
    (!w || (r.dep_date >= w.depFrom && r.dep_date <= w.depTo))).sort((a, b) => a.price_eur - b.price_eur);
  // o singură carte pe destinație (cea mai ieftină), cu numărul celorlalte date găsite
  const byRoute = new Map();
  for (const r of rows) {
    const k = `${r.origin}|${r.dest}`;
    if (byRoute.has(k)) byRoute.get(k).more.push(r.dep_date); else byRoute.set(k, { ...r, more: [] });
  }
  const cards = [...byRoute.values()];
  const c = $("#c-escale"); if (c) c.textContent = all.length ? cards.length : "";

  const head = escModeSeg() + `<div class="banner info">🔀 <div><b>Escale făcute de tine:</b> două zboruri low-cost separate, prin aeroporturile mari Ryanair (Bergamo, Barcelona, Charleroi…), mai ieftine decât zborul direct sau spre locuri unde nu există zbor direct. Prețuri pentru un drum (doar dus).</div></div>
    <div class="banner warn">⚠️ <div><b>Sunt bilete separate.</b> Dacă primul zbor întârzie, al doilea nu te așteaptă și nu primești despăgubire. Recomandat doar cu bagaj de mână. Am ales numai combinații cu <b>peste 3 ore între zboruri</b> sau cu o noapte la escală.</div></div>`
    + (state.dep && !datesInvalid() ? `<div class="banner">📅 <div>Escalele sunt doar dus: se arată cele cu plecare pe datele tale (<b>${fmtDate(w.depFrom, false)}${w.depTo !== w.depFrom ? " – " + fmtDate(w.depTo, false) : ""}</b>). <button class="linkish" data-clear-dates>Arată toate datele</button></div></div>` : "");
  if (!all.length) { el.innerHTML = head + `<div class="empty">Combinațiile apar după următoarea scanare completă.</div>`; return; }
  if (!rows.length) { el.innerHTML = head + `<div class="empty">Nicio escală pentru filtrele alese.</div>`; return; }
  el.innerHTML = head + shelves("escale", cards, escCard, ["origin", "month", "country"], "escale");
  initShelves(el);
}
function renderAll() {
  filtersSummary();
  renderDeals(); renderSearch(); renderLM(); renderDest(); renderExotic(); renderPosts(); renderHelp();
  if (state.tab === "map") renderMap(); else mapCount();
  if (state.tab === "escale") renderEscale();
  if (state.tab === "favs") renderFavs(); else saveFavs();
}

/* ---------- modal rută ---------- */
async function openRoute(origin, dest, trip) {
  const dlg = $("#route-modal");
  $("#rm-title").textContent = `${ORIGIN_NAMES[origin] || origin} → …`;
  $("#rm-sub").textContent = "";
  $("#rm-body").innerHTML = `<p class="muted">Se încarcă…</p>`;
  if (!dlg.open) dlg.showModal();
  const [r, dd] = await Promise.all([
    api(`/api/route?origin=${origin}&dest=${dest}${exactQ("&")}`),
    api(`/api/route-deals?origin=${origin}&dest=${dest}&trip=${trip}`),
  ]);
  $("#rm-title").textContent = `${r.origin_name} → ${r.dest_name}`;
  $("#rm-sub").textContent = `${r.country ? r.country + " · " : ""}${origin} → ${dest}`;
  const minDisc = state.status?.settings?.rules?.min_discount_pct ?? 40;
  const stOW = r.stats.OW || {}, stRT = r.stats.RT || {};
  const minOW = r.calendar_ow.length ? Math.min(...r.calendar_ow.map(x => x.price_eur)) : null;
  const minRT = r.calendar_rt.length ? Math.min(...r.calendar_rt.map(x => x.price_eur)) : null;
  $("#rm-body").innerHTML = `
    <div class="stats">
      <div class="stat"><div class="k">Cel mai ieftin dus</div><div class="v num">${eur(minOW)}</div></div>
      <div class="stat"><div class="k">Obișnuit (dus)</div><div class="v num">${eur(stOW.typical_eur)}</div></div>
      <div class="stat"><div class="k">Cel mai ieftin dus-întors</div><div class="v num">${eur(minRT)}</div></div>
      <div class="stat"><div class="k">Istoric</div><div class="v num">${stOW.history_days || 0} ${(stOW.history_days || 0) === 1 ? "zi" : "zile"}</div></div>
    </div>
    <div class="chart-card">
      <h3>Prețul pe zile de plecare · doar dus</h3>
      <p class="sub">Cel mai mic preț pentru fiecare zi. Barele închise la culoare sunt cu ≥${minDisc}% sub prețul obișnuit.</p>
      <div class="legend"><span><i style="background:var(--series-1)"></i>Ofertă</span><span><i style="background:var(--series-1-soft)"></i>Alte zile</span><span><i class="dash"></i>Preț obișnuit</span></div>
      <div class="chart" id="ch-ow"></div>
    </div>
    ${r.calendar_rt.length ? `<div class="chart-card">
      <h3>Dus-întors, după ziua plecării</h3>
      <p class="sub">Cel mai ieftin retur între ${state.status?.settings?.round_trip?.min_nights ?? 2} și ${state.status?.settings?.round_trip?.max_nights ?? 10} nopți.</p>
      <div class="legend"><span><i style="background:var(--series-1)"></i>Ofertă</span><span><i style="background:var(--series-1-soft)"></i>Alte zile</span><span><i class="dash"></i>Preț obișnuit</span></div>
      <div class="chart" id="ch-rt"></div>
    </div>` : ""}
    <div class="chart-card">
      <h3>Istoricul prețului pe rută · doar dus</h3>
      <p class="sub">Cum au evoluat prețurile de la o zi la alta (minimul și mediana tuturor datelor de plecare).</p>
      <div id="ch-hist-wrap"></div>
    </div>
    ${(dd[0] || r.cheapest[0]) ? compareLinks(dd[0] || r.cheapest[0]).replace('class="compare"', 'class="compare open modal-compare"') : ""}
    <h3 style="font-size:14px;margin:4px 0 8px">${dd.length ? `Datele cu oferte (${tripLabel({ trip })})` : "Cele mai ieftine bilete"}</h3>
    <div class="list">${(dd.length ? dd : r.cheapest.filter(x => x.trip === trip)).slice(0, 30).map(x => `
      <div class="list-row">
        <span class="p num">${eur(x.price_eur)}<br><span class="muted" style="font-size:12px;font-weight:600">${fmtLei(x.price_ron)}</span></span>
        <span style="flex:1 1 200px">${whenText(x)} <span class="muted">· ${esc(x.airline || "")}</span></span>
        <span class="badges">${badges(x.flags)}</span>
        ${bookBtn(x.link || x.gf_link, x.airline)}
        ${verifyBtn(x)}
      </div>`).join("") || `<p class="muted">Nu există bilete.</p>`}</div>`;

  barChart($("#ch-ow"), r.calendar_ow.map(x => ({ x: x.dep_date, y: x.price_eur })), stOW.typical_eur, minDisc);
  if (r.calendar_rt.length) barChart($("#ch-rt"), r.calendar_rt.map(x => ({ x: x.dep_date, y: x.price_eur })), stRT.typical_eur, minDisc);
  const hist = r.history.filter(h => h.trip === "OW");
  if (hist.length >= 2) {
    $("#ch-hist-wrap").innerHTML = `<div class="legend"><span><i class="line" style="background:var(--series-1)"></i>Cel mai mic preț</span><span><i class="line" style="background:var(--series-2)"></i>Prețul median</span></div><div class="chart" id="ch-hist"></div>`;
    lineChart($("#ch-hist"), hist);
  } else {
    $("#ch-hist-wrap").innerHTML = `<p class="muted">Graficul apare după cel puțin 2 zile de monitorizare.</p>`;
  }
}

/* ---------- grafice (SVG) ---------- */
const tip = $("#tooltip");
function showTip(html, ev) {
  tip.innerHTML = html; tip.hidden = false;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = ev.clientX + 14, y = ev.clientY - h - 10;
  if (x + w > innerWidth - 8) x = ev.clientX - w - 14;
  if (y < 8) y = ev.clientY + 16;
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
function hideTip() { tip.hidden = true; }
function niceMax(v) {
  if (v <= 0) return { max: 10, step: 2.5 };
  const raw = v / 4, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(s => s * mag).find(s => s >= raw);
  return { max: step * 4, step };
}
function barChart(el, pts, typical, minDisc) {
  if (!pts.length) { el.innerHTML = `<p class="muted">Nu există bilete.</p>`; return; }
  const W = Math.max(el.clientWidth, 300), H = 200, m = { t: 10, r: 8, b: 24, l: 44 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const { max, step } = niceMax(Math.max(...pts.map(p => p.y), typical || 0));
  const first = d0(pts[0].x), last = d0(pts[pts.length - 1].x);
  const days = Math.round((last - first) / 864e5) + 1;
  const slot = iw / days;
  const bw = Math.max(1, Math.min(18, slot - 2));
  const y = v => m.t + ih - (v / max) * ih;
  const xOf = iso => m.l + Math.round((d0(iso) - first) / 864e5) * slot + (slot - bw) / 2;
  const thr = typical ? typical * (1 - minDisc / 100) : -1;
  let s = "";
  for (let v = 0; v <= max + 1e-9; v += step) {
    s += `<line class="grid-line" x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${Math.round(v)} €</text>`;
  }
  // etichete lună
  const d = new Date(first);
  d.setDate(1);
  while (d <= last) {
    if (d >= first) {
      const x = m.l + Math.round((d - first) / 864e5) * slot;
      s += `<line class="grid-line" x1="${x}" x2="${x}" y1="${m.t}" y2="${m.t + ih}"/><text x="${x + 3}" y="${H - 6}">${MONTHS[d.getMonth()]}</text>`;
    } else {
      // eticheta lunii începute doar dacă are loc până la luna următoare (altfel se suprapun)
      const next = new Date(d.getFullYear(), d.getMonth() + 1, 1);
      if (Math.round((next - first) / 864e5) * slot > 30) s += `<text x="${m.l}" y="${H - 6}">${MONTHS[first.getMonth()]}</text>`;
    }
    d.setMonth(d.getMonth() + 1);
  }
  pts.forEach((p, i) => {
    const x = xOf(p.x), top = y(p.y), h = m.t + ih - top, r = Math.min(4, bw / 2, h);
    const deal = p.y <= thr;
    s += `<path class="bar${deal ? " deal" : ""}" data-i="${i}" d="M${x},${m.t + ih} V${top + r} Q${x},${top} ${x + r},${top} H${x + bw - r} Q${x + bw},${top} ${x + bw},${top + r} V${m.t + ih} Z"/>`;
  });
  if (typical) s += `<line class="ref-line" x1="${m.l}" x2="${W - m.r}" y1="${y(typical)}" y2="${y(typical)}"/>`;
  pts.forEach((p, i) => {
    const x = m.l + Math.round((d0(p.x) - first) / 864e5) * slot;
    s += `<rect class="hit" data-i="${i}" x="${x}" y="${m.t}" width="${Math.max(slot, 4)}" height="${ih}"/>`;
  });
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Prețuri pe zile">${s}</svg>`;
  const bars = $$(".bar", el);
  $$(".hit", el).forEach(hit => {
    const i = +hit.dataset.i, p = pts[i];
    hit.addEventListener("mousemove", ev => {
      bars.forEach(b => b.classList.toggle("hover", +b.dataset.i === i));
      const diff = typical ? Math.round((typical - p.y) / typical * 100) : null;
      showTip(`<b>${eur(p.y)}</b> · ${lei(p.y)}<br>${fmtDate(p.x)}${diff != null ? `<br>${diff > 0 ? "−" + diff + "% sub" : "+" + (-diff) + "% peste"} obișnuit` : ""}`, ev);
    });
    hit.addEventListener("mouseleave", () => { hideTip(); bars.forEach(b => b.classList.remove("hover")); });
  });
}
function lineChart(el, rows) {
  const W = Math.max(el.clientWidth, 300), H = 180, m = { t: 12, r: 70, b: 24, l: 44 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const { max, step } = niceMax(Math.max(...rows.map(r => r.p50_eur)));
  const n = rows.length;
  const x = i => m.l + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
  const y = v => m.t + ih - (v / max) * ih;
  let s = "";
  for (let v = 0; v <= max + 1e-9; v += step) {
    s += `<line class="grid-line" x1="${m.l}" x2="${m.l + iw}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${Math.round(v)} €</text>`;
  }
  const every = Math.max(1, Math.ceil(n / 8));
  rows.forEach((r, i) => { if (i % every === 0 || i === n - 1) s += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${fmtDate(r.day, false)}</text>`; });
  const path = key => rows.map((r, i) => `${i ? "L" : "M"}${x(i)},${y(r[key])}`).join(" ");
  s += `<path class="line-2" d="${path("p50_eur")}"/><path class="line-1" d="${path("min_eur")}"/>`;
  const lr = rows[n - 1];
  s += `<text class="dlabel" x="${x(n - 1) + 8}" y="${y(lr.min_eur) + 4}">${eur(lr.min_eur)}</text>`;
  s += `<text class="dlabel" x="${x(n - 1) + 8}" y="${y(lr.p50_eur) + 4}">${eur(lr.p50_eur)}</text>`;
  s += `<line class="cross" id="cross" x1="0" x2="0" y1="${m.t}" y2="${m.t + ih}" visibility="hidden"/>`;
  s += `<circle class="dot-1" id="dot1" r="4" visibility="hidden"/><circle class="dot-2" id="dot2" r="4" visibility="hidden"/>`;
  s += `<rect class="hit" x="${m.l}" y="${m.t}" width="${iw}" height="${ih}"/>`;
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Istoric prețuri">${s}</svg>`;
  const svg = $("svg", el), cross = $("#cross", el), d1 = $("#dot1", el), d2 = $("#dot2", el);
  $(".hit", el).addEventListener("mousemove", ev => {
    const rect = svg.getBoundingClientRect();
    const px = (ev.clientX - rect.left) * (W / rect.width);
    const i = Math.max(0, Math.min(n - 1, Math.round(((px - m.l) / iw) * (n - 1))));
    const r = rows[i];
    [cross, d1, d2].forEach(e => e.setAttribute("visibility", "visible"));
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i));
    d1.setAttribute("cx", x(i)); d1.setAttribute("cy", y(r.min_eur));
    d2.setAttribute("cx", x(i)); d2.setAttribute("cy", y(r.p50_eur));
    showTip(`<b>${fmtDate(r.day)}</b><br>Minim: ${eur(r.min_eur)}<br>Median: ${eur(r.p50_eur)}`, ev);
  });
  $(".hit", el).addEventListener("mouseleave", () => { hideTip(); [cross, d1, d2].forEach(e => e.setAttribute("visibility", "hidden")); });
}

/* ---------- evenimente ---------- */
function setTab(t) {
  if (!$(`#tab-${t}`)) t = "deals";
  state.tab = t;
  if (state.tabInit) gcEvent("tab: " + t); state.tabInit = true;
  $$(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
  for (const id of ["deals", "search", "lm", "dest", "map", "escale", "exotic", "favs", "posts", "help"]) $(`#tab-${id}`).hidden = id !== t;
  if (t === "map") renderMap();
  if (t === "escale") renderEscale();
  $("#filters").hidden = t === "help" || t === "favs";
  if (t === "favs") renderFavs();
  $("#f-sort-wrap").hidden = !["deals", "search", "lm", "dest", "exotic"].includes(t);
  $("#f-origin").hidden = t === "exotic";
  $("#quick-origins").hidden = t === "exotic" || t === "help" || t === "favs";
  $("#f-days-wrap").hidden = t !== "lm";
  try { localStorage.setItem("tab", t); } catch (e) { /* ignorat */ }
  if (innerWidth <= 700) $(`.tab[data-tab="${t}"]`)?.scrollIntoView({ inline: "nearest", block: "nearest" });
}
// pe telefon, bara de tab-uri se derulează: estompăm marginea unde mai sunt tab-uri
function tabsEdges() {
  const n = $(".tabs");
  n.classList.toggle("more-l", n.scrollLeft > 4);
  n.classList.toggle("more-r", n.scrollLeft + n.clientWidth < n.scrollWidth - 4);
}
$(".tabs").addEventListener("scroll", tabsEdges, { passive: true });
addEventListener("resize", tabsEdges);
setTimeout(tabsEdges, 0);
function renderOriginChips(codes) {
  const key = codes.join(",");
  if (renderOriginChips.last === key) return;
  renderOriginChips.last = key;
  const list = [{ code: "ALL", name: "Toate" }, ...codes.map(c => ({ code: c, name: ORIGIN_NAMES[c] || c }))];
  const html = list.map(o => `<button class="chip${o.code === state.origin ? " on" : ""}" data-v="${o.code}">${o.name}</button>`).join("");
  $("#f-origin").innerHTML = html.replace(">Toate<", ">Toate orașele<");
  $("#quick-origins").innerHTML = html;
  $("#cities-line").innerHTML = codes.map(c => esc(ORIGIN_NAMES[c] || c)).join('<span class="sep" aria-hidden="true">✦</span>');
}
function initFilters() {
  renderOriginChips(Object.keys(ORIGIN_NAMES));
  for (const box of ["#f-origin", "#quick-origins"]) {
    $(box).addEventListener("click", e => {
      const b = e.target.closest(".chip"); if (!b) return;
      state.origin = b.dataset.v;
      $$("#f-origin .chip, #quick-origins .chip").forEach(c => c.classList.toggle("on", c.dataset.v === state.origin));
      renderAll();
    });
  }
  $("#f-trip").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    state.trip = b.dataset.v;
    $$("#f-trip button").forEach(c => c.classList.toggle("on", c === b));
    renderAll();
  });
  $("#f-max").addEventListener("input", e => { state.max = e.target.value; renderAll(); });
  $("#f-q").addEventListener("input", e => { state.q = e.target.value; renderAll(); });
  $("#f-sort").addEventListener("change", e => {
    state.sort = e.target.value;
    try { localStorage.setItem("sort", state.sort); } catch (err) { /* ignorat */ }
    renderAll();
  });
  try {
    const saved = localStorage.getItem("sort");
    if (saved && $(`#f-sort option[value="${saved}"]`)) { state.sort = saved; $("#f-sort").value = saved; }
  } catch (err) { /* ignorat */ }
  const dep = $("#f-dep"), ret = $("#f-ret");
  dep.min = ret.min = todayIso();
  dep.addEventListener("change", () => {
    state.dep = dep.value;
    if (state.dep) ret.min = isoAdd(state.dep, 1);
    onDatesChanged();
  });
  ret.addEventListener("change", () => { state.ret = ret.value; onDatesChanged(); });
  $("#f-flex").addEventListener("change", e => { state.flex = +e.target.value; onDatesChanged(); });
  try { const v = localStorage.getItem("exact2"); state.exact = v === null ? true : v === "1"; } catch (err) { /* ignorat */ }
  $("#f-exact").checked = state.exact;
  $("#f-exact").addEventListener("change", e => {
    state.exact = e.target.checked;
    try { localStorage.setItem("exact2", state.exact ? "1" : "0"); } catch (err) { /* ignorat */ }
    filtersSummary();
    loadData();
  });
  try {
    const p = JSON.parse(localStorage.getItem("paxv2") || "null");
    if (p) { state.adults = Math.max(1, +p.a || 1); state.children = Math.max(0, +p.c || 0); state.infants = Math.min(state.adults, Math.max(0, +p.i || 0)); }
  } catch (err) { /* ignorat */ }
  state.pax = seats();
  renderPax();
  const pop = $("#pax-pop"), pbtn = $("#pax-btn");
  const openPax = open => { pop.hidden = !open; pbtn.setAttribute("aria-expanded", open); };
  pbtn.addEventListener("click", () => openPax(pop.hidden));
  $("#pax-done").addEventListener("click", () => openPax(false));
  pop.addEventListener("click", e => {
    const b = e.target.closest("button[data-d]"); if (!b) return;
    setPax(b.closest(".pax-row").dataset.k, +b.dataset.d);
  });
  document.addEventListener("click", e => { if (!pop.hidden && !e.target.closest(".pax-field")) openPax(false); });
  $("#f-dates-clear").addEventListener("click", clearDates);
  $("#f-days").addEventListener("change", async e => {
    state.days = +e.target.value;
    state.lm = await api(`/api/lastminute?days=${state.days}${exactQ("&")}`);
    renderLM();
  });
}
function clearDates() {
  state.dep = state.ret = "";
  $("#f-dep").value = $("#f-ret").value = "";
  $("#f-ret").min = todayIso();
  onDatesChanged();
}
document.addEventListener("click", async e => {
  if (e.target.id === "btn-copy-link") {
    try { await navigator.clipboard.writeText(e.target.dataset.url); e.target.textContent = "Copiat ✓"; }
    catch (err) { prompt("Copiază linkul:", e.target.dataset.url); }
    setTimeout(() => { e.target.textContent = "Copiază linkul site-ului"; }, 2500);
    return;
  }
  const ct = e.target.closest(".cmp-toggle");
  if (ct) { ct.parentElement.classList.toggle("open"); return; }
  const gb = e.target.closest("[data-gfcheck]");
  if (gb) { runGfCheck(gb); return; }
  const vb = e.target.closest("[data-verify]");
  if (vb) { runVerify(vb); return; }
  if (e.target.closest("[data-clear-dates]")) { clearDates(); return; }
  const fd = e.target.closest("[data-fav-del]");
  if (fd) { delete state.favs[fd.dataset.favDel]; saveFavs(); renderFavs(); renderAll(); return; }
  if (e.target.closest("[data-fav-clear]")) {
    if (confirm("Ștergi toate zborurile din favorite?")) { state.favs = {}; saveFavs(); renderFavs(); renderAll(); }
    return;
  }
  const fv = e.target.closest("[data-fav]");
  if (fv) { toggleFav(fv.dataset.fav); return; }
  const sn = e.target.closest("[data-shelf-nav]");
  if (sn) { const row = sn.closest(".shelf").querySelector(".shelf-row"); row.scrollBy({ left: +sn.dataset.shelfNav * row.clientWidth * 0.9, behavior: "smooth" }); return; }
  const st = e.target.closest("[data-shelf-toggle]");
  if (st) { toggleShelf(st.dataset.shelfToggle); return; }
  const em = e.target.closest("[data-escmode]");
  if (em) { ESC_MODE = em.dataset.escmode; try { localStorage.setItem("escMode", ESC_MODE); } catch (err) { /* ignorat */ } renderEscale(); return; }
  const exr = e.target.closest("[data-exregion]");
  if (exr) { state.exRegion = exr.dataset.exregion; renderExotic(); return; }
  const t = e.target.closest("[data-tab]");
  if (t) { setTab(t.dataset.tab); if (t.closest(".tabs") && innerWidth <= 700) scrollTo({ top: 0 }); return; }
  const r = e.target.closest("[data-route]");
  if (r) { const [o, d, trip] = r.dataset.route.split("|"); openRoute(o, d, trip); return; }
  if (e.target.id === "btn-feeds") {
    e.target.textContent = "Se verifică…";
    await post("/api/feeds");
    state.posts = await api("/api/posts");
    await loadStatus();
    renderPosts();
    return;
  }
  if (e.target.id === "btn-tg-test") {
    const res = await post("/api/telegram-test");
    e.target.textContent = res.ok ? "Trimis ✓" : (res.message || "Eroare");
  }
});
$("#filters-toggle").addEventListener("click", () => {
  const f = $("#filters");
  f.classList.toggle("open");
  $("#filters-toggle").setAttribute("aria-expanded", f.classList.contains("open"));
});
$("#btn-quick").addEventListener("click", async () => {
  const res = await post("/api/scan?quick=1");
  if (!res.ok && res.message) alert(res.message);
  setTimeout(loadStatus, 800);
});
$("#btn-scan").addEventListener("click", async () => {
  const res = await post("/api/scan");
  if (!res.ok && res.message) alert(res.message);
  setTimeout(loadStatus, 800);
});
$("#rm-close").addEventListener("click", () => $("#route-modal").close());
/* ---------- 🎲 Surprinde-mă: o destinație la întâmplare, în bugetul ales ---------- */
const SURP = { budget: 50, trip: "OW", last: [] };
function surprisePool() {
  const best = new Map();  // cel mai ieftin zbor spre fiecare destinație, ca fiecare loc să aibă aceeași șansă
  for (const r of [...(state.search || []), ...(state.deals || []), ...(state.lm || [])]) {
    if (r.trip !== SURP.trip || !(r.price_eur <= SURP.budget) || r.days_to_dep < 1) continue;
    if (state.origin !== "ALL" && r.origin !== state.origin) continue;
    if (!best.has(r.dest) || r.price_eur < best.get(r.dest).price_eur) best.set(r.dest, r);
  }
  return [...best.values()];
}
function renderSurprise() {
  $$("#sp-budget button").forEach(b => b.classList.toggle("on", +b.dataset.v === SURP.budget));
  $$("#sp-trip button").forEach(b => b.classList.toggle("on", b.dataset.v === SURP.trip));
  const pool = surprisePool(), body = $("#sp-body");
  const from = state.origin !== "ALL" ? " din " + esc(ORIGIN_NAMES[state.origin]) : "";
  $("#sp-again").hidden = pool.length < 2;
  if (!pool.length) {
    body.innerHTML = `<div class="empty">Nu am găsit zboruri ${SURP.trip === "RT" ? "dus-întors" : "dus"} sub ${SURP.budget} €${from}${state.dep ? " pe datele alese" : ""}. Încearcă un buget mai mare.</div>`;
    return;
  }
  const fresh = pool.filter(r => !SURP.last.includes(r.dest)), from2 = fresh.length ? fresh : pool;
  const pick = from2[Math.floor(Math.random() * from2.length)];
  SURP.last = [pick.dest, ...SURP.last].slice(0, Math.min(8, pool.length - 1));
  body.innerHTML = `<p class="sp-count muted">Ales la întâmplare dintre <b>${pool.length}</b> ${pool.length === 1 ? "destinație" : "destinații"} sub ${SURP.budget} €${from}${state.dep ? ", pe datele tale" : ""}.</p><div class="sp-card">${flightCard(pick)}</div>`;
}
$("#btn-surprise").addEventListener("click", () => { $("#surprise-modal").showModal(); renderSurprise(); });
$("#sp-close").addEventListener("click", () => $("#surprise-modal").close());
$("#surprise-modal").addEventListener("click", e => {
  if (e.target.id === "surprise-modal") { e.target.close(); return; }
  const b = e.target.closest("#sp-budget button"), t = e.target.closest("#sp-trip button");
  if (b) { SURP.budget = +b.dataset.v; SURP.last = []; renderSurprise(); }
  if (t) { SURP.trip = t.dataset.v; SURP.last = []; renderSurprise(); }
  if (e.target.closest("#sp-again")) renderSurprise();
  if (e.target.closest("[data-route]")) e.currentTarget.close();
});
$("#route-modal").addEventListener("click", e => { if (e.target.id === "route-modal") e.target.close(); });
$("#btn-theme").addEventListener("click", () => {
  const cur = document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("theme", next); } catch (e) { /* ignorat */ }
});

(function init() {
  try {
    const th = localStorage.getItem("theme"); if (th) document.documentElement.dataset.theme = th;
    const tb = localStorage.getItem("tab"); if (tb) state.tab = tb;
  } catch (e) { /* ignorat */ }
  initFilters();
  setTab(state.tab);
  loadStatus().then(() => { if (!state.lastScanId) loadData(); });
  if (STATIC) { $("#btn-scan").hidden = true; $("#btn-quick").hidden = true; }
  else {  // doar pe laptop (site-ul „din spate”): pagina în care alegi pozele destinațiilor
    const a = document.createElement("a");
    a.href = "poze.html"; a.className = "btn small ghost"; a.textContent = "🖼 Poze"; a.title = "Verifică și schimbă pozele destinațiilor";
    $("#btn-theme").before(a);
    const v = document.createElement("a");
    v.href = "vizitatori.html"; v.className = "btn small ghost"; v.textContent = "📊 Vizitatori"; v.title = "Câte persoane intră pe site-ul public";
    a.before(v);
  }

  setInterval(loadStatus, STATIC ? 60000 : 8000);
})();
