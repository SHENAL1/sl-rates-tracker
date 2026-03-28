"""
Sampath Bank Sri Lanka - FD Rate Scraper
Page: https://www.sampath.lk/rates-and-charges?activeTab=interest-rates-local
Strategy: JS-rendered page — uses Playwright to fully render before scraping.
"""

import re
from datetime import date

# Playwright is used because Sampath's site renders rates via JavaScript
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[Sampath] Playwright not installed. Run: pip install playwright && playwright install chromium")


URL = "https://www.sampath.lk/rates-and-charges?activeTab=interest-rates-local"


def scrape() -> list[dict]:
    """
    Scrape Sampath Bank FD rates using a headless browser.
    Returns a list of dicts: [{tenure, rate_percent, notes}]
    """
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

            # Click the "Interest Rates (Local)" tab if not already active
            try:
                tab = page.locator("text=Interest Rates", exact=False).first
                tab.click(timeout=5000)
                page.wait_for_timeout(2000)
            except Exception:
                pass  # Tab might already be active

            # Wait for rate tables to appear
            page.wait_for_selector("table", timeout=15000)

            # Get all tables
            tables = page.query_selector_all("table")

            for table in tables:
                rows = table.query_selector_all("tr")
                col_headers = []

                for row in rows:
                    cells = row.query_selector_all("th, td")
                    cell_texts = [c.inner_text().strip() for c in cells]

                    if not cell_texts or all(t == "" for t in cell_texts):
                        continue

                    row_text_lower = " ".join(cell_texts).lower()

                    # Detect header rows
                    if any(k in row_text_lower for k in ["tenure", "period", "term", "rate", "interest", "month", "days"]):
                        if row.query_selector("th"):
                            col_headers = cell_texts
                            continue

                    if len(cell_texts) >= 2:
                        tenure = cell_texts[0]
                        rate = None
                        notes = ""

                        for i, val in enumerate(cell_texts[1:], 1):
                            cleaned = val.replace("%", "").strip()
                            # Handle ranges like "8.00 - 9.00" — take the higher value
                            range_match = re.match(r"([\d.]+)\s*[-–]\s*([\d.]+)", cleaned)
                            if range_match:
                                rate = float(range_match.group(2))
                                notes = f"Range: {val}"
                                break
                            try:
                                rate = float(cleaned)
                                notes = " | ".join(cell_texts[i+1:]) if i+1 < len(cell_texts) else ""
                                break
                            except ValueError:
                                continue

                        if tenure and rate is not None and rate > 0:
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

    if not results:
        print("[Sampath] WARNING: No FD rate tables found. Page structure may have changed.")
    else:
        print(f"[Sampath] Found {len(results)} rate entries.")

    return results


if __name__ == "__main__":
    import json
    data = scrape()
    print(json.dumps(data, indent=2))
