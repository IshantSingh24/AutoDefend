/* AutoDefend — login page controller (served at /login)
   Vanilla JS. Handles sign-in / create-account. On success (or an existing
   valid session) it redirects the merchant into the dashboard at /app. */

const $ = id => document.getElementById(id);

function showAuthMsg(type, text) {
  const box = $("auth-msg");
  box.className = type === "error" ? "auth-err" : "auth-ok";
  box.textContent = text;
  box.classList.remove("hidden");
}

function clearAuthMsg() {
  $("auth-msg").className = "hidden";
  $("auth-msg").textContent = "";
}

let mode = "login"; // 'login' | 'register'

function setMode(m) {
  mode = m;
  $("tab-login").classList.toggle("active", m === "login");
  $("tab-register").classList.toggle("active", m === "register");
  $("field-name").classList.toggle("hidden", m !== "register");
  $("field-merchant").classList.toggle("hidden", m !== "register");
  $("auth-title").textContent = m === "login" ? "Sign in" : "Create account";
  $("auth-sub").textContent = m === "login"
    ? "Autonomous chargeback defense with a verifiable audit trail"
    : "Create a merchant account. Your dashboard is scoped to your Merchant ID.";
  $("auth-submit").textContent = m === "login" ? "Sign in" : "Create account";
  $("password").autocomplete = m === "login" ? "current-password" : "new-password";
  clearAuthMsg();
}

async function submit(e) {
  e.preventDefault();
  clearAuthMsg();
  const email = $("email").value.trim();
  const password = $("password").value;
  const action = mode === "login" ? "login" : "register";
  const body = mode === "login"
    ? { email, password }
    : {
        email,
        password,
        full_name: $("full_name").value.trim(),
        merchant_id: $("merchant_id").value.trim(),
      };

  if (mode === "register" && !body.full_name) return showAuthMsg("error", "Please add your full name.");
  if (mode === "register" && !body.merchant_id) return showAuthMsg("error", "Please add a Merchant ID.");

  const btn = $("auth-submit");
  btn.disabled = true;
  btn.textContent = mode === "login" ? "Signing in…" : "Creating account…";

  try {
    const r = await fetch(`/auth/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (r.ok) {
      location.href = "/app";
      return;
    }

    let message = "Something went wrong. Please try again.";
    try {
      const err = await r.json();
      if (Array.isArray(err.detail)) {
        message = err.detail.map(d => (d.msg || "")).join(" · ") || message;
      } else if (typeof err.detail === "string") {
        message = err.detail;
      }
    } catch (_) { /* keep default */ }
    showAuthMsg("error", message);
  } finally {
    btn.disabled = false;
    btn.textContent = mode === "login" ? "Sign in" : "Create account";
  }
}

function init() {
  $("tab-login").addEventListener("click", () => setMode("login"));
  $("tab-register").addEventListener("click", () => setMode("register"));
  $("auth-form").addEventListener("submit", submit);

  // Already have a valid session? Skip straight to the dashboard.
  fetch("/auth/me", { credentials: "same-origin" }).then(r => {
    if (r.ok) location.href = "/app";
  }).catch(() => {});

  setMode("login");
  $("auth-page").classList.remove("hidden");
}

init();