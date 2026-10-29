// Minimal front end for the copilot API. No build step, no framework.
const $ = (s) => document.querySelector(s);
let token = null, me = null;

const EXAMPLES = {
  operator: ["What torque for the M10 flange bolts?", "What is the test pressure on the leak test bench?",
             "What are the steps of lockout tagout?", "What was the root cause of the oil leakage complaint?"],
  maintenance: ["Dispensing cell shows E-205, what is the likely cause?", "How do I vent the dosing pump of cell D2?",
                "Below which clamping force do the disc springs have to be replaced?"],
  quality: ["What was the root cause of the oil leakage complaint on the gearbox flange?",
            "What overall result did Kessler Gusstechnik get in the supplier audit?",
            "What was the internal scrap rate in September 2026?"],
  engineering: ["From when does the Machinery Regulation (EU) 2023/1230 apply?", "What Cmk do production torque tools need?",
                "What was the flange bolt torque in revision B of WI-ASM-014?"],
  admin: ["What budget was approved for the second source of housing castings?", "How many e-drive units were produced in Q3 2026?"],
};

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (token) headers["Authorization"] = "Bearer " + token;
  if (opts.json) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const r = await fetch(path, { ...opts, headers });
  if (r.status === 401) { logout(); throw new Error("session expired"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

async function showLogin() {
  const users = await api("/demo-users");
  $("#users").innerHTML = users.map((u) =>
    `<button data-u="${esc(u.username)}"><b>${esc(u.full_name)}</b><span class="role">${esc(u.role)}</span></button>`).join("");
  $("#users").querySelectorAll("button").forEach((b) => b.onclick = () => login(b.dataset.u));
}

async function login(username) {
  const body = new URLSearchParams({ username, password: "demo" });
  const r = await fetch("/auth/token", { method: "POST", body });
  if (!r.ok) return alertBox("Login failed");
  const data = await r.json();
  token = data.access_token; me = data.user;
  $("#login").classList.add("hidden"); $("#app").classList.remove("hidden");
  $("#who").innerHTML = `${esc(me.full_name)} <span class="role">${esc(me.role)}</span> <button id="logout">Switch user</button>`;
  $("#logout").onclick = logout;
  $("#examples").innerHTML = (EXAMPLES[me.role] || []).map((q) => `<button>${esc(q)}</button>`).join("");
  $("#examples").querySelectorAll("button").forEach((b) => b.onclick = () => { $("#q").value = b.textContent; ask(); });
  const health = await api("/health");
  $("#mode").value = health.default_mode;
  if (!health.llm_configured) $("#mode").querySelector('[value="llm"]').textContent = "LLM (no API key, falls back)";
  $("#result").innerHTML = "";
  loadDocs();
}

function logout() {
  token = null; me = null;
  $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); $("#who").innerHTML = "";
}

function alertBox(msg) { $("#result").innerHTML = `<div class="card answer flag">${esc(msg)}</div>`; }

function renderAnswer(a) {
  const lines = a.answer.split("\n").map((l) => l.replace(/^-\s*/, "")).filter(Boolean);
  const withCites = (t) => esc(t).replace(/\[(\d+)\]/g, '<span class="cite" data-n="$1">$1</span>');
  const body = a.abstained ? `<p>${esc(a.answer)}</p>`
    : (lines.length > 1 ? `<ul>${lines.map((l) => `<li>${withCites(l)}</li>`).join("")}</ul>` : `<p>${withCites(lines[0])}</p>`);
  const g = a.guard || {};
  const guard = a.abstained ? "" : (g.passed ? '<span class="pass">grounding check passed</span>'
    : `<span class="fail">grounding check failed${g.unsupported_numbers && g.unsupported_numbers.length ? " (numbers: " + esc(g.unsupported_numbers.join(", ")) + ")" : ""}</span>`);
  const cls = a.abstained ? "abstain" : (g.passed ? "" : "flag");
  const srcs = a.sources.map((s) => `
    <div class="src ${s.cited ? "cited" : ""}" id="src-${s.n}">
      <div class="head"><span><span class="num">[${s.n}]</span>${esc(s.doc_no)} Rev ${esc(s.revision)} &middot; ${esc(s.section)} &middot; p. ${s.page}</span>
      <span class="badge">${esc(s.status)} &middot; score ${s.score.toFixed(2)}</span></div>
      <div class="muted" style="font-size:13px">${esc(s.title)}</div>
      <pre>${esc(s.text)}</pre>
    </div>`).join("");
  $("#result").innerHTML = `
    <div class="card answer ${cls}">
      ${body}
      <div class="meta"><span>mode: ${esc(a.mode)}</span>${guard ? `<span>${guard}</span>` : ""}
        <span>${a.current_only ? "current revisions only" : "all revisions searched"}</span>
        <span>${a.timings.total_ms} ms</span></div>
      ${a.query_id ? `<div class="feedback">Was this helpful? <button data-h="1">Yes</button><button data-h="0">No</button><span id="fb"></span></div>` : ""}
    </div>
    ${a.sources.length ? `<div class="card sources"><h3>Sources</h3>${srcs}</div>` : ""}`;
  $("#result").querySelectorAll(".cite").forEach((c) => c.onclick = () =>
    document.getElementById("src-" + c.dataset.n).scrollIntoView({ behavior: "smooth", block: "center" }));
  $("#result").querySelectorAll(".feedback button").forEach((b) => b.onclick = async () => {
    await api("/feedback", { method: "POST", json: { query_id: a.query_id, helpful: b.dataset.h === "1" } });
    $("#fb").textContent = "thanks";
  });
}

async function ask(ev) {
  if (ev) ev.preventDefault();
  const question = $("#q").value.trim();
  if (question.length < 3) return;
  $("#result").innerHTML = '<div class="card muted">Searching&hellip;</div>';
  try {
    renderAnswer(await api("/ask", { method: "POST", json: { question, mode: $("#mode").value } }));
  } catch (e) { alertBox(e.message); }
}

async function loadDocs() {
  const docs = await api("/documents");
  $("#docs").innerHTML = docs.map((d) => `<tr class="${d.is_current ? "" : "old"}"><td class="mono">${esc(d.doc_no)}</td>
    <td>${esc(d.revision)}</td><td>${esc(d.title)}</td><td>${esc(d.doc_type)}</td><td>${esc(d.status)}</td>
    <td>${esc(d.effective)}</td></tr>`).join("");
}

document.querySelectorAll(".tab").forEach((t) => t.onclick = () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
  $("#tab-ask").classList.toggle("hidden", t.dataset.tab !== "ask");
  $("#tab-docs").classList.toggle("hidden", t.dataset.tab !== "docs");
});
$("#ask-form").onsubmit = ask;
showLogin();
