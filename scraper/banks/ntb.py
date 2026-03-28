"""
Nations Trust Bank (NTB) Sri Lanka - FD Rate Scraper
Page: https://www.ntb.lk/personal/deposits/fixed-deposits
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

# NTB publishes rates on their deposits/rates page
URLS = [
    "https://www.ntb.lk/personal/deposits/fixed-deposits",
    "https://www.ntb.lk/rates",
    "https://www.ntb.lk/interest-rates",
]

FD_KEYWORDS    = ["fixed deposit", "term deposit", "fd"]
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

    for heading in soup.find_all(["h1","h2","h3","h4","h5","strong","b"]):
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
                        "bank": "NTB",
                        "tenure": tenure,
                        "rate_percent": rate,
                        "notes": notes,
                        "scraped_date": str(date.today()),
                    })

    if not results:
        for table in soup.find_all("table"):
            if not any(k in table.get_text(" ").lower() for k in RATE_KEYWORDS):
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
                        "bank": "NTB",
                        "tenure": tenure,
                        "rate_percent": rate,
                        "notes": notes,
                        "scraped_date": str(date.today()),
                    })

    return results


def scrape() -> list[dict]:
    results = []

    # Try each URL with static fetch
    for url in URLS:
        if results:
            break
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            results = _extract_from_soup(soup)
            if results:
                print(f"[NTB] Got data from {url}")
        except Exception as e:
            print(f"[NTB] Static fetch failed for {url}: {e}")

    # Playwright fallback — try each URL
    if not results:
        print("[NTB] Trying Playwright...")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                for url in URLS:
                    if results:
                        break
                    try:
                        page = browser.new_page(user_agent=HEADERS["User-Agent"])
                        page.goto(url, wait_until="networkidle", timeout=30000)
                        page.wait_for_timeout(3000)
                        html = page.content()
                        page.close()
                        soup = BeautifulSoup(html, "lxml")
                        results = _extract_from_soup(soup)
                        if results:
                            print(f"[NTB] Playwright got data from {url}")
                    except Exception as e:
                        print(f"[NTB] Playwright failed for {url}: {e}")
                browser.close()
        except Exception as e:
            print(f"[NTB] Playwright error: {e}")

    if not results:
        print("[NTB] WARNING: No FD rate tables found.")
    else:
        print(f"[NTB] Found {len(results)} rate entries.")

    return results


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
