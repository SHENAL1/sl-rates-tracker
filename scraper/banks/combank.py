"""
Commercial Bank Sri Lanka - FD Rate Scraper
Pages scraped:
  - Standard FDs:  https://www.combank.lk/rates-tariff
  - Special FDs:   https://www.combank.lk/personal-banking/term-deposits/special-100-days-200-days-300-days-400-days-500-days-fixed-deposit
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

STANDARD_URL = "https://www.combank.lk/rates-tariff"
SPECIAL_URL  = "https://www.combank.lk/personal-banking/term-deposits/special-100-days-200-days-300-days-400-days-500-days-fixed-deposit"


def _parse_rate(value: str) -> float | None:
    cleaned = value.replace("%", "").strip()
    range_match = re.match(r"([\d.]+)\s*[-–]\s*([\d.]+)", cleaned)
    if range_match:
        return float(range_match.group(2))
    try:
        v = float(cleaned)
        return v if v > 0 else None
    except ValueError:
        return None


def _extract_tables(soup: BeautifulSoup, label: str = "") -> list[dict]:
    results = []
    tables = soup.find_all("table")

    for table in tables:
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        first_row = table.find("tr")
        first_row_text = first_row.get_text(strip=True).lower() if first_row else ""

        has_tenure = any(k in " ".join(headers) + first_row_text
                         for k in ["tenure", "period", "term", "month", "days"])
        has_rate   = any(k in " ".join(headers) + first_row_text
                         for k in ["rate", "interest", "%", "p.a"])

        if not (has_tenure and has_rate):
            continue

        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            cell_texts = [c.get_text(strip=True) for c in cells]

            if not cell_texts or all(t == "" for t in cell_texts):
                continue

            row_lower = " ".join(cell_texts).lower()
            if any(k in row_lower for k in ["tenure", "period", "term", "rate", "interest"]):
                continue  # skip header rows

            if len(cell_texts) >= 2:
                tenure = cell_texts[0]
                rate = None
                notes = label  # tag special vs standard
                for i, val in enumerate(cell_texts[1:], 1):
                    rate = _parse_rate(val)
                    if rate is not None:
                        extra = " | ".join(cell_texts[i+1:]) if i+1 < len(cell_texts) else ""
                        notes = f"{label} | {extra}".strip(" |") if extra else label
                        break

                if tenure and rate is not None:
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
    """
    Scrape Commercial Bank standard + special FD rates.
    Returns a list of dicts.
    """
    results = []

    # ── Standard FDs ──────────────────────────────────────────────
    soup = _fetch_soup(STANDARD_URL)
    if soup:
        standard = _extract_tables(soup, label="")
        results.extend(standard)
        print(f"[ComBank] Standard FDs: {len(standard)} entries")

    # ── Special term FDs (100/200/300/400/500 days) ───────────────
    soup = _fetch_soup(SPECIAL_URL)
    if soup:
        special = _extract_tables(soup, label="Special FD")
        results.extend(special)
        print(f"[ComBank] Special FDs: {len(special)} entries")

    if not results:
        print("[ComBank] WARNING: No FD rate tables found. Page structure may have changed.")
    else:
        # Deduplicate by tenure (standard takes priority over special if duplicate)
        seen = set()
        deduped = []
        for r in results:
            key = r["tenure"].lower().strip()
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        results = deduped
        print(f"[ComBank] Total unique entries: {len(results)}")

    return results


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
