-- ============================================================
-- SL Rates Tracker — Supabase Schema
-- Run this in the Supabase SQL Editor to set up your tables
-- ============================================================

-- FD Rates table
CREATE TABLE IF NOT EXISTS fd_rates (
  id            BIGSERIAL PRIMARY KEY,
  bank          TEXT        NOT NULL,
  tenure        TEXT        NOT NULL,
  rate_percent  NUMERIC     NOT NULL,
  notes         TEXT        DEFAULT '',
  scraped_date  DATE        NOT NULL DEFAULT CURRENT_DATE,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast queries by date and bank
CREATE INDEX IF NOT EXISTS idx_fd_rates_date ON fd_rates(scraped_date DESC);
CREATE INDEX IF NOT EXISTS idx_fd_rates_bank ON fd_rates(bank);

-- Gold Rates table (one row per day)
CREATE TABLE IF NOT EXISTS gold_rates (
  id                        BIGSERIAL PRIMARY KEY,
  gold_usd_per_oz           NUMERIC     NOT NULL,
  usd_to_lkr                NUMERIC     NOT NULL,
  gold_lkr_per_gram_24k     NUMERIC     NOT NULL,
  gold_lkr_per_gram_22k     NUMERIC     NOT NULL,
  gold_lkr_per_gram_21k     NUMERIC     NOT NULL,
  gold_lkr_per_gram_18k     NUMERIC     NOT NULL,
  gold_lkr_per_pavan_22k    NUMERIC,
  note                      TEXT        DEFAULT '',
  scraped_date              DATE        NOT NULL DEFAULT CURRENT_DATE,
  scraped_at                TIMESTAMPTZ,
  created_at                TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gold_rates_date ON gold_rates(scraped_date DESC);

-- Enable Row Level Security (RLS) — read-only for everyone (anon), write only via service key
ALTER TABLE fd_rates   ENABLE ROW LEVEL SECURITY;
ALTER TABLE gold_rates ENABLE ROW LEVEL SECURITY;

-- Public read policy (your frontend uses the anon key to read)
CREATE POLICY "Public can read fd_rates"
  ON fd_rates FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "Public can read gold_rates"
  ON gold_rates FOR SELECT
  TO anon
  USING (true);

-- Service role can do everything (scraper uses service key)
CREATE POLICY "Service role full access fd_rates"
  ON fd_rates FOR ALL
  TO service_role
  USING (true);

CREATE POLICY "Service role full access gold_rates"
  ON gold_rates FOR ALL
  TO service_role
  USING (true);

-- ── Useful views ──────────────────────────────────────────────────────────────

-- Latest FD rates per bank — strictly filtered to real FD rates only.
-- Filtering rules:
--   1. Tenure must contain a time unit (month/year/day/week)
--   2. Rate must be between 1% and 20%
--   3. Tenure must START with a digit (rejects "Fixed Loans...", "Short Term Gold Loans...", etc.)
--   4. No currency or loan keywords in tenure
--   5. Whitespace is normalised for deduplication
CREATE OR REPLACE VIEW latest_fd_rates AS
WITH normalized AS (
  SELECT
    bank,
    regexp_replace(trim(tenure), '\s+', ' ', 'g') AS tenure,
    rate_percent,
    notes,
    scraped_date
  FROM fd_rates
  WHERE
    tenure ~* '(month|year|day|week)'
    AND rate_percent BETWEEN 1.0 AND 20.0
    AND tenure ~* '^\s*[0-9]'
    AND tenure !~* '(dollar|pound|euro|franc|yen|yuan|rupee|dirham|kroner|krona|u\.s\.|u\.k\.)'
    AND tenure !~* '(loan|lending|leasing|overdraft|agri|udara|apr|treasury|t-bill|saving[^s])'
)
SELECT DISTINCT ON (bank, tenure)
  bank, tenure, rate_percent, notes, scraped_date
FROM normalized
ORDER BY bank, tenure, scraped_date DESC, rate_percent DESC;

-- Latest gold rate
CREATE OR REPLACE VIEW latest_gold_rate AS
SELECT * FROM gold_rates
ORDER BY scraped_date DESC
LIMIT 1;
