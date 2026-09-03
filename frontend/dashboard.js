/* AutoDefend — dashboard JS
   Vanilla, no framework. Converses with the FastAPI dashboard router at /api/*.
   Views: overview, disputes, false-positive, and an expandable detail drawer.
   The audit trail is rendered with live chain-integrity from the backend. */

const API = "/api";
const fmtINR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

/* ---------- helpers ---------- */
function badgeFor(label) {
  const map = {
    AUTO_DEFENDED: ["b-a", "AUTO-DEFENDED"],
    WON: ["b-a", "WON"],
    LOST: ["b-r", "LOST"],
    ACCEPTED: ["b-n", "ACCEPTED"],
    PENDING_REVIEW: ["b-p", "PENDING REVIEW"],
    CONTEST: ["b-i", "CONTEST"],
    INGESTED: ["b-p", "PROCESSING"],
    SUBMITTED: ["b-a", "SUBMITTED"],
  };
  const [cls, txt] = map[label] || ["b-n", label || "—"];
  return `<span class="badge ${cls}"><span class="dot"></span>${txt}</span>`;
}

function amountRs(paise) {
  return fmtINR.format(Math.round((paise || 0) / 100));
}

function shortId(id) {
  if (!id) return "—";
  return id.length > 22 ? id.slice(0, 10) + "…" + id.slice(-6) : id;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

async function getJSON(url) {
  const r = await fetch(url);
  if (r.status === 401) { window.location.reload(); throw new Error("unauthorized"); }
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (r.status === 401) { window.location.reload(); throw new Error("unauthorized"); }
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

/* ---------- nav ---------- */
function showView(name) {
  document.querySelectorAll("section[id^='view-']").forEach(s => s.classList.add("hidden"));
  const sec = document.getElementById("view-" + name);
  if (sec) sec.classList.remove("hidden");
  document.querySelectorAll("#topnav a").forEach(a =>
    a.classList.toggle("active", a.dataset.view === name));
  window.scrollTo({ top: 0 });
}

/* ---------- overview ---------- */
async function renderOverview() {
  const [sum, disputes] = await Promise.all([
    getJSON(`${API}/metrics/summary`),
    getJSON(`${API}/disputes?limit=200`),
  ]);

  const stats = document.getElementById("summary-stats");
  stats.innerHTML = "";
  const cards = [
    ["Win rate", `${sum.win_rate_pct}%`, `${sum.won} won / ${sum.contested} contested`],
    ["Revenue recovered", amountRs(sum.revenue_recovered_rs * 100), "from won disputes"],
    ["Auto-defended", `${sum.auto_defended}`, `~${sum.time_saved_hours_est}h manual effort saved (est.)`],
    ["Pending review", `${sum.pending_review}`, "need a human decision"],
  ];
  cards.forEach(([label, value, note]) => {
    const c = el("div", "stat");
    c.appendChild(el("div", "label", label));
    c.appendChild(el("div", "value", value));
    c.appendChild(el("div", "note", note));
    stats.appendChild(c);
  });

  const recent = document.getElementById("recent-rows");
  recent.innerHTML = "";
  disputes.disputes.slice(0, 6).forEach(d => {
    const tr = document.createElement("tr");
    tr.onclick = () => openDetail(d.db_id);
    tr.innerHTML = `
      <td class="mono" title="${d.dispute_id}">${shortId(d.dispute_id)}</td>
      <td>${d.reason_code || "—"}</td>
      <td class="amount">${amountRs(d.amount_paise)}</td>
      <td>${d.system_decision || "—"}</td>
      <td>${badgeFor(d.status_badge)}</td>`;
    recent.appendChild(tr);
  });

  const queue = document.getElementById("review-queue");
  queue.innerHTML = "";
  const pending = disputes.disputes.filter(d => d.fsm_state === "HUMAN_REVIEW");
  if (!pending.length) {
    queue.appendChild(el("div", "empty", "Nothing needs a human right now."));
  } else {
    pending.forEach(d => {
      const row = el("div", "fp-row");
      row.style.cursor = "pointer";
      row.onclick = () => openDetail(d.db_id);
      const left = el("div");
      left.appendChild(el("div", "mono", shortId(d.dispute_id)));
      left.appendChild(el("div", "", `<span style="font-size:12.5px;color:var(--ink-500)">${d.reason_code}</span>`));
      const right = el("div", "amount", amountRs(d.amount_paise));
      row.appendChild(left);
      row.appendChild(right);
      queue.appendChild(row);
    });
  }
}

/* ---------- disputes list ---------- */
async function renderDisputes() {
  const data = await getJSON(`${API}/disputes?limit=200`);
  document.getElementById("dispute-count").textContent = `${data.count} disputes`;

  const tbody = document.getElementById("dispute-rows");
  tbody.innerHTML = "";
  data.disputes.forEach(d => {
    const tr = document.createElement("tr");
    tr.onclick = () => openDetail(d.db_id);
    const conf = d.fight_confidence != null ? Math.round(d.fight_confidence * 100) + "%" : "—";
    tr.innerHTML = `
      <td class="mono" title="${d.dispute_id}">${shortId(d.dispute_id)}</td>
      <td>${d.reason_code || "—"}</td>
      <td class="amount">${amountRs(d.amount_paise)}</td>
      <td>${conf}</td>
      <td>${d.system_decision || "—"}</td>
      <td>${badgeFor(d.status_badge)}</td>`;
    tbody.appendChild(tr);
  });
}

/* ---------- detail drawer ---------- */
async function openDetail(dbId) {
  const data = await getJSON(`${API}/disputes/${dbId}`);
  const d = data.dispute;
  const sec = document.getElementById("view-detail");
  const chain = data.audit_trail;

  const chainBanner = chain.chain_valid
    ? `<div class="chain-banner ok">✓ Audit chain intact — ${chain.total_events} hash-linked events verified</div>`
    : `<div class="chain-banner bad">✕ Audit chain tamper detected at event ${chain.first_tampered_event}</div>`;

  const evidenceHtml = data.evidence.length ? `<div class="evidence">${data.evidence.map(ev =>
    `<div class="ev-item ${(ev.strength||'weak').toLowerCase()}">
       <div class="ev-top">
         <span class="ev-type">${ev.evidence_type}</span>
         <span class="ev-src">${ev.source_api || ""}</span>
         <span class="strength">${ev.strength || "—"}</span>
       </div>
     </div>`).join("")}</div>`
    : `<div class="empty">No evidence collected.</div>`;

  const timelineHtml = chain.events.map(e =>
    `<div class="tl-item ${e.chain_intact ? "" : "tampered"}">
       <div class="tl-head">
         <span class="tl-stage">${e.stage || "—"}</span>
         <span class="tl-agent">${e.agent_name || ""}</span>
         <span class="tl-time">${e.created_at ? new Date(e.created_at).toLocaleString() : ""}</span>
       </div>
       <div class="tl-data">${JSON.stringify(e.event_data || {})}</div>
     </div>`).join("");

  sec.innerHTML = `
    <div class="page-head">
      <button class="btn ghost" id="back-btn">← Back</button>
      <h1>${shortId(d.dispute_id)}</h1>
      <span class="sub">${d.reason_code || ""}</span>
    </div>

    <div class="card">
      <div class="card-head"><h2>Dispute summary</h2>${badgeFor(d.status_badge)}</div>
      <div class="drawer">
        <div class="kv" style="margin-top:16px">
          <dt>Amount</dt><dd>${amountRs(d.amount_paise)}</dd>
          <dt>Phase</dt><dd>${d.phase}</dd>
          <dt>Class</dt><dd>${d.dispute_class || "—"}</dd>
          <dt>Fight confidence</dt><dd>${d.fight_confidence != null ? (Math.round(d.fight_confidence*100)+"%") : "—"}</dd>
          <dt>Initial confidence</dt><dd>${d.initial_confidence != null ? (Math.round(d.initial_confidence*100)+"%") : "—"}</dd>
          <dt>Decision</dt><dd>${d.system_decision || "—"}</dd>
          <dt>Outcome</dt><dd>${d.actual_outcome || "Pending"}</dd>
        </div>
      </div>
    </div>

    <div class="grid-2" style="margin-top:20px">
      <div class="card">
        <div class="card-head"><h2>Evidence collected</h2></div>
        <div class="drawer">${evidenceHtml}</div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Verifiable audit trail</h2></div>
        <div class="drawer">
          ${chainBanner}
          <div class="timeline">${timelineHtml}</div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:20px">
      <div class="card-head"><h2>Actions</h2></div>
      <div class="drawer actions">
        ${d.rebuttal_pdf_path ? `<a class="btn primary" href="${API}/disputes/${d.db_id}/pdf" target="_blank">Download rebuttal PDF</a>` : ""}
        <button class="btn" id="accept-btn">Accept chargeback</button>
        <button class="btn" id="contest-btn">Contest (override)</button>
      </div>
    </div>`;

  document.getElementById("back-btn").onclick = () => showView("disputes");
  document.getElementById("accept-btn").onclick = async () => {
    await postJSON(`${API}/disputes/${d.db_id}/accept`, { note: "Merchant accepted from dashboard" });
    alert("Dispute marked as accepted.");
    openDetail(d.db_id);
  };
  document.getElementById("contest-btn").onclick = async () => {
    await postJSON(`${API}/disputes/${d.db_id}/contest`, { note: "Merchant override" });
    alert("Dispute marked as contested.");
    openDetail(d.db_id);
  };

  showView("detail");
}

/* ---------- false positive ---------- */
async function renderFP() {
  const data = await getJSON(`${API}/metrics/false-positive-cost`);
  document.getElementById("fp-cost").textContent = amountRs(data.false_positive_cost_rs * 100);
  document.getElementById("fp-count").textContent = data.false_positive_count;
  document.getElementById("fp-avg").textContent = amountRs(data.avg_fp_cost_rs * 100);

  const list = document.getElementById("fp-list");
  list.innerHTML = data.cases.length ? "" : `<div class="empty">No false positives in this window — clean over-filing record.</div>`;
  data.cases.forEach(c => {
    const row = el("div", "fp-row");
    const left = el("div");
    left.appendChild(el("div", "mono", c.id));
    left.appendChild(el("div", "", `<span style="font-size:12.5px;color:var(--ink-500)">${c.reason_code || ""} · conf ${c.fight_confidence != null ? Math.round(c.fight_confidence*100)+"%" : "—"}</span>`));
    const right = el("div", "amount", amountRs(c.amount_rs * 100));
    row.appendChild(left);
    row.appendChild(right);
    list.appendChild(row);
  });
}

/* ---------- routing ---------- */
document.getElementById("topnav").addEventListener("click", e => {
  const a = e.target.closest("a");
  if (!a) return;
  e.preventDefault();
  const v = a.dataset.view;
  showView(v);
  if (v === "overview") renderOverview();
  if (v === "disputes") renderDisputes();
  if (v === "false-positive") renderFP();
});
document.querySelectorAll("[data-to]").forEach(a => {
  a.addEventListener("click", e => { e.preventDefault(); showView(a.dataset.to); renderDisputes(); });
});

/* ---------- bootstrap (standalone at /app) ---------- */
document.getElementById("logout-btn").addEventListener("click", async () => {
  await postJSON("/auth/logout", {});
  location.href = "/login";
});

async function boot() {
  try {
    const me = await (await fetch("/auth/me", { credentials: "same-origin" })).json();
    document.getElementById("me-name").textContent = me.full_name || me.email;
    document.getElementById("me-merchant").textContent = me.merchant_id;
    showView("overview");
    renderOverview().catch(err => console.error("overview:", err));
  } catch (_) {
    // Not authenticated → back to the login page.
    location.href = "/login";
  }
}
boot();
