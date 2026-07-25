"""Scrape business leads from Bing Maps using Playwright browser automation."""

import re
import time
from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PwTimeout


JUNK_EMAILS = [
    "example.com", "sentry.io", "wixpress.com", "schema.org",
    "googleapis.com", "google.com", "gstatic.com", "facebook.com",
    "cloudflare.com", "wordpress.org", "w3.org", ".png", ".jpg",
    ".gif", ".svg", ".webp", "no-reply", "noreply", "mailer-daemon",
    "wix.com", "squarespace.com", "weebly.com", "godaddy.com",
]


def extract_email_from_website(page: Page, url: str) -> str:
    """Visit a business website and try to find an email address."""
    try:
        page.goto(url, timeout=8000, wait_until="domcontentloaded")
        content = page.content()
        email_pattern = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        matches = re.findall(email_pattern, content)
        for email in matches:
            if not any(junk in email.lower() for junk in JUNK_EMAILS):
                return email
    except Exception:
        pass
    return ""


def scrape_leads(business_category: str, location: str) -> list[dict]:
    """Search Bing Maps and extract business leads.

    Returns a list of dicts with keys:
        business_name, email, phone, website, location
    """
    search_query = f"{business_category} in {location}" if location else business_category
    print(f"[Scrape] Starting browser automation for: \"{search_query}\"")

    leads: list[dict] = []
    seen: set[str] = set()

    with sync_playwright() as p:
        browser: Browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => false});"
        )
        page = context.new_page()

        # Navigate to Bing Maps
        print("[Scrape] Opening Bing Maps...")
        page.goto("https://www.bing.com/maps", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Dismiss any cookie/privacy banners
        try:
            for selector in [
                'button:has-text("Accept")',
                'button:has-text("I agree")',
                'button:has-text("Agree")',
                '#bnp_btn_accept',
                '#bnp_btn_dismiss',
            ]:
                btn = page.locator(selector).first
                if btn.count() > 0:
                    btn.click(timeout=3000)
                    page.wait_for_timeout(1000)
                    break
        except Exception:
            pass

        # Find and fill the search box
        print("[Scrape] Entering search query...")
        search_box = None
        for selector in ["#sb_form_q", "#maps_sb", 'input[name="q"]', 'input[type="search"]', "#maps_sb_input"]:
            loc = page.locator(selector)
            if loc.count() > 0:
                search_box = loc.first
                break

        if not search_box:
            print("[Scrape] ERROR: Could not find search box on Bing Maps.")
            browser.close()
            return leads

        try:
            search_box.click(timeout=5000)
            search_box.fill(search_query)
            page.wait_for_timeout(500)
            search_box.press("Enter")
        except Exception as e:
            print(f"[Scrape] ERROR filling search box: {e}")
            browser.close()
            return leads

        # Wait for results to load
        print("[Scrape] Waiting for results...")
        page.wait_for_timeout(5000)

        # Scroll the results panel to load more listings
        print("[Scrape] Scrolling results panel...")
        for _ in range(6):
            try:
                # Try to scroll the results sidebar
                scrolled = False
                for scroll_sel in [
                    ".b_results",
                    "#b_results",
                    ".b_algo",
                    '[id*="result"]',
                    "ul.b_algo",
                ]:
                    panel = page.locator(scroll_sel).first
                    if panel.count() > 0:
                        panel.evaluate("el => el.scrollBy(0, 600)")
                        scrolled = True
                        break
                if not scrolled:
                    page.mouse.wheel(0, 600)
            except Exception:
                try:
                    page.mouse.wheel(0, 600)
                except Exception:
                    pass
            page.wait_for_timeout(1500)

        # Extract leads from search results
        print("[Scrape] Extracting lead data from results...")

        # Try multiple selector strategies for result items
        result_items = []
        result_selectors = [
            ".b_algo",
            ".b_algo h2 a",
            'li.b_algo',
            '[data-bm="1"]',
            ".b_ans",
        ]
        for sel in result_selectors:
            items = page.locator(sel).all()
            if len(items) > len(result_items):
                result_items = items
                print(f"[Scrape] Found {len(items)} results with selector: {sel}")

        if not result_items:
            # Fallback: try all links in results area
            print("[Scrape] No results found with standard selectors, trying fallback...")
            all_links = page.locator("a").all()
            for link in all_links:
                try:
                    href = link.get_attribute("href") or ""
                    text = link.text_content() or ""
                    if text.strip() and len(text.strip()) > 3:
                        result_items.append(link)
                except Exception:
                    continue
            print(f"[Scrape] Fallback found {len(result_items)} potential links")

        for i, item in enumerate(result_items):
            if len(leads) >= 15:
                break
            try:
                # Extract business name
                business_name = ""
                try:
                    # Try to get from heading
                    heading = item.locator("h2, h3, .b_title").first
                    if heading.count() > 0:
                        business_name = (heading.text_content() or "").strip()
                except Exception:
                    pass

                if not business_name:
                    try:
                        business_name = (item.text_content() or "").split("\n")[0].strip()
                    except Exception:
                        pass

                if not business_name or len(business_name) < 2:
                    continue

                # Get the detail page URL
                detail_url = ""
                try:
                    link = item.locator("a").first
                    if link.count() > 0:
                        detail_url = link.get_attribute("href") or ""
                except Exception:
                    pass

                # Try to extract phone from the visible text
                phone = ""
                website = ""
                addr = ""
                try:
                    block_text = item.text_content() or ""
                    phone_match = re.search(r"[\+]?[\d][\d\s\-\(\)]{7,}", block_text)
                    if phone_match:
                        phone = phone_match.group(0).strip()
                except Exception:
                    pass

                # Now click into the Bing Maps result to get details
                # Bing Maps shows a side panel with details when you click
                if detail_url and "bing.com/maps" in detail_url:
                    try:
                        item.click(timeout=4000)
                        page.wait_for_timeout(3000)

                        detail_text = ""
                        try:
                            detail_panel = page.locator(
                                '[class*="detail"], [class*="panel"], [class*="sidebar"], '
                                '[class*="entity"], .b_entityPanel'
                            ).first
                            if detail_panel.count() > 0:
                                detail_text = detail_panel.text_content() or ""
                        except Exception:
                            pass

                        if not detail_text:
                            detail_text = page.locator("body").text_content() or ""

                        # Extract phone from detail
                        if not phone:
                            pm = re.search(r"[\+]?[\d][\d\s\-\(\)]{7,}", detail_text)
                            if pm:
                                phone = pm.group(0).strip()

                        # Extract website from detail
                        try:
                            web_link = page.locator(
                                'a[href*="http"]:not([href*="bing.com"]):not([href*="microsoft.com"]):not([href*="go.microsoft"])'
                            ).first
                            if web_link.count() > 0:
                                href = web_link.get_attribute("href") or ""
                                if href and "bing.com" not in href and "microsoft.com" not in href:
                                    website = href
                        except Exception:
                            pass

                        # Extract address from detail
                        if not addr:
                            try:
                                addr_el = page.locator(
                                    '[class*="address"], [class*="addr"]'
                                ).first
                                if addr_el.count() > 0:
                                    addr = (addr_el.text_content() or "").strip()
                            except Exception:
                                pass

                        # Go back to results list
                        try:
                            back_btn = page.locator(
                                'button[aria-label*="Back"], button[aria-label*="back"], '
                                'a[aria-label*="Back"], #backBtn'
                            ).first
                            if back_btn.count() > 0:
                                back_btn.click(timeout=3000)
                                page.wait_for_timeout(2000)
                        except Exception:
                            page.go_back(timeout=5000)
                            page.wait_for_timeout(2000)

                    except Exception:
                        pass

                # Visit business website to find email
                email = ""
                if website:
                    try:
                        normalized_url = (
                            website if website.startswith("http") else f"https://{website}"
                        )
                        email = extract_email_from_website(page, normalized_url)
                        # Go back to Bing Maps
                        page.go_back(timeout=5000)
                        page.wait_for_timeout(1000)
                    except Exception:
                        pass

                # Dedup check
                dedup_key = f"{business_name.lower()}|{phone}|{website}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                leads.append({
                    "business_name": business_name,
                    "email": email or "",
                    "phone": phone or "",
                    "website": website or "",
                    "location": addr or "",
                })
                print(
                    f"[Scrape] Lead {len(leads)}: {business_name} | "
                    f"Phone: {phone or 'N/A'} | Web: {website or 'N/A'}"
                )

            except Exception as e:
                print(f"[Scrape] Error processing result {i}: {e}")
                continue

        # If Bing Maps didn't yield results, try Google Search as fallback
        if not leads:
            print("[Scrape] Bing Maps yielded no results. Trying Google Search fallback...")
            try:
                leads = _google_search_fallback(page, search_query, seen)
            except Exception as e:
                print(f"[Scrape] Google Search fallback failed: {e}")

        browser.close()

    print(f"[Scrape] Completed. Found {len(leads)} leads for \"{search_query}\"")
    return leads


def _google_search_fallback(page: Page, search_query: str, seen: set) -> list[dict]:
    """Fallback: scrape business info from Google Search local results."""
    leads: list[dict] = []

    try:
        page.goto(
            f"https://www.google.com/search?q={search_query}",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        page.wait_for_timeout(3000)

        # Google's local pack shows business cards
        cards = page.locator('[data-attrid="kc:/local:one box"]').all()
        if not cards:
            cards = page.locator('.VkpGBb, .dbg0pd, [data-local-attribute]').all()
        if not cards:
            cards = page.locator('.rllt__details').all()

        print(f"[Scrape-Fallback] Found {len(cards)} local result cards")

        for card in cards[:15]:
            try:
                text = card.text_content() or ""

                business_name = ""
                try:
                    name_el = card.locator("[role='heading'], .dbg0pd, .OSrXXb").first
                    if name_el.count() > 0:
                        business_name = (name_el.text_content() or "").strip()
                except Exception:
                    pass
                if not business_name:
                    business_name = text.split("\n")[0].strip()[:100]

                if not business_name or len(business_name) < 2:
                    continue

                phone = ""
                pm = re.search(r"[\+]?[\d][\d\s\-\(\)]{7,}", text)
                if pm:
                    phone = pm.group(0).strip()

                website = ""
                try:
                    web_el = card.locator("a[href^='http']:not([href*='google'])").first
                    if web_el.count() > 0:
                        website = web_el.get_attribute("href") or ""
                except Exception:
                    pass

                addr = ""
                try:
                    addr_el = card.locator('[data-local-attribute="addressLine1"], .rllt__details div:nth-child(3)').first
                    if addr_el.count() > 0:
                        addr = (addr_el.text_content() or "").strip()
                except Exception:
                    pass

                dedup_key = f"{business_name.lower()}|{phone}|{website}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                email = ""
                if website:
                    try:
                        email = extract_email_from_website(
                            page, website if website.startswith("http") else f"https://{website}"
                        )
                    except Exception:
                        pass

                leads.append({
                    "business_name": business_name,
                    "email": email or "",
                    "phone": phone or "",
                    "website": website or "",
                    "location": addr or "",
                })
                print(f"[Scrape-Fallback] Lead {len(leads)}: {business_name}")

            except Exception:
                continue

    except Exception as e:
        print(f"[Scrape-Fallback] Error: {e}")

    return leads
