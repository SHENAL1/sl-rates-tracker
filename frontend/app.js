/**
 * SL Rates Tracker — Frontend App
 * Reads from Supabase (public anon key, read-only)
 */

// ─── CONFIG ───────────────────────────────────────────────────────────────────
const SUPABASE_URL      = "https://bcpdrudyqtatzzisxygd.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJjcGRydWR5cXRhdHp6aXN4eWdkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ3MDU2MDQsImV4cCI6MjA5MDI4MTYwNH0._CUdNVnQwq9UPbGbfAJ8GJkq3zXDzhM7J55fN1aevxs";
// ─────────────────────────────────────────────────────────────────────────────

const API = `${SUPABASE_URL}/rest/v1`;
const HEADERS = {
  "apikey":        SUPABASE_ANON_KEY,
  "Authorization": `Bearer ${SUPABASE_ANON_KEY}`,
  "Content-Type":  "application/json",
};

// ─── Supabase helpers ─────────────────────────────────────────────────────────

async function supaFetch(endpoint, params = {}) {
  const url = new URL(`${API}/${endpoint}`);
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const resp = await fetch(url.toString(), { headers: HEADERS });
  if (!resp.ok) throw new Error(`Supabase error ${resp.status}: ${await resp.text()}`);
  return resp.json();
}

// ─── State ────────────────────────────────────────────────────────────────────

let allFdRates = [];
let activeBank = "all";
let goldChartInstance = null;

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
  if (b.includes("nsb"))        return "nsb";
  if (b.includes("ntb") || b.includes("nations trust")) return "ntb";
  return b.replace(/\s+/g, "-");
}

// ─── Tenure sorting helpers ───────────────────────────────────────────────────

/**
 * Convert a tenure string to approximate days for sorting (shortest first).
 * e.g. "1 Month" → 30, "3 Months" → 90, "100 Days" → 100, "2 Years" → 730
 */
function tenureToDays(tenure) {
  if (!tenure) return 99999;
  const t = tenure.toLowerCase();

  // Extract the leading number
  const numMatch = t.match(/^(\d+(?:\.\d+)?)/);
  if (!numMatch) return 99999;
  const num = parseFloat(numMatch[1]);

  if (t.includes("day"))   return num;
  if (t.includes("week"))  return num * 7;
  if (t.includes("month")) return num * 30;
  if (t.includes("year"))  return num * 365;
  return 99999;
}

/**
 * Normalize tenure to just the base duration (strip payment frequency suffixes).
 * Used for "best rate" grouping: "12 Months (Monthly)" → "12 months"
 */
function baseTenure(tenure) {
  return tenure
    .toLowerCase()
    .replace(/\s*\(.*?\)/g, "")   // remove anything in parentheses
    .replace(/\s*-\s*(interest|monthly|annually|maturity|at maturity).*/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

// ─── Live gold & exchange rate fetchers ──────────────────────────────────────

async function fetchLiveGoldUSD() {
  try {
    const r = await fetch("https://data-asg.goldprice.org/dbXRates/USD");
    const d = await r.json();
    const price = d?.items?.[0]?.xauPrice;
    if (price) return parseFloat(price);
  } catch (_) {}

  try {
    const r = await fetch("https://metals.live/api/v1/latest");
    const d = await r.json();
    const price = Array.isArray(d) ? d[0]?.gold : d?.gold;
    if (price) return parseFloat(price);
  } catch (_) {}

  return null;
}

async function fetchLiveUSDtoLKR() {
  try {
    const r = await fetch("https://open.er-api.com/v6/latest/USD");
    const d = await r.json();
    const rate = d?.rates?.LKR;
    if (rate) return parseFloat(rate);
  } catch (_) {}

  try {
    const r = await fetch("https://api.frankfurter.app/latest?from=USD&to=LKR");
    const d = await r.json();
    const rate = d?.rates?.LKR;
    if (rate) return parseFloat(rate);
  } catch (_) {}

  return null;
}

function calcGoldRates(goldUSD, usdToLKR) {
  const perGram = (goldUSD * usdToLKR) / 31.1035;
  return {
    gold_usd_per_oz:        goldUSD,
    usd_to_lkr:             usdToLKR,
    gold_lkr_per_gram_24k:  Math.round(perGram * 100) / 100,
    gold_lkr_per_gram_22k:  Math.round(perGram * (22/24) * 100) / 100,
    gold_lkr_per_gram_21k:  Math.round(perGram * (21/24) * 100) / 100,
    gold_lkr_per_gram_18k:  Math.round(perGram * (18/24) * 100) / 100,
    gold_lkr_per_pavan_22k: Math.round(perGram * (22/24) * 8 * 100) / 100,
  };
}

// ─── Gold history chart ───────────────────────────────────────────────────────

async function loadGoldChart(currentGoldUSD, currentUSDtoLKR) {
  const noteEl = document.getElementById("gold-chart-note");

  try {
    let labels = [];
    let prices = [];

    // Always use Supabase stored history (seeded + daily scrape appends)
    const data = await supaFetch("gold_rates", {
      select: "scraped_date,gold_lkr_per_gram_24k",
      order:  "scraped_date.asc",
      limit:  "30",
    });
    if (data && data.length > 0) {
      labels = data.map(r => {
        const d = new Date(r.scraped_date);
        return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
      });
      prices = data.map(r => parseFloat(r.gold_lkr_per_gram_24k));
    }

    // Append today's live price if not already the last point
    if (currentGoldUSD && currentUSDtoLKR) {
      const todayLabel = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short" });
      const todayPrice = Math.round((currentGoldUSD * currentUSDtoLKR) / 31.1035 * 100) / 100;
      if (labels[labels.length - 1] !== todayLabel) {
        labels.push(todayLabel);
        prices.push(todayPrice);
      }
    }

    if (prices.length < 2) {
      noteEl.textContent = "Not enough history yet — chart will populate as data accumulates daily.";
      return;
    }

    // Destroy previous chart instance if any
    if (goldChartInstance) goldChartInstance.destroy();

    const ctx = document.getElementById("gold-chart").getContext("2d");
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const padding  = (maxPrice - minPrice) * 0.1 || 500;

    goldChartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "24K Gold (LKR/g)",
          data: prices,
          borderColor:     "#C9A84C",
          backgroundColor: "rgba(201,168,76,0.12)",
          borderWidth: 2,
          pointRadius: prices.length > 15 ? 0 : 3,
          pointHoverRadius: 5,
          fill: true,
          tension: 0.3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` LKR ${ctx.parsed.y.toLocaleString("en-LK", { minimumFractionDigits: 2 })}`,
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              font: { size: 10 },
              color: "#94A3B8",
              maxTicksLimit: 8,
              maxRotation: 0,
            },
          },
          y: {
            min: Math.floor((minPrice - padding) / 100) * 100,
            max: Math.ceil((maxPrice + padding) / 100) * 100,
            grid: { color: "rgba(0,0,0,0.05)" },
            ticks: {
              font: { size: 10 },
              color: "#94A3B8",
              callback: (v) => `LKR ${v.toLocaleString()}`,
            },
          },
        },
      },
    });

    if (prices.length < 7) {
      noteEl.textContent = `${prices.length} day(s) of data so far — chart fills in automatically each day.`;
    } else {
      noteEl.textContent = "";
    }

  } catch (err) {
    console.warn("[GoldChart]", err);
    noteEl.textContent = "Could not load historical gold data.";
  }
}

// ─── Gold rates ───────────────────────────────────────────────────────────────

async function loadGoldRates() {
  document.getElementById("gold-loading").classList.remove("hidden");
  document.getElementById("gold-content").classList.add("hidden");
  document.getElementById("gold-error").classList.add("hidden");

  try {
    const [goldUSD, usdToLKR] = await Promise.all([
      fetchLiveGoldUSD(),
      fetchLiveUSDtoLKR(),
    ]);

    let g;

    if (goldUSD && usdToLKR) {
      g = calcGoldRates(goldUSD, usdToLKR);
      g.scraped_date = new Date().toISOString().split("T")[0];
      g.isLive = true;
    } else {
      console.warn("[Gold] Live APIs failed, falling back to Supabase cache.");
      const data = await supaFetch("gold_rates", {
        select: "*",
        order:  "scraped_date.desc",
        limit:  "1",
      });
      if (!data || data.length === 0) throw new Error("No gold data available.");
      g = data[0];
      g.isLive = false;
    }

    document.getElementById("gold-usd").textContent   = fmtUSD(g.gold_usd_per_oz);
    document.getElementById("gold-fx").textContent    = `1 USD = LKR ${Number(g.usd_to_lkr).toFixed(2)}`;
    document.getElementById("gold-24k").textContent   = fmtLKR(g.gold_lkr_per_gram_24k);
    document.getElementById("gold-22k").textContent   = fmtLKR(g.gold_lkr_per_gram_22k);
    document.getElementById("gold-21k").textContent   = fmtLKR(g.gold_lkr_per_gram_21k);
    document.getElementById("gold-18k").textContent   = fmtLKR(g.gold_lkr_per_gram_18k);
    document.getElementById("gold-pavan").textContent = fmtLKR(g.gold_lkr_per_pavan_22k);

    const goldDateEl = document.getElementById("gold-date");
    goldDateEl.textContent = g.isLive ? "⚡ Live" : fmtDate(g.scraped_date);
    goldDateEl.className   = g.isLive ? "date-badge live" : "date-badge";

    document.getElementById("gold-loading").classList.add("hidden");
    document.getElementById("gold-content").classList.remove("hidden");

    // Load the history chart after showing gold content
    const usdVal = g.isLive ? g.gold_usd_per_oz : null;
    const fxVal  = g.isLive ? g.usd_to_lkr       : null;
    loadGoldChart(usdVal, fxVal);

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
    const data = await supaFetch("latest_fd_rates", {
      select: "*",
      order:  "bank.asc,rate_percent.desc",
      limit:  "500",
    });

    if (!data || data.length === 0) throw new Error("No FD rate data available.");
    allFdRates = data;

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

  // ── Sort by tenure duration (shortest first) ──────────────────
  const sorted = [...filtered].sort((a, b) => {
    const daysA = tenureToDays(a.tenure);
    const daysB = tenureToDays(b.tenure);
    if (daysA !== daysB) return daysA - daysB;
    // Same duration: sort by rate descending
    return parseFloat(b.rate_percent) - parseFloat(a.rate_percent);
  });

  // ── Build "best rate per base-tenure" map (across ALL banks, not just filtered) ──
  const bestRateMap = {};   // baseTenure key → { rate, bank }
  allFdRates.forEach(r => {
    const key  = baseTenure(r.tenure);
    const rate = parseFloat(r.rate_percent);
    if (!bestRateMap[key] || rate > bestRateMap[key].rate) {
      bestRateMap[key] = { rate, bank: r.bank };
    }
  });

  // ── Render rows ───────────────────────────────────────────────
  sorted.forEach(row => {
    const slug = bankSlug(row.bank);
    const rate = parseFloat(row.rate_percent);
    const key  = baseTenure(row.tenure);
    const best = bestRateMap[key];

    const isBest = best && Math.abs(best.rate - rate) < 0.001;
    const bestBadge = isBest
      ? `<span class="best-badge" title="Best rate for this tenure across all banks">★ Best</span>`
      : "";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="bank-badge ${slug}">${row.bank}</span></td>
      <td>${row.tenure}</td>
      <td><span class="rate-value">${rate.toFixed(2)}%</span>${bestBadge}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ─── Main tab switching (Gold / FD Rates) ─────────────────────────────────────

document.getElementById("main-tabs").addEventListener("click", (e) => {
  const tab = e.target.closest(".main-tab");
  if (!tab) return;
  const panelId = tab.dataset.panel;

  document.querySelectorAll(".main-tab").forEach(t => t.classList.remove("active"));
  tab.classList.add("active");

  document.querySelectorAll(".panel").forEach(p => p.classList.add("hidden"));
  document.getElementById(panelId).classList.remove("hidden");
});

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
