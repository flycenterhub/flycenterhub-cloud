/* Cont utilizator (Supabase Auth) + mesajul despre cookie-uri.
   Până se completează SB_URL/SB_KEY (valori publice din Supabase → Project Settings → API), fereastra arată
   „conturile se deschid în curând”. */
(() => {
  const SB_URL = "";  // ex. https://xxxx.supabase.co
  const SB_KEY = "";  // cheia publică „anon” (NU cea „service_role”)
  const LIB = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.min.js";
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const ls = { get: k => { try { return localStorage.getItem(k); } catch { return null; } },
               set: (k, v) => { try { localStorage.setItem(k, v); } catch {} } };
  let sb = null, user = null, mode = "in";

  function client() {
    if (!SB_URL || !SB_KEY) return Promise.resolve(null);
    if (sb) return Promise.resolve(sb);
    return new Promise(ok => {
      const s = document.createElement("script");
      s.src = LIB; s.onload = () => ok(sb = window.supabase.createClient(SB_URL, SB_KEY)); s.onerror = () => ok(null);
      document.head.appendChild(s);
    });
  }

  /* ---------- buton în antet ---------- */
  function button() {
    let b = $("#acct-btn");
    if (!b) {
      b = document.createElement("button");
      b.id = "acct-btn"; b.className = "btn acct-btn";
      const area = $(".status-area");
      area?.insertBefore(b, $("#btn-theme", area) || null);
      b.onclick = e => { e.stopPropagation(); user ? menu() : open("in"); };
    }
    const name = user?.user_metadata?.name || user?.email?.split("@")[0] || "";
    b.innerHTML = user ? `<span class="acct-av">${esc(name[0]?.toUpperCase() || "?")}</span><span class="acct-nm">${esc(name)}</span> ▾`
                       : `👤 <span class="acct-nm">Intră în cont</span>`;
    b.title = user ? "Contul meu" : "Intră în cont sau fă-ți unul nou";
  }

  /* ---------- fereastra Intră / Cont nou ---------- */
  function open(m) {
    mode = m; close();
    const nw = m === "up";
    const d = document.createElement("div");
    d.className = "acct-back"; d.id = "acct-modal";
    d.innerHTML = `<div class="acct-box" role="dialog" aria-modal="true" aria-label="Cont">
      <button class="acct-x" aria-label="Închide">×</button>
      <h3>${nw ? "Cont nou" : "Bine ai revenit"}</h3>
      <p class="acct-s">${nw ? "Gratuit. Durează 10 secunde." : "Intră ca să-ți păstrezi rutele favorite."}</p>
      <div class="acct-seg"><button data-m="in" class="${nw ? "" : "on"}">Intră</button><button data-m="up" class="${nw ? "on" : ""}">Cont nou</button></div>
      <button class="acct-g" type="button"><b>G</b> Continuă cu Google</button>
      <div class="acct-or">sau cu email</div>
      <form novalidate>
        ${nw ? `<label>Nume<input name="name" autocomplete="given-name" placeholder="Andrei"></label>` : ""}
        <label>Email<input name="email" type="email" autocomplete="email" placeholder="nume@exemplu.ro" required></label>
        <label>Parolă${nw ? " (minim 8 caractere)" : ""}<input name="pass" type="password" autocomplete="${nw ? "new-password" : "current-password"}" minlength="8" required></label>
        ${nw ? `<label class="acct-chk"><input type="checkbox" name="ok"> <span>Sunt de acord cu <a href="#" data-info="termeni">Termenii</a> și <a href="#" data-info="confidentialitate">Politica de confidențialitate</a></span></label>
        <label class="acct-chk"><input type="checkbox" name="news"> <span>Vreau oferte pe email (opțional, mă pot dezabona oricând)</span></label>` : ""}
        <div class="acct-msg" role="alert"></div>
        <button class="acct-go" type="submit">${nw ? "Creează contul" : "Intră în cont"}</button>
      </form>
      <div class="acct-small">${nw ? "Îți trimitem un email de confirmare." : `<a href="#" class="acct-forgot">Ai uitat parola?</a>`}</div>
    </div>`;
    document.body.appendChild(d);
    d.addEventListener("click", e => {
      if (e.target === d || e.target.closest(".acct-x")) return close();
      const seg = e.target.closest("[data-m]"); if (seg) return open(seg.dataset.m);
      const inf = e.target.closest("[data-info]"); if (inf) { e.preventDefault(); close(); return info(inf.dataset.info); }
      if (e.target.closest(".acct-g")) return google();
      if (e.target.closest(".acct-forgot")) { e.preventDefault(); return forgot(); }
    });
    $("form", d).onsubmit = submit;
    $("input", d)?.focus();
  }
  const close = () => { $("#acct-modal")?.remove(); $("#acct-menu")?.remove(); };
  const msg = (t, good) => { const m = $("#acct-modal .acct-msg"); if (m) { m.textContent = t; m.classList.toggle("good", !!good); } };
  const soon = () => msg("Conturile se deschid în curând. Mulțumim pentru răbdare!");
  function info(id) {
    document.querySelector('[data-tab="help"]')?.click();
    setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }), 150);
  }

  async function submit(e) {
    e.preventDefault();
    const f = e.target, v = Object.fromEntries(new FormData(f));
    if (!/^\S+@\S+\.\S+$/.test(v.email || "")) return msg("Scrie o adresă de email validă.");
    if ((v.pass || "").length < 8) return msg("Parola trebuie să aibă minim 8 caractere.");
    if (mode === "up" && !v.ok) return msg("Bifează acordul cu Termenii și Politica de confidențialitate.");
    const c = await client(); if (!c) return soon();
    const go = $(".acct-go", f); go.disabled = true;
    const r = mode === "up"
      ? await c.auth.signUp({ email: v.email, password: v.pass, options: { emailRedirectTo: location.origin + location.pathname,
          data: { name: (v.name || "").trim(), news: !!v.news, consent_at: new Date().toISOString() } } })
      : await c.auth.signInWithPassword({ email: v.email, password: v.pass });
    go.disabled = false;
    if (r.error) return msg(ro(r.error.message));
    if (mode === "up" && !r.data.session) return msg("Gata! Verifică emailul și apasă linkul de confirmare.", true);
    close();
  }
  async function google() {
    const c = await client(); if (!c) return soon();
    c.auth.signInWithOAuth({ provider: "google", options: { redirectTo: location.origin + location.pathname } });
  }
  async function forgot() {
    const email = $("#acct-modal input[name=email]")?.value || "";
    if (!/^\S+@\S+\.\S+$/.test(email)) return msg("Scrie întâi emailul, apoi apasă „Ai uitat parola?”.");
    const c = await client(); if (!c) return soon();
    const r = await c.auth.resetPasswordForEmail(email, { redirectTo: location.origin + location.pathname + "#parola-noua" });
    msg(r.error ? ro(r.error.message) : "Ți-am trimis pe email linkul pentru parolă nouă.", !r.error);
  }
  const ro = m => /invalid login/i.test(m) ? "Email sau parolă greșită."
    : /already registered/i.test(m) ? "Există deja un cont cu acest email. Apasă „Intră”."
    : /not confirmed/i.test(m) ? "Confirmă întâi emailul (verifică și Spam)."
    : /rate limit|too many/i.test(m) ? "Prea multe încercări. Mai încearcă peste câteva minute."
    : "Nu a mers: " + m;

  /* ---------- meniul contului + setări (GDPR) ---------- */
  function menu() {
    if ($("#acct-menu")) return close();
    const m = document.createElement("div");
    m.id = "acct-menu"; m.className = "acct-menu";
    const meta = user.user_metadata || {};
    m.innerHTML = `<div class="acct-who"><b>${esc(meta.name || "Contul meu")}</b>${esc(user.email)}</div>
      <button data-a="favs">⭐ Rutele mele favorite <span class="acct-soon">curând</span></button>
      <button data-a="alerts">🔔 Alerte de preț <span class="acct-soon">curând</span></button>
      <button data-a="name">✏️ Schimbă numele</button>
      <button data-a="pass">🔑 Schimbă parola</button>
      <button data-a="news">📧 Oferte pe email: <b>${meta.news ? "da" : "nu"}</b></button>
      <button data-a="export">⬇️ Descarcă datele mele</button>
      <button data-a="delete" class="acct-red">🗑️ Șterge contul definitiv</button>
      <button data-a="out">↪ Ieși din cont</button>`;
    const r = $("#acct-btn").getBoundingClientRect();
    m.style.top = (r.bottom + scrollY + 6) + "px";
    m.style.right = Math.max(8, innerWidth - r.right) + "px";
    document.body.appendChild(m);
    m.onclick = e => { e.stopPropagation(); const b = e.target.closest("[data-a]"); if (b) act(b.dataset.a); };
  }
  async function act(a) {
    const c = await client(); if (!c) return;
    const meta = user.user_metadata || {};
    if (a === "favs" || a === "alerts") return;
    close();
    if (a === "out") return c.auth.signOut();
    if (a === "name") { const n = prompt("Numele tău:", meta.name || ""); if (n != null) await c.auth.updateUser({ data: { name: n.trim() } }); }
    if (a === "pass") { const p = prompt("Parola nouă (minim 8 caractere):"); if (p) { const r = await c.auth.updateUser({ password: p }); alert(r.error ? ro(r.error.message) : "Parola a fost schimbată."); } }
    if (a === "news") await c.auth.updateUser({ data: { news: !meta.news } });
    if (a === "export") {
      const prefs = {}; ["theme", "favs1", "paxv2", "tab", "sort", "escMode", "exact2"].forEach(k => prefs[k] = ls.get(k));
      const data = { email: user.email, creat: user.created_at, ultima_logare: user.last_sign_in_at, profil: meta, preferinte_din_browser: prefs };
      const u = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      Object.assign(document.createElement("a"), { href: u, download: "flycenterhub-datele-mele.json" }).click();
      setTimeout(() => URL.revokeObjectURL(u), 1000);
    }
    if (a === "delete" && confirm("Ștergi definitiv contul și toate datele lui? Nu se poate anula.")) {
      const r = await c.rpc("delete_my_account");
      if (r.error) return alert("Nu am putut șterge contul acum. Scrie-ne din secțiunea Contact și îl ștergem noi.");
      await c.auth.signOut(); alert("Contul a fost șters.");
    }
  }
  document.addEventListener("click", e => { if (!e.target.closest("#acct-menu, #acct-btn")) $("#acct-menu")?.remove(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") close(); });

  /* ---------- mesajul despre cookie-uri ---------- */
  function cookies() {
    if (ls.get("cookie-ok")) return;
    const d = document.createElement("div");
    d.className = "ck-bar"; d.setAttribute("role", "region"); d.setAttribute("aria-label", "Cookie-uri");
    d.innerHTML = `<span>🍪 Nu folosim cookie-uri de urmărire. Păstrăm doar preferințele tale în browser. <a href="#">Detalii</a></span><button class="btn">Am înțeles</button>`;
    $("a", d).onclick = e => { e.preventDefault(); info("cookies"); };
    $("button", d).onclick = () => { ls.set("cookie-ok", "1"); d.remove(); };
    document.body.appendChild(d);
  }

  async function init() {
    button(); cookies();
    const c = await client(); if (!c) return;
    c.auth.onAuthStateChange((ev, s) => {
      user = s?.user || null; button();
      if (ev === "PASSWORD_RECOVERY") setTimeout(() => act("pass"), 300);
    });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
})();
