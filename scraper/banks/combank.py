"""
Commercial Bank Sri Lanka - FD Rate Scraper
Pages scraped:
  - Standard LKR FDs:  https://www.combank.lk/rates-tariff
  - Special FDs:       https://www.combank.lk/personal-banking/term-deposits/special-100-days-...

Strategy:
  - For the rates-tariff page: ONLY read tables that appear under a
    "Fixed Deposit" or "Term Deposit" section heading.
    This avoids pulling in loan rates, savings rates, gold loan rates, etc.
  - For the special FD page: read all tables (page is exclusively about special FDs).

Filtering rules (double-safety):
  1. Tenure must start with a digit (e.g. "1 Month", "100 Days") — not "Short Term Gold Loans..."
  2. Tenure must contain a time unit (month/year/day/week)
  3. Rate must be between 1% and 20%
  4. Tenure must not contain currency or loan keywords
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

# Headings that signal an FD section on the rates page
FD_SECTION_KEYWORDS = [
    "fixed deposit", "term deposit", "fd rate",
    "fixed term", "time deposit"
]

# Headings that signal a NON-FD section (stop reading here)
NON_FD_SECTION_KEYWORDS = [
    "saving", "lending", "loan", "leasing", "overdraft", "credit",
    "forex", "foreign", "exchange rate", "treasury", "bill",
    "insurance", "pawning", "current account"
]

# Words in a tenure that disqualify it as a real FD tenure
BAD_TENURE_WORDS = {
    "loan", "loans", "lending", "leasing", "overdraft",
    "agri", "platinum", "udara", "apr", "treasury", "t-bill",
    "gold loan", "week's rate", "weekly rate", "reward",
    "credit", "advance", "saving",
    "usd", "gbp", "eur", "aud", "cad", "sgd", "chf", "jpy",
    "dollar", "pound", "euro", "franc", "yen", "yuan",
    "foreign", "fcbu", "forex", "currency",
}

# Tenure must have a time unit
TIME_UNITS = ["month", "year", "day", "week"]


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def _is_valid_tenure(text: str) -> bool:
    """
    Returns True only for genuine FD tenures.
    - Must start with a digit (e.g. "1 Month", "24 Months", "100 Days")
    - Must contain a time unit
    - Must not contain bad words (loan/currency terms)
    """
    t = _clean(text)
    if not t:
        return False
    # Must start with a digit
    if not re.match(r"^\d", t):
        return False
    tl = t.lower()
    # Must contain a time unit
    if not any(unit in tl for unit in TIME_UNITS):
        return False
    # Must not contain disqualifying words
    if any(word in tl for word in BAD_TENURE_WORDS):
        return False
    return True


def _parse_fd_rate(value: str) -> float | None:
    """Parse a rate, accepting only values in the valid FD rate range (1–20%)."""
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


def _is_fd_heading(text: str) -> bool:
    t = text.lower().strip()
    return any(k in t for k in FD_SECTION_KEYWORDS)


def _is_non_fd_heading(text: str) -> bool:
    t = text.lower().strip()
    return any(k in t for k in NON_FD_SECTION_KEYWORDS)


def _process_table(table, label: str = "") -> list[dict]:
    """Extract valid FD rates from a single BeautifulSoup table element."""
    results = []
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"])
        cell_texts = [_clean(c.get_text()) for c in cells]
        if len(cell_texts) < 2:
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


def _extract_fd_sections(soup: BeautifulSoup, label: str = "") -> list[dict]:
    """
    Walk the document looking for headings that say "Fixed Deposit" or "Term Deposit".
    Only process the table that immediately follows such a heading.
    Stop at the next non-FD section heading.
    """
    results = []
    heading_tags = ["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"]
    inside_fd_section = False

    # Collect all block-level elements in order
    for el in soup.find_all(["h1","h2","h3","h4","h5","h6","p","div","section","table"]):
        tag = el.name

        if tag in heading_tags or tag in ["p", "div", "section"]:
            text = _clean(el.get_text())
            # Only consider short-ish text as a section heading
            if len(text) < 120:
                if _is_fd_heading(text):
                    inside_fd_section = True
                    continue
                elif _is_non_fd_heading(text) and inside_fd_section:
                    # Exiting the FD section
                    inside_fd_section = False
                    continue

        if tag == "table" and inside_fd_section:
            rows = _process_table(el, label)
            results.extend(rows)
            # Only read the first table per section (stop after one table per heading)
            inside_fd_section = False

    # Fallback: if section detection found nothing, scan all tables with strict filters
    if not results:
        print(f"[ComBank] Section detection found nothing ({label}), falling back to all-tables scan.")
        for table in soup.find_all("table"):
            results.extend(_process_table(table, label))

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

    # Standard LKR FDs — section-aware extraction
    soup = _fetch_soup(STANDARD_URL)
    if soup:
        standard = _extract_fd_sections(soup, label="")
        results.extend(standard)
        print(f"[ComBank] Standard FDs: {len(standard)} entries")

    # Special term FDs (75/100/200/300/400/500 days) — whole page is FD content
    soup = _fetch_soup(SPECIAL_URL)
    if soup:
        special = []
        for table in soup.find_all("table"):
            special.extend(_process_table(table, label="Special FD"))
        results.extend(special)
        print(f"[ComBank] Special FDs: {len(special)} entries")

    # Deduplicate by (tenure normalised, rate) — keep highest rate for same tenure
    seen = {}
    for r in results:
        key = re.sub(r"\s+", " ", r["tenure"].lower().strip())
        if key not in seen or r["rate_percent"] > seen[key]["rate_percent"]:
            seen[key] = r

    deduped = list(seen.values())

    if not deduped:
        print("[ComBank] WARNING: No FD rate tables found.")
    else:
        print(f"[ComBank] Total unique entries: {len(deduped)}")

    return deduped


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
