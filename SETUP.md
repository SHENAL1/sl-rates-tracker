# SL Rates Tracker — Setup Guide

## ✅ Already done for you
- Supabase project created: **sl-rates-tracker** (`ap-south-1` — Mumbai, closest to Sri Lanka)
- Project URL: `https://bcpdrudyqtatzzisxygd.supabase.co`
- Database tables, RLS policies, and views are live
- Seed data loaded (17 FD rates + 1 gold rate) so the site works immediately
- Frontend already wired to the Supabase project

---

## Step 1 — Get your service role key (for the scraper)

The scraper needs the **service role** key (write access) — this is kept secret and never in the frontend.

1. Go to [supabase.com/dashboard](https://supabase.com/dashboard) → **sl-rates-tracker** project
2. **Project Settings → API → service_role** → copy the key

---

## Step 2 — Exchange Rate API key (free, optional but recommended)

1. Sign up at [exchangerate-api.com](https://www.exchangerate-api.com/) — free, 1500 req/month
2. Copy your API key

---

## Step 3 — Test the scraper locally

```bash
cd scraper
pip install -r requirements.txt
playwright install chromium

# Create your local .env
cp ../.env.example .env
# Fill in SUPABASE_SERVICE_KEY and EXCHANGE_RATE_API_KEY in .env

# Dry run first — prints results, doesn't save to DB
python scraper.py --dry-run

# If results look correct, run for real
python scraper.py
```

---

## Step 4 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit — SL Rates Tracker"
git remote add origin https://github.com/YOUR_USERNAME/sl-rates-tracker.git
git push -u origin main
```

---

## Step 5 — Add GitHub Secrets (for the daily auto-scrape)

In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|-------------|-------|
| `SUPABASE_URL` | `https://bcpdrudyqtatzzisxygd.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Your service_role key from Supabase dashboard |
| `EXCHANGE_RATE_API_KEY` | Your exchangerate-api key |

The GitHub Action will run automatically every day at ~8 AM Sri Lanka time.
You can also trigger it manually: **GitHub → Actions → Daily Rates Scraper → Run workflow**.

---

## Step 6 — Deploy the frontend

### Option A: Netlify (recommended)
1. Go to [netlify.com](https://netlify.com) → **Add new site → Import an existing project**
2. Connect your GitHub repo
3. Set **Publish directory** to `frontend`
4. Click Deploy — your site is live!

### Option B: GitHub Pages
1. Go to your repo → **Settings → Pages**
2. Source: **Deploy from a branch** → `main` → `/frontend`
3. Site live at `https://YOUR_USERNAME.github.io/sl-rates-tracker/`

---

## Project structure

```
sl-rates-tracker/
├── scraper/
│   ├── banks/combank.py      ← Static HTML scraper
│   ├── banks/sampath.py      ← JS-rendered (Playwright)
│   ├── banks/hnb.py          ← Smart scraper (static + Playwright fallback)
│   ├── gold.py               ← Gold price + LKR conversion
│   └── scraper.py            ← Main runner
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js                ← Already configured with your Supabase URL + key
├── .github/workflows/
│   └── scrape.yml            ← Daily cron at 8 AM SL time
├── supabase/schema.sql       ← Already applied — keep for reference
└── .env.example
```

---

## Troubleshooting

**Scraper returns empty results for a bank** — The bank updated their website HTML.
Check the relevant file in `scraper/banks/` and update the CSS selectors.

**Gold rate not loading** — Check `EXCHANGE_RATE_API_KEY` is set. Without it, the free fallback may be rate-limited.

**Frontend shows "Could not load" errors** — Confirm you're online and Supabase project is active at [supabase.com/dashboard](https://supabase.com/dashboard).
