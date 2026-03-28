/**
 * SL Rates Tracker — Frontend App
 * Reads from Supabase (public anon key, read-only)
 * Config: edit SUPABASE_URL and SUPABASE_ANON_KEY below
 */

// ─── CONFIG — update these with your Supabase project values ──────────────────
const SUPABASE_URL      = "https://bcpdrudyqtatzzisxygd.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJjcGRydWR5cXRhdHp6aXN4eWdkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ3MDU2MDQsImV4cCI6MjA5MDI4MTYwNH0._CUdNVnQwq9UPbGbfAJ8GJkq3zXDzhM7J55fN1aevxs";
// ─────────────────────────────────────────────────────────────────────────────

const API = `${SUPABASE_URL}/rest/v1`;
const HEADERS = {
  "apikey":        SUPABASE_ANON_KEY,
  "Authorization": `Bearer ${SUPABASE_ANON_KEY}`,
  "Content-Type":  "application/json",
};

// ─── Supabase fetch helpers ───────────────────────────────────────────────────

async function supaFetch(endpoint, params = {}) {
  const url = new URL(`${API}/${endpoint}`);
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const resp = await fetch(url.toString(), { headers: HEADERS });
  if (!resp.ok) throw new Error(`Supabase error ${resp.status}: ${await resp.text()}`);
  return resp.json();
}

// ─── State ────────────────────────────────────────────────────────────────────

let allFdRates   = [];
let activeBank   = "all";

// ─── Format helpers ───────────────────────────────────────────────────────────

const fmtLKR = (n) =>
  new Intl.NumberFormat("en-LK", { style: "currency", currency: "LKR", maximumFractionDigits: 2 })
    .format(n);

const fmtUSD = (n) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 })
    .format(n);

const fmtDate = (dateStr) => {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
};

function bankSlug(bank) {
  if (!bank) return "";
  const b = bank.toLowerCase();
  if (b.includes("commercial")) return "combank";
  if (b.includes("sampath"))    return "sampath";
  if (b.includes("hnb"))        return "hnb";
  return b.replace(/\s+/g, "-");
}

// ─── Gold rates ───────────────────────────────────────────────────────────────

async function loadGoldRates() {
  document.getElementById("gold-loading").classList.remove("hidden");
  document.getElementById("gold-content").classList.add("hidden");
  document.getElementById("gold-error").classList.add("hidden");

  try {
    const data = await supaFetch("gold_rates", {
      select: "*",
      order:  "scraped_date.desc",
      limit:  "1",
    });

    if (!data || data.length === 0) throw new Error("No gold data available.");
    const g = data[0];

    document.getElementById("gold-usd").textContent  = fmtUSD(g.gold_usd_per_oz);
    document.getElementById("gold-fx").textContent   = `1 USD = LKR ${Number(g.usd_to_lkr).toFixed(2)}`;
    document.getElementById("gold-24k").textContent  = fmtLKR(g.gold_lkr_per_gram_24k);
    document.getElementById("gold-22k").textContent  = fmtLKR(g.gold_lkr_per_gram_22k);
    document.getElementById("gold-21k").textContent  = fmtLKR(g.gold_lkr_per_gram_21k);
    document.getElementById("gold-18k").textContent  = fmtLKR(g.gold_lkr_per_gram_18k);
    document.getElementById("gold-pavan").textContent = fmtLKR(g.gold_lkr_per_pavan_22k);
    document.getElementById("gold-date").textContent  = fmtDate(g.scraped_date);

    document.getElementById("gold-loading").classList.add("hidden");
    document.getElementById("gold-content").classList.remove("hidden");
  } catch (err) {
    console.error("[Gold]", err);
    document.getElementById("gold-loading").classList.add("hidden");
    document.getElementById("gold-error").classList.remove("hidden");
  }
}

// ─── FD rates ─────────────────────────────────────────────────────────────────

async function loadFdRates() {
  document.getElementById("fd-loading").classList.remove("hidden");
  document.getElementById("fd-content").classList.add("hidden");
  document.getElementById("fd-error").classList.add("hidden");

  try {
    // Use the latest_fd_rates view (most recent per bank+tenure)
    const data = await supaFetch("latest_fd_rates", {
      select: "*",
      order:  "bank.asc,rate_percent.desc",
      limit:  "200",
    });

    if (!data || data.length === 0) throw new Error("No FD rate data available.");
    allFdRates = data;

    // Update date badge (most recent)
    const latestDate = data.reduce((max, r) => r.scraped_date > max ? r.scraped_date : max, "");
    document.getElementById("fd-date").textContent = fmtDate(latestDate);

    renderFdTable();

    document.getElementById("fd-loading").classList.add("hidden");
    document.getElementById("fd-content").classList.remove("hidden");
  } catch (err) {
    console.error("[FD]", err);
    document.getElementById("fd-loading").classList.add("hidden");
    document.getElementById("fd-error").classList.remove("hidden");
  }
}

function renderFdTable() {
  const tbody = document.getElementById("fd-tbody");
  tbody.innerHTML = "";

  const filtered = activeBank === "all"
    ? allFdRates
    : allFdRates.filter(r => r.bank === activeBank);

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;color:var(--text-muted);padding:24px">No rates available for this bank yet.</td></tr>`;
    return;
  }

  filtered.forEach(row => {
    const slug = bankSlug(row.bank);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="bank-badge ${slug}">${row.bank}</span></td>
      <td>${row.tenure}</td>
      <td><span class="rate-value">${Number(row.rate_percent).toFixed(2)}%</span></td>
    `;
    tbody.appendChild(tr);
  });
}

// ─── Bank filter tabs ─────────────────────────────────────────────────────────

document.getElementById("bank-tabs").addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (!tab) return;
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  tab.classList.add("active");
  activeBank = tab.dataset.bank;
  renderFdTable();
});

// ─── Refresh button ───────────────────────────────────────────────────────────

async function refreshRates() {
  const btn = document.getElementById("refresh-btn");
  btn.disabled = true;
  btn.classList.add("spinning");
  btn.querySelector(".refresh-icon").textContent = "↻";

  showToast("🔄 Refreshing rates...");

  try {
    await Promise.all([loadGoldRates(), loadFdRates()]);
    showToast("✅ Rates updated!");
    updateLastUpdatedTime();
  } catch (err) {
    showToast("❌ Refresh failed. Please try again.", true);
  } finally {
    btn.disabled = false;
    btn.classList.remove("spinning");
  }
}

// ─── Toast ────────────────────────────────────────────────────────────────────

let toastTimer;
function showToast(msg, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = "toast" + (isError ? " error" : "");
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
}

// ─── Last updated time ────────────────────────────────────────────────────────

function updateLastUpdatedTime() {
  const el = document.getElementById("last-updated");
  const now = new Date();
  el.textContent = `Updated ${now.toLocaleTimeString("en-LK", { hour: "2-digit", minute: "2-digit" })}`;
}

// ─── Init ─────────────────────────────────────────────────────────────────────

async function init() {
  await Promise.all([loadGoldRates(), loadFdRates()]);
  updateLastUpdatedTime();
}

init();
