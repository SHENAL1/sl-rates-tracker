"""
Commercial Bank Sri Lanka - FD Rate Scraper
Pages scraped:
  - Standard LKR FDs:  https://www.combank.lk/rates-tariff
  - Special FDs:       https://www.combank.lk/personal-banking/term-deposits/special-100-days-...

IMPORTANT: ComBank's rates page also contains FCBU (foreign currency) deposit rates
with currency names like "USD", "GBP", "AUD" as tenures. We strictly filter
to only accept LKR rates with time-based tenures.
"""

import requests
import re
from bs4 import BeautifulSoup
from datetime import date

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

STANDARD_URL = "https://www.combank.lk/rates-tariff"
SPECIAL_URL  = "https://www.combank.lk/personal-banking/term-deposits/special-100-days-200-days-300-days-400-days-500-days-fixed-deposit"

# FD rates in Sri Lanka are always in this range
FD_RATE_MIN = 1.0
FD_RATE_MAX = 20.0

# Currency-related words — if a tenure contains these, it's a forex product
CURRENCY_WORDS = {
    "usd", "gbp", "eur", "aud", "cad", "sgd", "chf", "jpy", "inr", "hkd",
    "nzd", "sek", "nok", "dkk", "aed", "cny", "hkd", "dollar", "pound",
    "euro", "franc", "yen", "yuan", "kroner", "krona", "rupee", "dirham",
    "foreign", "fcbu", "fcbu", "forex", "currency"
}

# Time keywords — valid FD tenures must contain one of these
TIME_UNITS = ["month", "year", "day", "week"]


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def _is_valid_tenure(text: str) -> bool:
    """Only accept time-based tenures, reject currency names."""
    t = _clean(text).lower()
    if not t:
        return False
    # Reject anything that mentions a currency
    if any(word in t for word in CURRENCY_WORDS):
        return False
    # Must contain a time unit
    if any(unit in t for unit in TIME_UNITS):
        return True
    # Or be a plain number (e.g. "3", "12")
    if re.match(r"^\d+$", t):
        return True
    return False


def _parse_fd_rate(value: str) -> float | None:
    """Parse a rate, accepting only values in the FD rate range (1–20%)."""
    cleaned = _clean(value).replace("%", "")
    range_match = re.match(r"([\d.]+)\s*[-–]\s*([\d.]+)", cleaned)
    if range_match:
        rate = float(range_match.group(2))
    else:
        try:
            rate = float(cleaned)
        except ValueError:
            return None
    return rate if FD_RATE_MIN <= rate <= FD_RATE_MAX else None


def _extract_tables(soup: BeautifulSoup, label: str = "") -> list[dict]:
    results = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            cell_texts = [_clean(c.get_text()) for c in cells]
            if len(cell_texts) < 2:
                continue

            # Skip header rows
            row_lower = " ".join(cell_texts).lower()
            if any(k in row_lower for k in ["tenure", "period", "interest rate", "p.a.", "maturity"]):
                if not any(k in row_lower for k in TIME_UNITS):
                    continue

            tenure = cell_texts[0]
            if not _is_valid_tenure(tenure):
                continue

            rate = None
            notes = label
            for i, val in enumerate(cell_texts[1:], 1):
                rate = _parse_fd_rate(val)
                if rate is not None:
                    extra = " | ".join(cell_texts[i+1:]) if i+1 < len(cell_texts) else ""
                    notes = f"{label} | {extra}".strip(" |") if extra else label
                    break

            if rate is not None:
                results.append({
                    "bank": "Commercial Bank",
                    "tenure": tenure,
                    "rate_percent": rate,
                    "notes": notes,
                    "scraped_date": str(date.today()),
                })
    return results


def _fetch_soup(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        print(f"[ComBank] Request failed for {url}: {e}")
        return None


def scrape() -> list[dict]:
    results = []

    # Standard LKR FDs
    soup = _fetch_soup(STANDARD_URL)
    if soup:
        standard = _extract_tables(soup, label="")
        results.extend(standard)
        print(f"[ComBank] Standard FDs: {len(standard)} entries")

    # Special term FDs (100/200/300/400/500 days)
    soup = _fetch_soup(SPECIAL_URL)
    if soup:
        special = _extract_tables(soup, label="Special FD")
        results.extend(special)
        print(f"[ComBank] Special FDs: {len(special)} entries")

    # Deduplicate by tenure
    seen = set()
    deduped = []
    for r in results:
        key = r["tenure"].lower().strip()
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    if not deduped:
        print("[ComBank] WARNING: No FD rate tables found.")
    else:
        print(f"[ComBank] Total unique entries: {len(deduped)}")

    return deduped


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
