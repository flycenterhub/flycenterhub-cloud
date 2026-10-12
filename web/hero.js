/* Căutarea simplă de sus („Unde zbori ieftin?”): De unde · Unde · Când · Buget → o singură listă.
   Modul separat: dacă nu-l mai vrem, ștergem <script src="hero.js"> și <link href="hero.css"> din index.html.
   Folosește funcțiile din app.js (api, flightCard, sunny, bestSeason, state…). */
(function () {
  const MOUNTAIN = new Set(["INN", "SZG", "GVA", "ZRH", "BSL", "TRN", "VRN", "BZO", "TSF", "BGY", "LYS", "GNB", "CMF", "SOF", "TAT", "KRK", "MUC", "MXP"]);
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
  const addDays = (s, n) => { const d = new Date(s + "T12:00"); d.setDate(d.getDate() + n); return iso(d); };

  function months() {
    const now = new Date();
    return Array.from({ length: 12 }, (_, i) => new Date(now.getFullYear(), now.getMonth() + i, 1))
      .map(d => [`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`, `${MONTHS_FULL[d.getMonth()]}${d.getFullYear() !== now.getFullYear() ? " " + d.getFullYear() : ""}`]);
  }
  // fereastra de plecare / întoarcere pentru „Când”
  function window_(when) {
    if (!when) return null;
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
    const maxNights = H.when === "weekend" ? 4 : 28;
    rows = rows.filter(r => {
      if (r.trip !== H.trip) return false;
      if (H.from !== "ALL" && r.origin !== H.from) return false;
      if (H.budget && r.price_eur > H.budget) return false;
      if (!(r.days_to_dep >= 1)) return false;
      if (w && r.trip === "RT" && r.ret_date > w.ret[1]) return false;
      if (r.trip === "RT" && r.nights != null && (r.nights < 2 || r.nights > maxNights)) return false;
      const region = reg.by[r.dest];
      if (text) return [r.dest_name, r.country, r.dest].some(x => norm(x).includes(text));
      if (H.where === "beach") return beach(r.dest, +r.dep_date.slice(5, 7) - 1);
      if (H.where === "city") return !region && !MOUNTAIN.has(r.dest);
      if (H.where === "exotic") return !!region;
      if (H.where === "ski") return MOUNTAIN.has(r.dest) && [11, 0, 1, 2, 3].includes(+r.dep_date.slice(5, 7) - 1);
      return true;
    });
    // o singură variantă pe destinație: cea mai ieftină
    const best = new Map();
    for (const r of rows) { const c = best.get(r.dest); if (!c || r.price_eur < c.price_eur) best.set(r.dest, r); }
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
    const when = !H.when ? "oricând" : H.when === "weekend" ? "weekendul acesta" : "în " + (months().find(m => m[0] === H.when) || [, ""])[1].toLowerCase();
    const from = H.from === "ALL" ? "din orice oraș" : "din " + ORIGIN_NAMES[H.from];
    return `${idea === "Oriunde" ? "Oriunde" : idea} ${when}, ${from}${H.budget ? `, sub ${H.budget} €` : ""}`;
  }

  function field(id, label, icon, control) {
    return `<label class="hf" for="${id}"><span class="hf-l">${label}</span><span class="hf-v"><span class="hf-i" aria-hidden="true">${icon}</span>${control}</span></label>`;
  }

  function formHtml() {
    const origins = (state.status?.origins || []).map(o => o.code).filter(c => ORIGIN_NAMES[c]);
    const sel = (v, cur) => v === cur ? " selected" : "";
    return `
      <div class="hero-in">
        <div class="hero-txt">
          <h2 class="hero-h">Lumea e mai <span class="script">aproape</span> decât crezi.</h2>
          <p class="hero-p">Verificăm zilnic mii de zboruri din Timișoara, Cluj, Oradea, București și Budapesta. Tu alegi doar destinația, noi găsim cel mai bun preț.</p>
        </div>
        <form class="hero-box" id="hero-form" autocomplete="off">
          ${field("h-from", "De unde", "🛫", `<select id="h-from"><option value="ALL">Oricare</option>${origins.map(c => `<option value="${c}"${sel(c, H.from)}>${esc(ORIGIN_NAMES[c])}</option>`).join("")}</select>`)}
          ${field("h-text", "Unde", "📍", `<input id="h-text" type="text" placeholder="${esc((IDEAS.find(i => i[0] === H.where) || IDEAS[0])[2])} – sau scrie o țară, un oraș" value="${esc(H.text)}">`)}
          ${field("h-when", "Când", "📅", `<select id="h-when"><option value="">Oricând</option><option value="weekend"${sel("weekend", H.when)}>Weekendul acesta</option>${months().map(([v, l]) => `<option value="${v}"${sel(v, H.when)}>${l}</option>`).join("")}</select>`)}
          ${field("h-budget", "Buget / pers.", "💶", `<select id="h-budget">${BUDGETS.map(b => `<option value="${b}"${sel(b, H.budget)}>${b ? "sub " + b + " €" : "Oricât"}</option>`).join("")}</select>`)}
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
    el.innerHTML = formHtml() + resultsHtml();
  }

  function readForm() {
    H.from = $("#h-from").value; H.when = $("#h-when").value; H.budget = +$("#h-budget").value;
    H.text = $("#h-text").value.trim();
  }

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

  // prima afișare, după ce aplicația a încărcat orașele (status)
  const start = () => {
    if (!state.status) return setTimeout(start, 300);
    H.from = state.origin || "ALL";
    render();
  };
  start();
})();
