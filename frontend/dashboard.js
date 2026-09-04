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

/* ---------- Toast notifications (replaces alert()) ---------- */
function toast(msg, type = "ok") {
  let wrap = document.getElementById("toast-wrap");
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.id = "toast-wrap";
    wrap.style.cssText = "position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:10px;pointer-events:none";
    document.body.appendChild(wrap);
  }
  const t = document.createElement("div");
  const colors = { ok: "var(--ok)", err: "var(--danger)", info: "var(--accent)" };
  t.style.cssText = `background:#fff;border:1px solid var(--line);border-left:4px solid ${colors[type]||colors.ok};border-radius:8px;padding:12px 18px;font-size:14px;font-weight:500;color:var(--ink-700);box-shadow:0 8px 30px rgba(0,0,0,0.12);opacity:0;transform:translateY(8px);transition:all .25s ease;pointer-events:auto;max-width:320px`;
  t.textContent = msg;
  wrap.appendChild(t);
  requestAnimationFrame(() => { t.style.opacity = "1"; t.style.transform = "none"; });
  setTimeout(() => {
    t.style.opacity = "0"; t.style.transform = "translateY(8px)";
    setTimeout(() => t.remove(), 300);
  }, 3500);
}

/* ---------- Audit event data renderer — human-readable, not JSON ---------- */
const STAGE_META = {
  CLASSIFICATION: { icon: "◈", color: "#305eff", label: "Classification" },
  EVIDENCE_GATHERING: { icon: "⌁", color: "#7c3aed", label: "Evidence Gathering" },
  EXECUTION: { icon: "⚡", color: "#7c3aed", label: "Executor" },
  EVALUATION: { icon: "▤", color: "#0891b2", label: "Evaluation" },
  COMPILATION: { icon: "📄", color: "#059669", label: "Compilation" },
  COMPILE: { icon: "📄", color: "#059669", label: "Compilation" },
  SUBMITTED: { icon: "✓", color: "#16a34a", label: "Submitted" },
  HALTED_ACCEPT: { icon: "⚑", color: "#d97706", label: "Halted – Accept" },
  HALTED_REVIEW: { icon: "⚠", color: "#dc2626", label: "Halted – Review" },
  SUBMIT_BLOCKED_HIGH_VALUE: { icon: "⛔", color: "#dc2626", label: "Submit Blocked" },
  MERCHANT_REVIEW: { icon: "👤", color: "#0284c7", label: "Merchant Action" },
};

function renderAuditEventData(stage, data) {
  if (!data || typeof data !== "object") return "";
  const rows = [];

  if (stage === "CLASSIFICATION") {
    if (data.reason_code) rows.push(["Reason code", `<code class="ev-code">${data.reason_code}</code>`]);
    if (data.dispute_class) rows.push(["Dispute class", `<span class="ev-pill ev-class">${data.dispute_class}</span>`]);
    if (data.description) rows.push(["Description", data.description]);
    if (data.source) rows.push(["Method", `<span class="ev-pill ev-method">${data.source === "embedding" ? "TF-IDF embedding" : data.source}</span>`]);
    if (data.executors) rows.push(["Executors", data.executors.map(e => `<span class="ev-pill ev-exec">${e}</span>`).join(" ")]);
    if (data.base_confidence != null) rows.push(["Base confidence", `<span class="ev-conf">${(data.base_confidence * 100).toFixed(0)}%</span>`]);
  } else if (stage === "EVIDENCE_GATHERING" || stage === "EXECUTION") {
    if (data.executor) rows.push(["Executor", `<span class="ev-pill ev-exec">${data.executor}</span>`]);
    if (data.source_api) rows.push(["Source API", `<code class="ev-code">${data.source_api}</code>`]);
    if (data.strength) rows.push(["Strength", `<span class="ev-pill ev-strength-${(data.strength||"").toLowerCase()}">${data.strength}</span>`]);
    if (data.status) rows.push(["Status", data.status === "OK" ? `<span class="ev-pill ev-ok">✓ OK</span>` : `<span class="ev-pill ev-err">${data.status}</span>`]);
  } else if (stage === "EVALUATION") {
    if (data.model) rows.push(["Model", `<code class="ev-code">${data.model}</code>`]);
    if (data.fight_confidence != null) {
      const pct = Math.round(data.fight_confidence * 100);
      const col = pct >= 70 ? "var(--ok)" : pct >= 50 ? "var(--warn)" : "var(--danger)";
      rows.push(["Confidence", `<div class="ev-conf-bar"><div class="ev-conf-fill" style="width:${pct}%;background:${col}"></div><span>${pct}%</span></div>`]);
    }
    if (data.decision) rows.push(["Decision", `<span class="ev-pill ev-decision-${(data.decision||"").toLowerCase()}">${data.decision}</span>`]);
    if (data.stopping_rule) rows.push(["Stopping rule", `<span class="ev-pill ev-err">${data.stopping_rule}</span>`]);
    if (data.reasoning) rows.push(["Reasoning", `<em class="ev-reasoning">${data.reasoning}</em>`]);
  } else if (stage === "COMPILATION" || stage === "COMPILE") {
    if (data.skipped) {
      rows.push(["Status", `<span class="ev-pill ev-warn">Skipped</span>`]);
      if (data.reason) rows.push(["Reason", data.reason]);
    } else {
      rows.push(["Status", `<span class="ev-pill ev-ok">✓ Generated</span>`]);
      if (data.pdf_path) rows.push(["PDF", `<code class="ev-code">${data.pdf_path.split("/").pop()}</code>`]);
      if (data.word_count) rows.push(["Word count", data.word_count]);
      if (data.evidence_keys) rows.push(["Evidence used", data.evidence_keys.map(k => `<span class="ev-pill ev-exec">${k}</span>`).join(" ")]);
    }
  } else if (stage === "HALTED_ACCEPT" || stage === "HALTED_REVIEW") {
    if (data.reason) rows.push(["Reason", data.reason]);
    if (data.stopping_rule) rows.push(["Rule", `<span class="ev-pill ev-err">${data.stopping_rule}</span>`]);
    if (data.fight_confidence != null) rows.push(["Confidence", `${Math.round(data.fight_confidence * 100)}%`]);
  } else if (stage === "MERCHANT_REVIEW") {
    if (data.action) rows.push(["Action", `<span class="ev-pill ev-method">${data.action}</span>`]);
    if (data.note) rows.push(["Note", data.note]);
    if (data.reason_code) rows.push(["Reason code", `<code class="ev-code">${data.reason_code}</code>`]);
  } else {
    const skip = new Set(["timestamp", "agent", "stage"]);
    Object.entries(data).forEach(([k, v]) => {
      if (skip.has(k) || v == null) return;
      const val = typeof v === "object" ? JSON.stringify(v, null, 2) : String(v);
      rows.push([k.replace(/_/g, " "), val.length > 120 ? `<details><summary class="ev-summary">Show details</summary><pre class="ev-pre">${val}</pre></details>` : val]);
    });
  }

  if (!rows.length) return "";
  return `<dl class="ev-dl">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>`;
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
      left.innerHTML += `<span style="font-size:12.5px;color:var(--ink-500)">${d.reason_code}</span>`;
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

  /* Evidence cards with field-level detail */
  const evidenceHtml = data.evidence.length
    ? `<div class="evidence">${data.evidence.map(ev => {
        const rd = ev.raw_data || {};
        const fields = Object.entries(rd)
          .filter(([k, v]) => v != null && !["status"].includes(k))
          .map(([k, v]) => {
            const label = k.replace(/_/g, " ");
            let val = typeof v === "boolean"
              ? (v ? "<span class='ev-pill ev-ok'>✓ Yes</span>" : "<span class='ev-pill ev-err'>✗ No</span>")
              : String(v);
            return `<div class="ev-field"><span class="ev-field-k">${label}</span><span class="ev-field-v">${val}</span></div>`;
          }).join("");
        return `<div class="ev-item ${(ev.strength||'weak').toLowerCase()}">
         <div class="ev-top">
           <span class="ev-type">${ev.evidence_type}</span>
           <span class="ev-src">${ev.source_api || ""}</span>
           <span class="strength" style="color:${ev.strength==='STRONG'?'var(--ok)':ev.strength==='MODERATE'?'var(--warn)':'var(--ink-300)'}">${ev.strength || "—"}</span>
         </div>
         ${fields ? `<div class="ev-fields">${fields}</div>` : ""}
       </div>`;
      }).join("")}</div>`
    : `<div class="empty">No evidence collected.</div>`;

  /* Audit timeline — beautiful cards */
  const timelineHtml = chain.events.map(e => {
    const meta = STAGE_META[e.stage] || { icon: "◉", color: "var(--ink-500)", label: e.stage };
    const prettyData = renderAuditEventData(e.stage, e.event_data);
    const timeStr = e.created_at ? new Date(e.created_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
    const dateStr = e.created_at ? new Date(e.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "";
    return `<div class="tl-item ${e.chain_intact ? "" : "tampered"}">
       <div class="tl-head">
         <span class="tl-icon" style="background:${meta.color}20;color:${meta.color}">${meta.icon}</span>
         <span class="tl-stage">${meta.label}</span>
         <span class="tl-agent">${e.agent_name || ""}</span>
         <span class="tl-time" title="${dateStr}">${timeStr}</span>
       </div>
       ${prettyData ? `<div class="tl-data">${prettyData}</div>` : ""}
       <div class="tl-hash">
         <span class="hash-chip">prev: ${e.previous_hash || "GENESIS"}</span>
         <span class="hash-chip">hash: ${e.event_hash || "—"}</span>
       </div>
     </div>`;
  }).join("");

  /* Confidence bar */
  const conf = d.fight_confidence;
  const confPct = conf != null ? Math.round(conf * 100) : null;
  const confBar = confPct != null
    ? `<div class="conf-bar-wrap">
         <div class="conf-bar-track"><div class="conf-bar-fill" style="width:${confPct}%;background:${confPct>=70?"var(--ok)":confPct>=50?"var(--warn)":"var(--danger)"}"></div></div>
         <span class="conf-bar-label">${confPct}%</span>
       </div>` : "—";

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
          <dt>Dispute class</dt><dd>${d.dispute_class || "—"}</dd>
          <dt>Fight confidence</dt><dd>${confBar}</dd>
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
        ${d.rebuttal_pdf_path ? `<a class="btn primary" href="${API}/disputes/${d.db_id}/pdf" target="_blank">⬇ Download rebuttal PDF</a>` : ""}
        <button class="btn" id="accept-btn">Accept chargeback</button>
        <button class="btn" id="contest-btn">Contest (override)</button>
      </div>
    </div>`;

  document.getElementById("back-btn").onclick = () => showView("disputes");
  document.getElementById("accept-btn").onclick = async () => {
    try {
      await postJSON(`${API}/disputes/${d.db_id}/accept`, { note: "Merchant accepted from dashboard" });
      toast("Dispute marked as accepted.", "ok");
      setTimeout(() => openDetail(d.db_id), 800);
    } catch(e) { toast("Failed: " + e.message, "err"); }
  };
  document.getElementById("contest-btn").onclick = async () => {
    try {
      await postJSON(`${API}/disputes/${d.db_id}/contest`, { note: "Merchant override" });
      toast("Dispute marked as contested.", "ok");
      setTimeout(() => openDetail(d.db_id), 800);
    } catch(e) { toast("Failed: " + e.message, "err"); }
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
    left.innerHTML += `<span style="font-size:12.5px;color:var(--ink-500)">${c.reason_code || ""} · conf ${c.fight_confidence != null ? Math.round(c.fight_confidence*100)+"%" : "—"}</span>`;
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

/* ---------- bootstrap ---------- */
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
    location.href = "/login";
  }
}
boot();
