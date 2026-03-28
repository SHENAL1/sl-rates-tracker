"""
Sampath Bank Sri Lanka - FD Rate Scraper
Page: https://www.sampath.lk/rates-and-charges?activeTab=interest-rates-local

The Sampath rates page contains MULTIPLE tables:
  - Foreign exchange rates (currency codes like USD, GBP — NOT what we want)
  - Fixed deposit interest rates (month/year tenures — THIS is what we want)

Strict filtering rules:
  1. Tenure MUST contain a time unit (month/year/day/week) or be a plain number
  2. Rate MUST be between 1.0% and 20.0% (FD rates in SL are never outside this)
  3. Deduplicate by (tenure, rate) pair
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

# Sri Lankan FD rates are always within this range
FD_RATE_MIN = 1.0
FD_RATE_MAX = 20.0

# Time keywords that a valid FD tenure must contain
TIME_UNITS = ["month", "year", "day", "week"]


def _clean(text: str) -> str:
    """Normalize whitespace in a cell value."""
    return " ".join(text.split()).strip()


def _is_valid_tenure(text: str) -> bool:
    """Return True only if text looks like a deposit tenure (not a currency code)."""
    t = _clean(text).lower()
    if not t:
        return False
    # Must contain a time unit
    if any(unit in t for unit in TIME_UNITS):
        return True
    # Or be a plain number like "3", "12"
    if re.match(r"^\d+$", t):
        return True
    return False


def _parse_fd_rate(value: str) -> float | None:
    """
    Parse a rate value. Returns float ONLY if it's in the valid FD rate range.
    Exchange rates (e.g. 312 LKR/USD) will be rejected since they're > 20.
    """
    cleaned = _clean(value).replace("%", "")
    # Handle ranges like "7.50 - 8.00" — take the higher value
    range_match = re.match(r"([\d.]+)\s*[-–]\s*([\d.]+)", cleaned)
    if range_match:
        rate = float(range_match.group(2))
    else:
        try:
            rate = float(cleaned)
        except ValueError:
            return None

    if FD_RATE_MIN <= rate <= FD_RATE_MAX:
        return rate
    return None


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
            page.wait_for_timeout(2000)

            # Try to click into the interest rates tab
            for selector in [
                "text=Interest Rates (Local)",
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

            page.wait_for_selector("table", timeout=15000)

            # Extract all table data
            all_tables = page.evaluate("""
                () => {
                    const tables = [];
                    document.querySelectorAll('table').forEach(table => {
                        const rows = [];
                        table.querySelectorAll('tr').forEach(tr => {
                            const cells = [];
                            tr.querySelectorAll('th, td').forEach(td => {
                                cells.push(td.innerText || '');
                            });
                            rows.push(cells);
                        });
                        tables.push(rows);
                    });
                    return tables;
                }
            """)

            for table_rows in all_tables:
                for row in table_rows:
                    if len(row) < 2:
                        continue

                    tenure = _clean(row[0])

                    # STRICT: only accept valid time-based tenures
                    if not _is_valid_tenure(tenure):
                        continue

                    # Find a valid FD rate in the remaining cells
                    rate = None
                    notes = ""
                    for i, val in enumerate(row[1:], 1):
                        rate = _parse_fd_rate(val)
                        if rate is not None:
                            remaining = [_clean(row[j]) for j in range(i+1, len(row)) if _clean(row[j])]
                            notes = " | ".join(remaining) if remaining else ""
                            break

                    if rate is not None:
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

    # Deduplicate by (tenure, rate) pair
    seen = set()
    deduped = []
    for r in results:
        key = (r["tenure"].lower(), r["rate_percent"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    if not deduped:
        print("[Sampath] WARNING: No FD rate tables found.")
    else:
        print(f"[Sampath] Found {len(deduped)} entries.")

    return deduped


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
