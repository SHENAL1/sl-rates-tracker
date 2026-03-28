"""
Main Scraper — SL Rates Tracker
Runs all bank scrapers + gold scraper and saves results to Supabase.

Usage:
  python scraper.py                  # Run all scrapers
  python scraper.py --banks-only     # Skip gold
  python scraper.py --gold-only      # Skip banks
  python scraper.py --dry-run        # Print results, don't save to Supabase

Environment variables required (set in .env or GitHub Actions secrets):
  SUPABASE_URL          — your Supabase project URL
  SUPABASE_SERVICE_KEY  — your Supabase service role key (not anon key)
  EXCHANGE_RATE_API_KEY — free key from exchangerate-api.com (optional but recommended)
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone

import requests

# Load .env if running locally
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import bank scrapers
from banks.combank import scrape as scrape_combank
from banks.sampath import scrape as scrape_sampath
from banks.hnb import scrape as scrape_hnb
from banks.nsb import scrape as scrape_nsb
from banks.ntb import scrape as scrape_ntb
from gold import scrape as scrape_gold


# ─── Supabase helpers ─────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

def supabase_upsert(table: str, data: list[dict] | dict) -> bool:
    """Upsert records into a Supabase table via REST API."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("⚠️  Supabase credentials not set — skipping DB save.")
        return False

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    payload = data if isinstance(data, list) else [data]

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            print(f"✅  Saved {len(payload)} record(s) to '{table}'")
            return True
        else:
            print(f"❌  Supabase error [{resp.status_code}]: {resp.text[:300]}")
            return False
    except Exception as e:
        print(f"❌  Supabase request failed: {e}")
        return False


def supabase_delete_today(table: str) -> None:
    """Delete today's records before re-inserting (clean refresh)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return

    today = datetime.now(timezone.utc).date().isoformat()
    url = f"{SUPABASE_URL}/rest/v1/{table}?scraped_date=eq.{today}"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    try:
        resp = requests.delete(url, headers=headers, timeout=10)
        print(f"🗑️   Cleared today's records from '{table}' [{resp.status_code}]")
    except Exception as e:
        print(f"[Warning] Could not clear old records: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def run(dry_run=False, banks_only=False, gold_only=False):
    run_time = datetime.now(timezone.utc).isoformat()
    print(f"\n{'='*55}")
    print(f"  SL Rates Tracker — Scrape Run")
    print(f"  {run_time}")
    print(f"{'='*55}\n")

    all_fd_rates = []
    gold_data = None

    # ── Bank FD Rates ──────────────────────────────────────────────
    if not gold_only:
        bank_scrapers = [
            ("Commercial Bank", scrape_combank),
            ("Sampath Bank",    scrape_sampath),
            ("HNB",             scrape_hnb),
            ("NSB",             scrape_nsb),
            ("NTB",             scrape_ntb),
        ]

        for bank_name, scraper_fn in bank_scrapers:
            print(f"\n── {bank_name} ─────────────────────────────────")
            try:
                rates = scraper_fn()
                all_fd_rates.extend(rates)
            except Exception as e:
                print(f"❌  {bank_name} scraper crashed: {e}")

        print(f"\n── FD Rates Summary ─────────────────────────────────")
        print(f"Total entries scraped: {len(all_fd_rates)}")

        if dry_run:
            print("\n[DRY RUN] FD Rates:")
            print(json.dumps(all_fd_rates, indent=2))
        elif all_fd_rates:
            supabase_delete_today("fd_rates")
            supabase_upsert("fd_rates", all_fd_rates)

    # ── Gold Rates ─────────────────────────────────────────────────
    if not banks_only:
        print(f"\n── Gold Rates ───────────────────────────────────────")
        try:
            gold_data = scrape_gold()
        except Exception as e:
            print(f"❌  Gold scraper crashed: {e}")

        if dry_run and gold_data:
            print("\n[DRY RUN] Gold Rates:")
            print(json.dumps(gold_data, indent=2))
        elif gold_data:
            supabase_upsert("gold_rates", gold_data)

    print(f"\n{'='*55}")
    print(f"  Done! ✓")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SL Rates Tracker Scraper")
    parser.add_argument("--dry-run",    action="store_true", help="Print results, don't save to DB")
    parser.add_argument("--banks-only", action="store_true", help="Only scrape bank FD rates")
    parser.add_argument("--gold-only",  action="store_true", help="Only scrape gold rates")
    args = parser.parse_args()

    run(dry_run=args.dry_run, banks_only=args.banks_only, gold_only=args.gold_only)
