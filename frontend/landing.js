/* AutoDefend — landing page behaviour.
   Smooth scroll (anchor nav), IntersectionObserver reveal, animated count-up
   metrics, and a looping hero "pipeline ball" preview that mirrors the stage
   rail before the real demo takes over. */

"use strict";

/* ---------- Smooth scroll for in-page anchor nav ---------- */
const smoothScroll = (targetY, dur = 700) => {
  const start = window.pageYOffset;
  const dist = targetY - start;
  const startT = performance.now();
  const ease = t => t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
  const frame = now => {
    const t = Math.min(1, (now - startT) / dur);
    window.scrollTo(0, start + dist * ease(t));
    if (t < 1) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
};

document.querySelectorAll('a[href^="#"]').forEach(link => {
  link.addEventListener("click", e => {
    const id = link.getAttribute("href");
    if (id.length < 2) { smoothScroll(0); return; }
    const target = document.querySelector(id);
    if (!target) return;
    e.preventDefault();
    smoothScroll(target.getBoundingClientRect().top + window.pageYOffset - 64);
  });
});

/* ---------- Reveal-on-scroll ---------- */
const io = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add("in");
      io.unobserve(entry.target);
    }
  });
}, { threshold: 0.15 });
document.querySelectorAll(".reveal").forEach(el => io.observe(el));

/* ---------- Sticky nav shade on scroll ---------- */
const nav = document.querySelector(".land-nav");
const onScroll = () => nav.classList.toggle("scrolled", window.pageYOffset > 10);
window.addEventListener("scroll", onScroll, { passive: true });

/* ---------- Count-up metrics ---------- */
const countIO = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    const el = entry.target;
    countIO.unobserve(el);
    const target = parseFloat(el.dataset.count);
    const dec = parseInt(el.dataset.dec || "0", 10);
    const prefix = el.dataset.prefix || "";
    const dur = 1400, startT = performance.now();
    const frame = now => {
      const t = Math.min(1, (now - startT) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      const val = target * eased;
      el.textContent = prefix + val.toFixed(dec);
      if (t < 1) requestAnimationFrame(frame);
      else el.textContent = prefix + target.toFixed(dec);
    };
    requestAnimationFrame(frame);
  });
}, { threshold: 0.5 });
document.querySelectorAll("[data-count]").forEach(el => countIO.observe(el));

/* ---------- Hero pipeline ball (looping preview) ---------- */
(function pipelineLoop() {
  const rail = document.querySelector(".pl-rail");
  if (!rail) return;
  const ball = document.getElementById("plBall");
  const line = document.getElementById("plLine");
  const status = document.getElementById("plStatus");
  const steps = Array.from(document.querySelectorAll(".pl-step"));
  const labels = {
    ingest: "Ingesting dispute#pay_1234…",
    classify: "Classifying — TF-IDF → non_receipt (conf 0.60)",
    executor: "Collecting evidence — logistics · security · crm",
    evaluate: "Evaluating — win-prob 0.92 → CONTEST",
    compile: "Compiling rebuttal — queued for filing",
  };
  const finish = "Filed — rebuttal submitted, audit chain intact ✓";

  const setBall = y => ball.style.transform = `translateY(${y}px)`;
  const lineH = () => line.clientHeight;
  const stepY = step => step.offsetTop + step.offsetHeight / 2 - 6;

  let stepIdx = 0;
  let active = null;
  let resetting = false;

  async function runOnce() {
    await sleep(1400); // let it sit "ready"
    ball.classList.add("show");
    // slide to step 0
    await tween(stepY(steps[0]));
    await mark(0);

    for (let i = 1; i < steps.length; i++) {
      await tween(stepY(steps[i]), 850);
      await mark(i);
    }
    status.textContent = finish;
    ball.classList.add("done");
    await sleep(2600);
    status.textContent = "Ready — awaiting dispute";
    steps.forEach(s => { s.classList.remove("active"); s.classList.remove("done"); });
    ball.classList.remove("show");
    ball.classList.remove("done");
    resetting = true;
    await sleep(900);
    resetting = false;
  }

  function mark(i) {
    if (active != null) steps[active].classList.replace("active", "done");
    active = i;
    steps[i].classList.add("active");
    status.textContent = labels[steps[i].dataset.key] || "Processing…";
    return sleep(850);
  }

  function tween(y, dur = 600) {
    return new Promise(res => {
      const start = parseFloat(getComputedStyle(ball).transform.split(",")[5] || 0) || 0;
      const startT = performance.now();
      const ease = t => t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
      const frame = now => {
        const t = Math.min(1, (now - startT) / dur);
        setBall(start + (y - start) * ease(t));
        if (t < 1) requestAnimationFrame(frame); else res();
      };
      requestAnimationFrame(frame);
    });
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  // restart loop, but pause when the hero is out of view
  let visible = true;
  const heroIO = new IntersectionObserver(([e]) => {
    const was = visible;
    visible = e.isIntersecting;
    if (visible && !resetting && !active) { ball.classList.add("show"); }
  }, { threshold: 0.2 });
  heroIO.observe(document.querySelector(".hero-visual"));

  (async function loop() {
    for (;;) {
      if (document.hidden || !visible) { await sleep(500); continue; }
      await runOnce();
    }
  })();
})();