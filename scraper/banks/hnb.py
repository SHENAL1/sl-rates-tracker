"""
Hatton National Bank (HNB) Sri Lanka - FD Rate Scraper
Page: https://www.hnb.lk/interest-rates
Strategy: Tries static HTML first (requests + BS4). Falls back to Playwright if needed.
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

URL = "https://www.hnb.lk/interest-rates"

# Keywords that indicate a table is about Fixed Deposits
FD_KEYWORDS = ["fixed deposit", "term deposit", "fd rate", "fixed rate"]
TENURE_KEYWORDS = ["tenure", "period", "term", "month", "days", "year"]
RATE_KEYWORDS = ["rate", "interest", "%", "p.a", "per annum"]


def _parse_rate(value: str) -> float | None:
    """Extract a numeric rate from a string like '8.50%' or '8.00 - 9.00'."""
    value = value.replace("%", "").strip()
    # Handle range — take the max
    range_match = re.match(r"([\d.]+)\s*[-–]\s*([\d.]+)", value)
    if range_match:
        return float(range_match.group(2))
    try:
        return float(value)
    except ValueError:
        return None


def _extract_rates_from_soup(soup: BeautifulSoup) -> list[dict]:
    results = []

    # Strategy 1: Look for section headings that mention "Fixed Deposit"
    # then grab the next table
    fd_sections = []
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "strong", "b"]):
        heading_text = heading.get_text(strip=True).lower()
        if any(k in heading_text for k in FD_KEYWORDS):
            fd_sections.append(heading)

    for section in fd_sections:
        # Find the next sibling table
        sibling = section.find_next("table")
        if sibling:
            rows = sibling.find_all("tr")
            col_headers = []
            for row in rows:
                cells = row.find_all(["th", "td"])
                cell_texts = [c.get_text(strip=True) for c in cells]
                if not cell_texts:
                    continue

                if row.find("th"):
                    col_headers = cell_texts
                    continue

                if len(cell_texts) >= 2:
                    tenure = cell_texts[0]
                    rate = None
                    notes = ""
                    for i, val in enumerate(cell_texts[1:], 1):
                        rate = _parse_rate(val)
                        if rate is not None and rate > 0:
                            notes = " | ".join(cell_texts[i+1:]) if i+1 < len(cell_texts) else ""
                            break

                    if tenure and rate is not None:
                        results.append({
                            "bank": "HNB",
                            "tenure": tenure,
                            "rate_percent": rate,
                            "notes": notes,
                            "scraped_date": str(date.today()),
                        })

    # Strategy 2: If no section found, scan all tables for tenure + rate columns
    if not results:
        for table in soup.find_all("table"):
            all_text = table.get_text(" ").lower()
            if not any(k in all_text for k in RATE_KEYWORDS):
                continue

            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["th", "td"])
                cell_texts = [c.get_text(strip=True) for c in cells]
                if len(cell_texts) < 2:
                    continue

                row_text = " ".join(cell_texts).lower()
                if any(k in row_text for k in ["tenure", "period", "interest", "rate"]):
                    continue  # skip header row

                tenure = cell_texts[0]
                rate = None
                notes = ""
                for i, val in enumerate(cell_texts[1:], 1):
                    rate = _parse_rate(val)
                    if rate is not None and rate > 0:
                        notes = " | ".join(cell_texts[i+1:]) if i+1 < len(cell_texts) else ""
                        break

                if tenure and rate is not None:
                    results.append({
                        "bank": "HNB",
                        "tenure": tenure,
                        "rate_percent": rate,
                        "notes": notes,
                        "scraped_date": str(date.today()),
                    })

    return results


def scrape() -> list[dict]:
    """
    Scrape HNB FD rates.
    Returns a list of dicts: [{tenure, rate_percent, notes}]
    """
    # First try: plain HTTP request (fast, works if page is server-rendered)
    results = []
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        results = _extract_rates_from_soup(soup)
    except Exception as e:
        print(f"[HNB] Static fetch failed: {e}")

    # Second try: Playwright if page is JS-rendered
    if not results:
        print("[HNB] Trying with Playwright (JS rendering)...")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=HEADERS["User-Agent"])
                page.goto(URL, wait_until="networkidle", timeout=30000)
                page.wait_for_selector("table", timeout=15000)
                html = page.content()
                browser.close()

            soup = BeautifulSoup(html, "lxml")
            results = _extract_rates_from_soup(soup)
        except Exception as e:
            print(f"[HNB] Playwright fetch also failed: {e}")

    if not results:
        print("[HNB] WARNING: No FD rate tables found. Page structure may have changed.")
    else:
        print(f"[HNB] Found {len(results)} rate entries.")

    return results


if __name__ == "__main__":
    import json
    data = scrape()
    print(json.dumps(data, indent=2))
