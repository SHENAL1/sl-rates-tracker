"""
Sampath Bank Sri Lanka - FD Rate Scraper
Page: https://www.sampath.lk/rates-and-charges?activeTab=interest-rates-local
Strategy: JS-rendered page — uses Playwright to fully render before scraping.

NOTE: The Sampath rates page has BOTH exchange rates and FD interest rates.
We must be careful to only pick up the FD/deposit interest rate tables,
not the forex exchange rate tables (which have currency codes as "tenures").
"""

import re
from datetime import date

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[Sampath] Playwright not installed.")

URL = "https://www.sampath.lk/rates-and-charges?activeTab=interest-rates-local"

# Currency codes — if a row's tenure looks like this, it's an exchange rate table
CURRENCY_CODES = {
    "USD", "GBP", "EUR", "AUD", "CAD", "SGD", "CHF", "JPY", "INR", "HKD",
    "NZD", "SEK", "NOK", "DKK", "AED", "SAR", "MYR", "THB", "QAR", "KWD",
    "BHD", "OMR", "PKR", "CNY", "ZAR"
}

# FD rates are always in this range (percent p.a.)
MIN_RATE = 1.0
MAX_RATE = 25.0

# Keywords that indicate an FD/deposit interest rate section
FD_SECTION_KEYWORDS = [
    "fixed deposit", "term deposit", "fd", "deposit rate",
    "savings", "interest rate", "local currency", "lkr deposit"
]

# Keywords that indicate an exchange rate section — skip these
FOREX_SECTION_KEYWORDS = [
    "exchange rate", "forex", "foreign currency", "buying", "selling",
    "tt buying", "tt selling", "telegraphic"
]


def _is_valid_tenure(text: str) -> bool:
    """Return True if text looks like a deposit tenure (not a currency code)."""
    t = text.strip().upper()
    if t in CURRENCY_CODES:
        return False
    # Must contain a time unit or number
    if any(k in text.lower() for k in ["month", "year", "day", "week"]):
        return True
    # Could be just a number like "3", "6", "12"
    if re.match(r"^\d+$", t):
        return True
    return False


def _is_valid_rate(value: str) -> float | None:
    """Return rate float if it looks like an interest rate, else None."""
    cleaned = value.replace("%", "").strip()
    # Handle range — take the higher value
    range_match = re.match(r"([\d.]+)\s*[-–]\s*([\d.]+)", cleaned)
    if range_match:
        rate = float(range_match.group(2))
    else:
        try:
            rate = float(cleaned)
        except ValueError:
            return None

    # Interest rates are between 1% and 25% — exchange rates are much higher
    if MIN_RATE <= rate <= MAX_RATE:
        return rate
    return None


def _is_forex_section(heading_text: str) -> bool:
    text = heading_text.lower()
    return any(k in text for k in FOREX_SECTION_KEYWORDS)


def _is_fd_section(heading_text: str) -> bool:
    text = heading_text.lower()
    return any(k in text for k in FD_SECTION_KEYWORDS)


def scrape() -> list[dict]:
    if not PLAYWRIGHT_AVAILABLE:
        return []

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )

        try:
            page.goto(URL, wait_until="networkidle", timeout=30000)

            # Try to activate the interest rates tab
            try:
                for selector in [
                    "text=Interest Rates",
                    "[data-tab='interest-rates-local']",
                    "a[href*='interest-rates-local']",
                ]:
                    try:
                        el = page.locator(selector).first
                        if el.is_visible(timeout=2000):
                            el.click()
                            page.wait_for_timeout(2000)
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            page.wait_for_selector("table", timeout=15000)
            page.wait_for_timeout(1000)

            # Get all headings and tables together — we need to know which
            # section each table belongs to
            sections = page.evaluate("""
                () => {
                    const results = [];
                    // Walk DOM and collect headings + tables in order
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_ELEMENT,
                        null
                    );
                    let currentHeading = '';
                    let node;
                    while (node = walker.nextNode()) {
                        const tag = node.tagName.toLowerCase();
                        if (['h1','h2','h3','h4','h5','strong','b'].includes(tag)) {
                            const txt = node.innerText?.trim();
                            if (txt && txt.length < 200) currentHeading = txt;
                        }
                        if (tag === 'table') {
                            const rows = [];
                            node.querySelectorAll('tr').forEach(tr => {
                                const cells = [];
                                tr.querySelectorAll('th,td').forEach(td => {
                                    cells.push(td.innerText?.trim() || '');
                                });
                                if (cells.length > 0) rows.push(cells);
                            });
                            results.push({ heading: currentHeading, rows });
                        }
                    }
                    return results;
                }
            """)

            for section in sections:
                heading = section.get("heading", "")
                rows = section.get("rows", [])

                # Skip if the section heading says it's a forex/exchange section
                if _is_forex_section(heading):
                    continue

                # Process each row
                for row in rows:
                    if len(row) < 2:
                        continue

                    # Skip header rows
                    row_text = " ".join(row).lower()
                    if any(k in row_text for k in ["tenure", "period", "term", "rate", "interest", "maturity"]):
                        if not any(k in row_text for k in ["month", "year", "day"]):
                            continue

                    # Clean whitespace (Sampath page has lots of \n and spaces in cells)
                    tenure = " ".join(row[0].split()).strip()

                    # Skip if tenure looks like a currency code
                    if not tenure or tenure.upper() in CURRENCY_CODES:
                        continue

                    # Find the rate — must be a valid interest rate (1–25%)
                    rate = None
                    notes = ""
                    for i, val in enumerate(row[1:], 1):
                        rate = _is_valid_rate(val)
                        if rate is not None:
                            remaining = [row[j] for j in range(i+1, len(row)) if row[j].strip()]
                            notes = " | ".join(remaining) if remaining else ""
                            break

                    if tenure and rate is not None:
                        results.append({
                            "bank": "Sampath Bank",
                            "tenure": tenure,
                            "rate_percent": rate,
                            "notes": notes,
                            "scraped_date": str(date.today()),
                        })

        except Exception as e:
            print(f"[Sampath] Scraping error: {e}")
        finally:
            browser.close()

    # Remove duplicates
    seen = set()
    deduped = []
    for r in results:
        key = (r["tenure"].lower().strip(), r["rate_percent"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    if not deduped:
        print("[Sampath] WARNING: No FD rate tables found.")
    else:
        print(f"[Sampath] Found {len(deduped)} rate entries.")

    return deduped


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
