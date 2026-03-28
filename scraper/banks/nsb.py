"""
National Savings Bank (NSB) Sri Lanka - FD Rate Scraper
Page: https://www.nsb.lk/interest-rates/
Strategy: Tries static HTML first, falls back to Playwright.
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

URL = "https://www.nsb.lk/interest-rates/"

FD_KEYWORDS    = ["fixed deposit", "term deposit", "fd", "fixed rate"]
TENURE_KEYWORDS = ["tenure", "period", "term", "month", "days", "year"]
RATE_KEYWORDS  = ["rate", "interest", "%", "p.a", "per annum"]


def _parse_rate(value: str) -> float | None:
    value = value.replace("%", "").strip()
    range_match = re.match(r"([\d.]+)\s*[-–]\s*([\d.]+)", value)
    if range_match:
        return float(range_match.group(2))
    try:
        v = float(value)
        return v if v > 0 else None
    except ValueError:
        return None


def _extract_from_soup(soup: BeautifulSoup) -> list[dict]:
    results = []

    # Strategy 1: look for headings/sections that mention FD, then grab next table
    for heading in soup.find_all(["h1","h2","h3","h4","h5","strong","b","p"]):
        heading_text = heading.get_text(strip=True).lower()
        if any(k in heading_text for k in FD_KEYWORDS):
            table = heading.find_next("table")
            if not table:
                continue
            for row in table.find_all("tr"):
                cells = row.find_all(["td","th"])
                cell_texts = [c.get_text(strip=True) for c in cells]
                if len(cell_texts) < 2:
                    continue
                row_text = " ".join(cell_texts).lower()
                if any(k in row_text for k in ["tenure","period","term","rate","interest","month"]):
                    continue  # skip header
                tenure = cell_texts[0]
                rate = None
                notes = ""
                for i, val in enumerate(cell_texts[1:], 1):
                    rate = _parse_rate(val)
                    if rate is not None:
                        notes = " | ".join(cell_texts[i+1:]) if i+1 < len(cell_texts) else ""
                        break
                if tenure and rate is not None:
                    results.append({
                        "bank": "NSB",
                        "tenure": tenure,
                        "rate_percent": rate,
                        "notes": notes,
                        "scraped_date": str(date.today()),
                    })

    # Strategy 2: scan all tables for rate data
    if not results:
        for table in soup.find_all("table"):
            table_text = table.get_text(" ").lower()
            if not any(k in table_text for k in RATE_KEYWORDS):
                continue
            for row in table.find_all("tr"):
                cells = row.find_all(["td","th"])
                cell_texts = [c.get_text(strip=True) for c in cells]
                if len(cell_texts) < 2:
                    continue
                row_text = " ".join(cell_texts).lower()
                if any(k in row_text for k in ["tenure","period","term","rate","interest"]):
                    continue
                tenure = cell_texts[0]
                rate = None
                notes = ""
                for i, val in enumerate(cell_texts[1:], 1):
                    rate = _parse_rate(val)
                    if rate is not None:
                        notes = " | ".join(cell_texts[i+1:]) if i+1 < len(cell_texts) else ""
                        break
                if tenure and rate is not None:
                    results.append({
                        "bank": "NSB",
                        "tenure": tenure,
                        "rate_percent": rate,
                        "notes": notes,
                        "scraped_date": str(date.today()),
                    })

    return results


def scrape() -> list[dict]:
    results = []

    # Try static first
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        results = _extract_from_soup(soup)
    except Exception as e:
        print(f"[NSB] Static fetch failed: {e}")

    # Playwright fallback
    if not results:
        print("[NSB] Trying Playwright...")
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
            print(f"[NSB] Playwright failed: {e}")

    if not results:
        print("[NSB] WARNING: No FD rate tables found.")
    else:
        print(f"[NSB] Found {len(results)} rate entries.")

    return results


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
