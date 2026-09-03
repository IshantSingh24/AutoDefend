/* AutoDefend — live demo controller
   Vanilla JS. Streams the pipeline over Server-Sent Events from
   /api/demo/simulate. Renders it as a neon "rail": a vertical line with a
   glowing blue ball that travels down the rail, seating itself on each step
   while that step executes, then settles to "done" and moves on. */

const $ = id => document.getElementById(id);

/* ---------- auth gate (directs to /login page) ---------- */
async function initAuth(){
  try {
    const r = await fetch("/auth/me", { credentials: "same-origin" });
    if(r.ok){
      const me = await r.json();
      $("me-name").textContent = me.full_name || me.email;
      $("me-merchant").textContent = me.merchant_id;
      $("demo-app").classList.remove("hidden");
      return;
    }
  } catch(_){}
  location.href = "/login";
}

/* ---------- pipeline rail ---------- */
const BASE_STAGES = [["ingest","Ingestion"],["classify","Classification"],["evaluate","Evaluation"],["compile","Compile"],["done","Complete"]];
const stageLabel = {
  ingest:"Ingestion", classify:"Classification", executor:"Evidence",
  evaluate:"Evaluation", compile:"Compile", done:"Complete",
};

const rails = sel => document.getElementById("railSteps").querySelectorAll(sel);
let ballY = 0;   // current ball position, updated by travelTo

function resetPipeline(){
  // remove only step nodes — keep the ball & line (children of #railSteps)
  document.querySelectorAll("#railSteps > .dm-node").forEach(n => n.remove());
  BASE_STAGES.forEach(([_, label]) => $("railSteps").appendChild(makeNode(label)));
  ballY = 0;
  $("railBall").classList.remove("ok");
  placeBall(8, 0);       // x is trivial; travelTo repositions the x anyway
  growLine(10);
  $("pipeline").style.display = "block";
  $("result-card").innerHTML = "";
  $("run-status").textContent = "Standing by…";
}

function makeNode(label){
  const n = document.createElement("div");
  n.className = "dm-node";
  n.innerHTML = `
    <span class="dm-dot"></span>
    <div class="dm-body">
      <span class="dm-label">${label}</span>
      <div class="dm-detail"></div>
    </div>`;
  return n;
}

/* Insert a sub-node (e.g. "Evidence · logistics") before "Evaluation". */
function insertSubNode(subLabel){
  const node = makeNode(stageLabel.executor + " · " + subLabel);
  node.classList.add("sub");
  node.dataset.sub = subLabel;
  const list = $("railSteps");
  let ref = null;
  for(const n of rails(".dm-node")){
    if(!n.dataset.sub && n.querySelector(".dm-label").textContent === "Evaluation"){ ref = n; break; }
  }
  if(ref) list.insertBefore(node, ref);
  else list.appendChild(node);
  return node;
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

/* Rail coordinates — simple & reliable.
   .dm-node is a direct child of the relative-positioned .dm-steps, so
   node.offsetTop is already rail-relative. The ball/line sit next to the
   dots; we align them to the vertical centre of the target node. */
const BALL = 16, LINE = 2, DOT_X = 7;   // DOT_X = edge of node dot area
function nodeCenter(node){
  const rail = node.offsetParent;                 // .dm-steps
  return { y: node.offsetTop + node.offsetHeight/2,
           x: (node.querySelector(".dm-dot").offsetLeft + node.querySelector(".dm-dot").offsetWidth/2) };
}
function placeBall(x, y){
  $("railBall").style.left = (x - BALL/2) + "px";
  $("railBall").style.top  = (y - BALL/2) + "px";
}
function placeLine(x){
  $("railLine").style.left = (x - LINE/2) + "px";
}
function growLine(y){
  $("railLine").style.height = (y + BALL/2) + "px";
}

/* Animate the ball down the rail to a node — pure rAF tween. */
function travelTo(node, dur = 600){
  return new Promise(res => {
    if(!node){ res(); return; }
    const target = nodeCenter(node);
    placeLine(target.x);
    const start = ballY;
    const startT = performance.now();
    const ease = t => t < 0.5 ? 2*t*t : -1 + (4-2*t)*t;
    const frame = now => {
      const t = Math.min(1, (now - startT)/dur);
      const y = start + (target.y - start) * ease(t);
      placeBall(target.x, y);
      growLine(y);
      if(t < 1){ requestAnimationFrame(frame); }
      else { ballY = target.y; growLine(target.y); res(); }
    };
    requestAnimationFrame(frame);
  });
}

function stageState(node, state){
  node.classList.remove("running","ok","error");
  node.classList.add(state);
}

/* Mark a step: classify/ingest/evaluate/compile/done OR a dynamic sub-node. */
async function markStage(stage, state, text, detail, dur){
  // locate target node
  let target = null;
  if(stage === "executor"){
    const subLabel = (text && text.match(/\b(logistics|security|crm)\b/) || [,"executor"])[1];
    for(const n of rails(".dm-node")){ if(n.dataset.sub === subLabel){ target = n; break; } }
    if(!target) target = insertSubNode(subLabel);
  } else {
    // find the base node by its label (robust to inserted sub-nodes)
    const want = stageLabel[stage];
    for(const n of rails(".dm-node")){
      if(!n.dataset.sub && n.querySelector(".dm-label").textContent === want){ target = n; break; }
    }
  }

  if(!target) return;
  const ball = $("railBall");
  if(state === "running"){
    ball.classList.remove("ok");            // travelling / executing → blue
    await travelTo(target, dur || 700);
    stageState(target, "running");
    const d = target.querySelector(".dm-detail");
    d.textContent = (text || "") + (detail ? " — " + detail : "");
  } else if(state === "ok"){
    ball.classList.add("ok");               // seated & done → green
    stageState(target, "ok");
    const d = target.querySelector(".dm-detail");
    d.textContent = (text || "") + (detail ? " — " + detail : "");
  } else if(state === "error"){
    stageState(target, "error");
  }
}

/* ---------- run ---------- */
let elapsedStart = 0;
let elapsedTimer = null;
function startElapsed(){
  elapsedStart = performance.now();
  $("elapsed").textContent = "0s";
  if(elapsedTimer) clearInterval(elapsedTimer);
  elapsedTimer = setInterval(()=>{
    $("elapsed").textContent = Math.round((performance.now()-elapsedStart)/1000)+"s";
  }, 250);
}
function stopElapsed(){
  if(elapsedTimer){ clearInterval(elapsedTimer); elapsedTimer = null; }
  $("elapsed").textContent = Math.round((performance.now()-elapsedStart)/1000)+"s";
}
async function runPipeline(){
  resetPipeline();
  startElapsed();
  $("run-btn").disabled = true;
  const reason = $("reason").value;
  const amountRs = Math.max(10, parseInt($("amount").value||"1250",10));
  const amount = amountRs * 100; // paise

  try {
    const res = await fetch("/api/demo/simulate", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ reason_code: reason, amount }),
    });
    if(!res.ok || !res.body){
      $("run-status").textContent = `Failed (${res.status})`;
      $("run-btn").disabled = false;
      return;
    }

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let done = false;
    while(!done){
      const { value, done: d } = await reader.read();
      done = d;
      buf += dec.decode(value || new Uint8Array(), {stream: !done});
      let idx;
      while((idx = buf.indexOf("\n\n")) >= 0){
        const chunk = buf.slice(0, idx); buf = buf.slice(idx+2);
        if(!chunk.startsWith("data: ")) continue;
        let ev; try { ev = JSON.parse(chunk.slice(6)); } catch(_){ continue; }
        await handleEvent(ev);
      }
    }
    $("run-status").textContent = "Complete";
  } catch(e){
    $("run-status").textContent = "Error: "+e.message;
  } finally {
    $("run-btn").disabled = false;
  }
}

async function handleEvent(ev){
  switch(ev.stage){
    case "ingest":
      await markStage("ingest","running", ev.text);
      await sleep(260);
      await markStage("ingest","ok", ev.text);
      break;
    case "classify":
      await markStage("classify","running", ev.text);
      await sleep(500);
      await markStage("classify","ok", ev.text, ev.detail);
      break;
    case "executor":
      const subLabel = (ev.text && ev.text.match(/\b(logistics|security|crm)\b/) || [,"executor"])[1];
      await markStage("executor","running", subLabel, ev.detail);
      await sleep(420);
      await markStage("executor","ok", subLabel, ev.detail);
      break;
    case "evaluate":
      await markStage("evaluate","running", ev.text);
      await sleep(550);
      await markStage("evaluate","ok", ev.text, ev.detail);
      break;
    case "compile":
      await markStage("compile","running", ev.text);
      await sleep(400);
      await markStage("compile","ok", ev.text);
      break;
    case "done":
      await markStage("done","ok", null, "Audit chain intact");
      await sleep(300);
      renderResult(ev.dispute);
      break;
    case "error":
      await markStage("evaluate","error", ev.text);
      $("run-status").textContent = "Pipeline failed";
      break;
  }
}

function renderResult(d){
  $("result-card").innerHTML = `
    <div class="card">
      <div class="card-head"><h2>Result — persistence verified</h2><span class="badge b-a">${d.decision}</span></div>
      <div class="drawer">
        <div class="kv" style="margin-top:16px">
          <dt>Dispute ID</dt><dd class="mono">${d.dispute_id}</dd>
          <dt>Reason code</dt><dd>${d.reason_code}</dd>
          <dt>Class</dt><dd>${d.class}</dd>
          <dt>Decision</dt><dd>${d.decision} (conf ${(d.confidence*100).toFixed(0)}%)</dd>
          <dt>Amount</dt><dd>₹${d.amount_rs.toLocaleString("en-IN", {maximumFractionDigits:0})}</dd>
        </div>
        <div style="margin-top:var(--space-5)">
          <a class="btn primary" href="/app">Open in dashboard →</a>
          <span class="note" style="margin-left:var(--space-3);color:var(--ink-300);font-size:12.5px">This dispute now appears in your real dashboard with a hash-chained audit trail</span>
        </div>
      </div>
    </div>`;
  stopElapsed();
}

/* ---------- wire up ---------- */
$("run-btn").addEventListener("click", runPipeline);
$("logout-btn").addEventListener("click", async ()=>{ await fetch("/auth/logout",{method:"POST",headers:{"Content-Type":"application/json"}}); location.href="/login"; });

initAuth();