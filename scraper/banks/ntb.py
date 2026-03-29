"""
Nations Trust Bank (NTB) Sri Lanka - FD Rate Scraper
URL: https://www.nationstrust.com/deposit-rates

NOTE: The NTB deposit-rates page uses a TRANSPOSED table layout:
  - Column headers = tenures (1 month, 3 month, 6 month, 12 month, 24 month, 36 month, 48 month, 60 month)
  - Row headers   = currency + payment type (e.g. "LKR Interest Paid at Maturity")

We only extract LKR rows and pivot them to one record per (tenure, rate_type).
"""

import re
import requests
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

URL = "https://www.nationstrust.com/deposit-rates"

FD_RATE_MIN = 1.0
FD_RATE_MAX = 20.0

# Known tenure column headers from the NTB page (months)
TENURE_MONTHS = {
    "1 month": "1 Month",
    "3 month": "3 Months",
    "6 month": "6 Months",
    "12 month": "12 Months",
    "24 month": "24 Months",
    "36 month": "36 Months",
    "48 month": "48 Months",
    "60 month": "60 Months",
}

PAYMENT_LABELS = {
    "maturity": "At Maturity",
    "monthly":  "Monthly",
    "annually": "Annually",
}


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def _parse_rate(value: str) -> float | None:
    """Extract rate from values like '8.00 (AER 8.00)' or '8.00'."""
    cleaned = _clean(value)
    # Take just the first number (ignore AER)
    m = re.match(r"([\d.]+)", cleaned)
    if not m:
        return None
    try:
        rate = float(m.group(1))
    except ValueError:
        return None
    return rate if FD_RATE_MIN <= rate <= FD_RATE_MAX else None


def _extract_from_soup(soup: BeautifulSoup) -> list[dict]:
    results = []
    today = str(date.today())

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        # Read column headers — look for tenure keywords
        header_row = rows[0]
        headers = [_clean(th.get_text()) for th in header_row.find_all(["th", "td"])]

        # Map column index → tenure label
        col_to_tenure = {}
        for idx, h in enumerate(headers):
            hl = h.lower().strip()
            for key, label in TENURE_MONTHS.items():
                if key in hl:
                    col_to_tenure[idx] = label
                    break

        if not col_to_tenure:
            continue  # Not a tenure-based table

        # Process data rows
        for row in rows[1:]:
            cells = [_clean(td.get_text()) for td in row.find_all(["th", "td"])]
            if not cells:
                continue

            row_label = cells[0].lower()

            # Only LKR rows
            if "lkr" not in row_label and "rupee" not in row_label:
                continue

            # Determine payment type
            notes = ""
            tenure_suffix = ""
            for key, label in PAYMENT_LABELS.items():
                if key in row_label:
                    notes = f"LKR - {label}"
                    if label != "At Maturity":
                        tenure_suffix = f" ({label})"
                    break

            if not notes:
                continue  # Skip unrecognised rows

            # Extract rate for each tenure column
            for col_idx, tenure in col_to_tenure.items():
                if col_idx >= len(cells):
                    continue
                rate = _parse_rate(cells[col_idx])
                if rate is None:
                    continue
                results.append({
                    "bank": "NTB",
                    "tenure": tenure + tenure_suffix,
                    "rate_percent": rate,
                    "notes": notes,
                    "scraped_date": today,
                })

    return results


def scrape() -> list[dict]:
    results = []

    # Try static fetch
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        results = _extract_from_soup(soup)
    except Exception as e:
        print(f"[NTB] Static fetch failed: {e}")

    # Playwright fallback
    if not results:
        print("[NTB] Trying Playwright...")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=HEADERS["User-Agent"])
                page.goto(URL, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(3000)
                html = page.content()
                browser.close()
            soup = BeautifulSoup(html, "lxml")
            results = _extract_from_soup(soup)
        except Exception as e:
            print(f"[NTB] Playwright failed: {e}")

    # Deduplicate by (tenure, notes)
    seen = set()
    deduped = []
    for r in results:
        key = (r["tenure"].lower(), r["notes"].lower())
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    if not deduped:
        print("[NTB] WARNING: No FD rate tables found.")
    else:
        print(f"[NTB] Found {len(deduped)} rate entries.")

    return deduped


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
