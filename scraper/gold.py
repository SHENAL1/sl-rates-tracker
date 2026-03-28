"""
Gold Rate Scraper for Sri Lanka
Sources:
  - Gold price (USD/oz): metals.live free API (no key required)
  - LKR exchange rate:   exchangerate-api.com (free tier, 1500 req/month)
  - Fallback gold:       goldpricez.com (scrape if API fails)

SETUP:
  Set environment variable EXCHANGE_RATE_API_KEY with your free key from:
  https://www.exchangerate-api.com/  (sign up, free — 1500 req/month)

  Gold API is free, no key needed from metals.live.
"""

import os
import requests
from datetime import date, datetime

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

# ─── Gold Price (USD per troy oz) ────────────────────────────────────────────

def get_gold_price_usd() -> float | None:
    """Fetch gold price in USD per troy ounce from metals.live (free, no key)."""
    try:
        resp = requests.get(
            "https://metals.live/api/v1/latest",
            headers=HEADERS,
            timeout=10
        )
        data = resp.json()
        # Response format: [{"gold": 2350.45, "silver": 28.1, ...}]
        if isinstance(data, list) and data:
            gold_usd = data[0].get("gold")
            if gold_usd:
                return float(gold_usd)
    except Exception as e:
        print(f"[Gold] metals.live failed: {e}")

    # Fallback: try goldpricez API
    try:
        resp = requests.get(
            "https://data-asg.goldprice.org/dbXRates/USD",
            headers=HEADERS,
            timeout=10
        )
        data = resp.json()
        # Response: {"items": [{"xauPrice": 2350.45, ...}]}
        items = data.get("items", [])
        if items:
            return float(items[0].get("xauPrice", 0)) or None
    except Exception as e:
        print(f"[Gold] goldprice.org fallback failed: {e}")

    return None


# ─── LKR Exchange Rate ────────────────────────────────────────────────────────

def get_usd_to_lkr() -> float | None:
    """
    Fetch USD → LKR exchange rate.
    Uses exchangerate-api.com free tier if EXCHANGE_RATE_API_KEY is set,
    otherwise falls back to open.er-api.com (no key, but less reliable).
    """
    api_key = os.environ.get("EXCHANGE_RATE_API_KEY")

    if api_key:
        try:
            resp = requests.get(
                f"https://v6.exchangerate-api.com/v6/{api_key}/pair/USD/LKR",
                headers=HEADERS,
                timeout=10
            )
            data = resp.json()
            if data.get("result") == "success":
                return float(data["conversion_rate"])
        except Exception as e:
            print(f"[Gold] exchangerate-api failed: {e}")

    # Fallback: open.er-api.com (free, no key, less reliable)
    try:
        resp = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            headers=HEADERS,
            timeout=10
        )
        data = resp.json()
        lkr_rate = data.get("rates", {}).get("LKR")
        if lkr_rate:
            return float(lkr_rate)
    except Exception as e:
        print(f"[Gold] open.er-api fallback failed: {e}")

    return None


# ─── Gold calculations ────────────────────────────────────────────────────────

GRAMS_PER_TROY_OZ = 31.1035

def calculate_gold_rates(gold_usd: float, usd_to_lkr: float) -> dict:
    """
    Calculate gold rates in LKR for common purities and weights.
    Sri Lanka typically sells gold in grams, so we calculate per gram.
    """
    gold_lkr_per_oz = gold_usd * usd_to_lkr
    gold_lkr_per_gram = gold_lkr_per_oz / GRAMS_PER_TROY_OZ

    return {
        "gold_usd_per_oz": round(gold_usd, 2),
        "usd_to_lkr": round(usd_to_lkr, 2),
        "gold_lkr_per_gram_24k": round(gold_lkr_per_gram, 2),
        "gold_lkr_per_gram_22k": round(gold_lkr_per_gram * (22/24), 2),
        "gold_lkr_per_gram_21k": round(gold_lkr_per_gram * (21/24), 2),
        "gold_lkr_per_gram_18k": round(gold_lkr_per_gram * (18/24), 2),
        # Common Sri Lankan weights
        "gold_lkr_per_pavan_22k": round(gold_lkr_per_gram * (22/24) * 8, 2),  # 1 pavan = 8g
        "scraped_date": str(date.today()),
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "note": "International spot price. Local dealer rates may vary slightly."
    }


def scrape() -> dict | None:
    """Main function — returns gold rate data dict, or None on failure."""
    print("[Gold] Fetching gold price (USD)...")
    gold_usd = get_gold_price_usd()
    if not gold_usd:
        print("[Gold] ERROR: Could not fetch gold price.")
        return None

    print(f"[Gold] Gold: ${gold_usd}/oz")

    print("[Gold] Fetching USD→LKR rate...")
    usd_to_lkr = get_usd_to_lkr()
    if not usd_to_lkr:
        print("[Gold] ERROR: Could not fetch exchange rate.")
        return None

    print(f"[Gold] USD→LKR: {usd_to_lkr}")

    rates = calculate_gold_rates(gold_usd, usd_to_lkr)
    print(f"[Gold] 24K: LKR {rates['gold_lkr_per_gram_24k']}/g | 22K: LKR {rates['gold_lkr_per_gram_22k']}/g")
    return rates


if __name__ == "__main__":
    import json
    data = scrape()
    print(json.dumps(data, indent=2))
