"""
National Savings Bank (NSB) Sri Lanka - FD Rate Scraper
Page: https://www.nsb.lk/interest-rates/

Filtering rules (strict):
  1. Tenure must START with a digit  (e.g. "1 Month", "12 Months", "365 Days")
  2. Tenure must contain a time unit  (month / year / day / week)
  3. Rate must be between 1% and 20%
  4. Tenure must not contain currency / loan / non-FD keywords
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

FD_RATE_MIN = 1.0
FD_RATE_MAX = 20.0

TIME_UNITS = ["month", "year", "day", "week"]

BAD_TENURE_WORDS = {
    "loan", "loans", "lending", "leasing", "overdraft", "agri",
    "platinum", "apr", "treasury", "t-bill", "gold loan",
    "saving", "credit", "advance",
    "usd", "gbp", "eur", "aud", "dollar", "pound", "euro", "franc",
    "yen", "yuan", "foreign", "fcbu", "forex", "currency",
}

FD_SECTION_KEYWORDS = ["fixed deposit", "term deposit", "fd rate", "fixed term"]
NON_FD_SECTION_KEYWORDS = [
    "saving", "lending", "loan", "leasing", "overdraft", "forex",
    "exchange rate", "treasury", "current account", "pawning",
]


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def _is_valid_tenure(text: str) -> bool:
    t = _clean(text)
    if not t:
        return False
    if not re.match(r"^\d", t):          # must start with a digit
        return False
    tl = t.lower()
    if not any(u in tl for u in TIME_UNITS):   # must contain a time unit
        return False
    if any(w in tl for w in BAD_TENURE_WORDS): # no loan/currency words
        return False
    return True


def _parse_fd_rate(value: str) -> float | None:
    value = _clean(value).replace("%", "")
    range_match = re.match(r"([\d.]+)\s*[-–]\s*([\d.]+)", value)
    if range_match:
        rate = float(range_match.group(2))
    else:
        try:
            rate = float(value)
        except ValueError:
            return None
    return rate if FD_RATE_MIN <= rate <= FD_RATE_MAX else None


def _process_table(table) -> list[dict]:
    results = []
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        cell_texts = [_clean(c.get_text()) for c in cells]
        if len(cell_texts) < 2:
            continue
        tenure = cell_texts[0]
        if not _is_valid_tenure(tenure):
            continue
        rate = None
        notes = ""
        for i, val in enumerate(cell_texts[1:], 1):
            rate = _parse_fd_rate(val)
            if rate is not None:
                notes = " | ".join(cell_texts[i+1:]) if i+1 < len(cell_texts) else ""
                break
        if rate is not None:
            results.append({
                "bank": "NSB",
                "tenure": tenure,
                "rate_percent": rate,
                "notes": notes,
                "scraped_date": str(date.today()),
            })
    return results


def _extract_from_soup(soup: BeautifulSoup) -> list[dict]:
    results = []

    # Strategy 1: only tables under FD section headings
    inside_fd = False
    for el in soup.find_all(["h1","h2","h3","h4","h5","h6","p","div","section","table"]):
        text = _clean(el.get_text())
        if el.name != "table" and len(text) < 120:
            tl = text.lower()
            if any(k in tl for k in FD_SECTION_KEYWORDS):
                inside_fd = True
                continue
            elif any(k in tl for k in NON_FD_SECTION_KEYWORDS) and inside_fd:
                inside_fd = False
                continue
        if el.name == "table" and inside_fd:
            results.extend(_process_table(el))
            inside_fd = False   # one table per section heading

    # Strategy 2: fallback — scan all tables with strict filtering
    if not results:
        for table in soup.find_all("table"):
            results.extend(_process_table(table))

    return results


def scrape() -> list[dict]:
    results = []

    # Try static HTML first
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        results = _extract_from_soup(soup)
    except Exception as e:
        print(f"[NSB] Static fetch failed: {e}")

    # Playwright fallback (for JS-rendered pages)
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

    # Deduplicate
    seen = {}
    for r in results:
        key = re.sub(r"\s+", " ", r["tenure"].lower().strip())
        if key not in seen or r["rate_percent"] > seen[key]["rate_percent"]:
            seen[key] = r
    results = list(seen.values())

    if not results:
        print("[NSB] WARNING: No FD rate tables found.")
    else:
        print(f"[NSB] Found {len(results)} rate entries.")

    return results


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
