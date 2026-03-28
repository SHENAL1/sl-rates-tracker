"""
Commercial Bank Sri Lanka - FD Rate Scraper
Page: https://www.combank.lk/rates-tariff
Strategy: Static HTML with rate tables. Uses requests + BeautifulSoup.
"""

import requests
from bs4 import BeautifulSoup
import re
from datetime import date

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

FD_URL = "https://www.combank.lk/rates-tariff"


def scrape() -> list[dict]:
    """
    Scrape Commercial Bank FD rates.
    Returns a list of dicts: [{tenure, rate_percent, notes}]
    """
    try:
        resp = requests.get(FD_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"[ComBank] Request failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    results = []

    # Find all tables on the page and look for FD/term deposit tables
    tables = soup.find_all("table")
    for table in tables:
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]

        # Look for tables that contain tenure/period and rate columns
        has_tenure = any(k in " ".join(headers) for k in ["tenure", "period", "term", "month", "days"])
        has_rate = any(k in " ".join(headers) for k in ["rate", "interest", "%", "p.a"])

        if not (has_tenure or has_rate):
            # Also check first row for column hints
            first_row = table.find("tr")
            if first_row:
                row_text = first_row.get_text(strip=True).lower()
                has_tenure = any(k in row_text for k in ["tenure", "period", "term", "month", "days"])
                has_rate = any(k in row_text for k in ["rate", "interest", "%", "p.a"])

        if not (has_tenure and has_rate):
            continue

        rows = table.find_all("tr")
        col_headers = []
        for row in rows:
            cells = row.find_all(["th", "td"])
            cell_texts = [c.get_text(strip=True) for c in cells]

            if not cell_texts or all(t == "" for t in cell_texts):
                continue

            # Detect header rows
            if row.find("th") or any(
                k in " ".join(cell_texts).lower()
                for k in ["tenure", "period", "term", "rate", "interest"]
            ):
                col_headers = cell_texts
                continue

            if len(cell_texts) >= 2:
                tenure = cell_texts[0]
                # Find the rate column — look for a percentage value
                rate = None
                notes = ""
                for i, val in enumerate(cell_texts[1:], 1):
                    cleaned = val.replace("%", "").strip()
                    try:
                        rate = float(cleaned)
                        notes = " | ".join(cell_texts[i+1:]) if i+1 < len(cell_texts) else ""
                        break
                    except ValueError:
                        continue

                if tenure and rate is not None:
                    results.append({
                        "bank": "Commercial Bank",
                        "tenure": tenure,
                        "rate_percent": rate,
                        "notes": notes,
                        "scraped_date": str(date.today()),
                    })

    if not results:
        print("[ComBank] WARNING: No FD rate tables found. Page structure may have changed.")
    else:
        print(f"[ComBank] Found {len(results)} rate entries.")

    return results


if __name__ == "__main__":
    import json
    data = scrape()
    print(json.dumps(data, indent=2))
