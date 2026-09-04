/* AutoDefend — demo page controller (redesigned)
   Two-column live view: stage cards on left, streamed event log on right.
   SSE from /api/demo/simulate drives both. */

const $ = id => document.getElementById(id);
const fmtTime = () => new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/* ── Auth gate ── */
async function initAuth() {
  try {
    const r = await fetch("/auth/me", { credentials: "same-origin" });
    if (r.ok) {
      const me = await r.json();
      $("me-name").textContent = me.full_name || me.email;
      $("me-merchant").textContent = me.merchant_id;
      $("demo-app").classList.remove("hidden");
      return;
    }
  } catch (_) {}
  location.href = "/login";
}

/* ── Stage definitions ── */
const BASE_STAGES = [
  { key: "ingest",   icon: "⚡", name: "Ingestion",      sub: "Webhook → Dispute record created" },
  { key: "classify", icon: "◈", name: "Classification", sub: "TF-IDF cosine → dispute class" },
  // executor sub-nodes injected here
  { key: "evaluate", icon: "▤", name: "Evaluation",     sub: "LightGBM → fight_confidence" },
  { key: "compile",  icon: "📄", name: "Compilation",    sub: "Rebuttal PDF with evidence exhibits" },
  { key: "done",     icon: "✓", name: "Complete",       sub: "Audit chain sealed & persisted" },
];

const stageOrder = ["ingest", "classify", "evaluate", "compile", "done"];
let logEventCount = 0;
let elapsedTimer = null;
let elapsedStart = 0;

/* ── Stage card management ── */
function buildStageDom() {
  const list = $("stage-list");
  list.innerHTML = "";
  BASE_STAGES.forEach(s => {
    const card = makeStageCard(s.key, s.icon, s.name, s.sub, false);
    list.appendChild(card);
  });
}

function makeStageCard(key, icon, name, detail, isSub) {
  const card = document.createElement("div");
  card.className = "stage-card" + (isSub ? " sub" : "");
  card.dataset.key = key;
  card.innerHTML = `
    <div class="stage-icon">${icon}</div>
    <div class="stage-body">
      <div class="stage-name">${name}</div>
      <div class="stage-detail">${detail || ""}</div>
    </div>
    <div class="stage-badge"><span>—</span></div>`;
  return card;
}

function setStageState(key, state, badge, detail) {
  const card = $("stage-list").querySelector(`[data-key="${key}"]`);
  if (!card) return;
  card.classList.remove("running", "ok", "error");
  if (state) card.classList.add(state);
  if (badge != null) card.querySelector(".stage-badge span").textContent = badge;
  if (detail != null) card.querySelector(".stage-detail").textContent = detail;
}

function getOrInsertSubCard(subKey) {
  const list = $("stage-list");
  let card = list.querySelector(`[data-key="exec-${subKey}"]`);
  if (!card) {
    const icons = { logistics: "🚚", security: "🔐", crm: "👤" };
    card = makeStageCard("exec-" + subKey, icons[subKey] || "⌁", `Evidence · ${subKey}`, "", true);
    // Insert before evaluate
    const evalCard = list.querySelector('[data-key="evaluate"]');
    if (evalCard) list.insertBefore(card, evalCard);
    else list.appendChild(card);
  }
  return card;
}

function setSubState(subKey, state, badge, detail) {
  getOrInsertSubCard(subKey); // ensure exists
  const card = $("stage-list").querySelector(`[data-key="exec-${subKey}"]`);
  if (!card) return;
  card.classList.remove("running", "ok", "error");
  if (state) card.classList.add(state);
  if (badge != null) card.querySelector(".stage-badge span").textContent = badge;
  if (detail != null) card.querySelector(".stage-detail").textContent = detail;
}

/* ── Log stream ── */
function addLogEntry(stageKey, msg, kvPairs) {
  const body = $("log-body");
  const empty = body.querySelector(".log-empty");
  if (empty) empty.remove();

  logEventCount++;
  $("log-count").textContent = `${logEventCount} event${logEventCount !== 1 ? "s" : ""}`;

  const entry = document.createElement("div");
  entry.className = "log-entry";

  const kvsHtml = kvPairs
    ? kvPairs.map(([k, v, cls]) =>
        `<span class="kv-pair"><span class="kv-k">${k}</span><span class="kv-v ${cls || ""}">${v}</span></span>`
      ).join("")
    : "";

  entry.innerHTML = `
    <span class="log-time">${fmtTime()}</span>
    <span class="log-stage ${stageKey}">${stageKey.toUpperCase()}</span>
    <span class="log-msg">${msg}${kvsHtml}</span>`;
  body.appendChild(entry);
  body.scrollTop = body.scrollHeight;
}

/* ── Elapsed timer ── */
function startElapsed() {
  elapsedStart = performance.now();
  const badge = $("elapsed-badge");
  badge.style.display = "inline";
  badge.textContent = "0s";
  if (elapsedTimer) clearInterval(elapsedTimer);
  elapsedTimer = setInterval(() => {
    badge.textContent = Math.round((performance.now() - elapsedStart) / 1000) + "s";
  }, 250);
}
function stopElapsed() {
  if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
  $("elapsed-badge").textContent = Math.round((performance.now() - elapsedStart) / 1000) + "s";
}

/* ── Status dot ── */
function setDot(state) {
  const d = $("status-dot");
  d.classList.remove("active", "done", "error");
  if (state) d.classList.add(state);
}

/* ── Reset ── */
function resetUI() {
  buildStageDom();
  $("log-body").innerHTML = `<div class="log-empty">Events will appear here as each agent fires…</div>`;
  $("result-wrap").innerHTML = "";
  logEventCount = 0;
  $("log-count").textContent = "0 events";
  $("workspace").style.display = "grid";
}

/* ── SSE event handling ── */
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function handleEvent(ev) {
  switch (ev.stage) {
    case "ingest":
      addLogEntry("ingest", `Dispute <strong>${ev.text || "received"}</strong> — persisted to DB`);
      setStageState("ingest", "running", "RUNNING", "Persisting dispute to database…");
      await sleep(250);
      setStageState("ingest", "ok", "DONE", "Dispute record created, FSM started");
      break;

    case "classify": {
      addLogEntry("classify", `Classifying…`);
      setStageState("classify", "running", "RUNNING", "TF-IDF vectorize → cosine similarity…");
      await sleep(480);
      const cls = ev.detail || ev.text || "";
      addLogEntry("classify", `Class detected`, [
        ["class", cls.match(/\b(fraud|non_receipt|service|policy)\b/i)?.[1] || cls, "val-ok"],
        ["method", "TF-IDF embedding"],
      ]);
      setStageState("classify", "ok", "DONE", cls || "Classification complete");
      break;
    }

    case "executor": {
      const m = (ev.text || "").match(/\b(logistics|security|crm)\b/i);
      const sub = m ? m[1].toLowerCase() : "executor";
      setSubState(sub, "running", "RUNNING", "Fetching evidence…");
      await sleep(380);
      const detail = ev.detail || "Evidence collected";
      const strength = detail.match(/STRONG|MODERATE|WEAK|TIMEOUT/i)?.[0] || "";
      const cls = strength === "STRONG" ? "val-ok" : strength === "TIMEOUT" ? "val-err" : "val-warn";
      addLogEntry("executor", `<strong>${sub}</strong> executor`, [
        ["strength", strength || "OK", cls],
        ["src", sub === "logistics" ? "delhivery" : sub === "security" ? "razorpay_payment" : "shopify"],
      ]);
      setSubState(sub, "ok", strength || "DONE", detail);
      break;
    }

    case "evaluate": {
      setStageState("evaluate", "running", "RUNNING", "LightGBM inference…");
      addLogEntry("evaluate", "Evaluating with LightGBM…");
      await sleep(500);
      const detail = ev.detail || ev.text || "";
      const confM = detail.match(/[\d.]+/);
      const conf = confM ? parseFloat(confM[0]) : null;
      const decM = detail.match(/\b(CONTEST|RECOMMEND_ACCEPT|HUMAN_REVIEW)\b/i);
      const dec = decM ? decM[1] : null;
      const kvs = [];
      if (conf != null) kvs.push(["confidence", (conf * 100).toFixed(0) + "%", conf >= 0.7 ? "val-ok" : "val-warn"]);
      if (dec) kvs.push(["decision", dec, dec === "CONTEST" ? "val-ok" : dec === "RECOMMEND_ACCEPT" ? "val-warn" : "val-err"]);
      addLogEntry("evaluate", "Decision reached", kvs);
      setStageState("evaluate", "ok", dec || "DONE", detail);
      break;
    }

    case "compile": {
      setStageState("compile", "running", "RUNNING", "Building rebuttal PDF…");
      addLogEntry("compile", "Compiling evidence exhibits…");
      await sleep(400);
      addLogEntry("compile", "Rebuttal PDF generated", [["exhibits", "A · B · C · D", "val-ok"]]);
      setStageState("compile", "ok", "DONE", "Rebuttal PDF ready");
      break;
    }

    case "done":
      setStageState("done", "ok", "DONE", "Audit chain sealed");
      addLogEntry("done", "Pipeline complete — dispute persisted with hash-chained audit trail", [["chain", "INTACT ✓", "val-ok"]]);
      setDot("done");
      stopElapsed();
      await sleep(300);
      renderResult(ev.dispute);
      break;

    case "error":
      setStageState("evaluate", "error", "ERROR");
      addLogEntry("error", ev.text || "Pipeline error — routed to human review", [["status", "ERROR", "val-err"]]);
      setDot("error");
      $("run-status").textContent = "Error — routed to human review";
      stopElapsed();
      break;
  }
}

/* ── Render result card ── */
function renderResult(d) {
  if (!d) return;
  const dec = (d.decision || "").toUpperCase();
  const decClass = dec === "CONTEST" ? "contest" : dec === "RECOMMEND_ACCEPT" ? "recommend_accept" : "human_review";
  const decLabel = dec === "CONTEST" ? "✓ REBUTTAL FILED" : dec === "RECOMMEND_ACCEPT" ? "⚑ ACCEPT RECOMMENDED" : "⚠ HUMAN REVIEW";
  const confPct = Math.round((d.confidence || 0) * 100);
  const confColor = confPct >= 70 ? "#34d399" : confPct >= 50 ? "#fbbf24" : "#f87171";

  const wrap = $("result-wrap");
  wrap.innerHTML = `
    <div class="result-card decision-${decClass}">
      <div>
        <div class="result-title">Pipeline result</div>
        <div class="result-decision ${decClass}">${decLabel}</div>
        <dl class="result-kv">
          <dt>Dispute ID</dt><dd style="font-family:'JetBrains Mono',monospace;font-size:12px">${d.dispute_id || "—"}</dd>
          <dt>Reason code</dt><dd>${d.reason_code || "—"}</dd>
          <dt>Dispute class</dt><dd>${d.class || "—"}</dd>
          <dt>Amount</dt><dd>₹${(d.amount_rs || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</dd>
        </dl>
        <div class="conf-meter">
          <div class="conf-track"><div class="conf-fill" id="conf-fill" style="width:0%;background:${confColor}"></div></div>
          <span class="conf-pct" style="color:${confColor}">${confPct}%</span>
        </div>
        <div style="font-size:12px;color:#4b5e7a;margin-top:6px">Fight confidence</div>
      </div>
      <div class="result-actions">
        <a class="btn-dashboard" href="/app">Open in dashboard →</a>
        <div class="btn-again" id="run-again">↺ Run again</div>
        <div class="keyboard-hint">or press <kbd>Space</kbd></div>
      </div>
    </div>`;

  // Animate confidence bar
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      $("conf-fill").style.width = confPct + "%";
    });
  });

  $("run-again").onclick = () => runPipeline();
  $("run-btn").disabled = false;
}

/* ── Main pipeline runner ── */
async function runPipeline() {
  resetUI();
  setDot("active");
  $("run-btn").disabled = true;
  $("run-status").textContent = "Pipeline running…";
  startElapsed();

  const reason = $("reason").value;
  const amountPaise = Math.max(10, parseInt($("amount").value || "1250", 10)) * 100;

  try {
    const res = await fetch("/api/demo/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason_code: reason, amount: amountPaise }),
    });

    if (!res.ok || !res.body) {
      $("run-status").textContent = `Failed (${res.status})`;
      setDot("error");
      $("run-btn").disabled = false;
      stopElapsed();
      return;
    }

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let done = false;

    while (!done) {
      const { value, done: d } = await reader.read();
      done = d;
      buf += dec.decode(value || new Uint8Array(), { stream: !done });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
        if (!chunk.startsWith("data: ")) continue;
        let ev; try { ev = JSON.parse(chunk.slice(6)); } catch (_) { continue; }
        await handleEvent(ev);
      }
    }

    if ($("run-status").textContent === "Pipeline running…") {
      $("run-status").textContent = "Complete";
    }
  } catch (e) {
    $("run-status").textContent = "Error: " + e.message;
    setDot("error");
    stopElapsed();
  } finally {
    $("run-btn").disabled = false;
  }
}

/* ── Wire events ── */
$("run-btn").addEventListener("click", runPipeline);
$("logout-btn").addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST", headers: { "Content-Type": "application/json" } });
  location.href = "/login";
});

// Keyboard shortcut: Space = run
document.addEventListener("keydown", e => {
  if (e.code === "Space" && e.target === document.body) {
    e.preventDefault();
    if (!$("run-btn").disabled) runPipeline();
  }
});

initAuth();