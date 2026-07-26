"""Scrape business leads from Bing Maps using Playwright browser automation."""

import os
import re
from playwright.sync_api import sync_playwright, Browser, Page


JUNK_EMAILS = [
    "example.com", "sentry.io", "wixpress.com", "schema.org",
    "googleapis.com", "google.com", "gstatic.com", "facebook.com",
    "cloudflare.com", "wordpress.org", "w3.org", ".png", ".jpg",
    ".gif", ".svg", ".webp", "no-reply", "noreply", "mailer-daemon",
    "wix.com", "squarespace.com", "weebly.com", "godaddy.com",
]

JUNK_WEBSITES = [
    "bingplaces.com", "openstreetmap.org", "microsoft.com", "bing.com",
    "google.com/maps", "go.microsoft",
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


def _get_browser(p):
    """Launch browser using system Chrome/Edge or Playwright Chromium."""
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    executable_path = None
    for path in chrome_paths:
        if os.path.exists(path):
            executable_path = path
            print(f"[Scrape] Using system browser: {path}")
            break
    if not executable_path:
        print("[Scrape] Using Playwright Chromium")

    return p.chromium.launch(
        headless=True,
        executable_path=executable_path,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )


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
        browser: Browser = _get_browser(p)
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
                '#bnp_btn_accept',
                '#bnp_btn_dismiss',
                'button:has-text("Accept")',
                'button:has-text("Agree")',
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
        search_box = page.locator("#searchBoxInput")
        if search_box.count() == 0:
            search_box = page.locator('input[name="searchbox"]')
        if search_box.count() == 0:
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
        page.wait_for_timeout(6000)

        # Scroll the results panel to load more listings
        print("[Scrape] Scrolling results panel...")
        for _ in range(4):
            try:
                page.evaluate("""() => {
                    const panel = document.querySelector('.b_results') ||
                                  document.querySelector('#b_results') ||
                                  document.querySelector('[class*="listingItem"]');
                    if (panel) panel.scrollBy(0, 500);
                    else window.scrollBy(0, 500);
                }""")
            except Exception:
                try:
                    page.mouse.wheel(0, 500)
                except Exception:
                    pass
            page.wait_for_timeout(1500)

        # Extract leads from result list items
        print("[Scrape] Extracting lead data from results...")

        # Bing Maps puts results in <li> elements with class containing "listingItem"
        result_items = page.locator("li.listingItem_fPE1q").all()
        if not result_items:
            # Fallback: try any li with data-key
            result_items = page.locator("li[data-key]").all()
        if not result_items:
            # Broader fallback
            result_items = page.locator("li").all()
            result_items = [
                item for item in result_items
                if (item.text_content() or "").strip() and len((item.text_content() or "").strip()) > 20
            ]

        print(f"[Scrape] Found {len(result_items)} result items")

        for i, item in enumerate(result_items):
            if len(leads) >= 15:
                break

            try:
                # Extract text content of the card
                card_text = (item.text_content() or "").strip()
                if len(card_text) < 5:
                    continue

                # Extract business name from heading or button title
                business_name = ""
                try:
                    # Try h2 first
                    h2 = item.locator("h2").first
                    if h2.count() > 0:
                        business_name = (h2.text_content() or "").strip()
                except Exception:
                    pass
                if not business_name:
                    try:
                        btn = item.locator("button[title]").first
                        if btn.count() > 0:
                            business_name = (btn.get_attribute("title") or "").strip()
                    except Exception:
                        pass
                if not business_name:
                    try:
                        mag = item.locator("[data-n]").first
                        if mag.count() > 0:
                            business_name = (mag.get_attribute("data-n") or "").strip()
                    except Exception:
                        pass

                if not business_name or len(business_name) < 2:
                    continue

                # Skip non-business results
                skip_words = ["item", "filter", "expand", "collapse", "map of", "toggle"]
                if any(sw in business_name.lower() for sw in skip_words):
                    continue

                # Extract phone from card text
                phone = ""
                pm = re.search(r"[\+]?[\d][\d\s\-\(\)]{7,}", card_text)
                if pm:
                    phone = pm.group(0).strip()

                # Extract category and address from card text
                card_lines = card_text.split("\n")
                addr = ""
                category = ""
                for line in card_lines:
                    line = line.strip()
                    if not line or line == business_name:
                        continue
                    # Category is usually short and contains common words
                    cat_words = ["restaurant", "fast food", "cafe", "coffee", "burger",
                                 "pizza", "bakery", "store", "shop", "dentist", "clinic",
                                 "hospital", "salon", "gym", "hotel", "bar", "pub"]
                    if any(cw in line.lower() for cw in cat_words) and len(line) < 50:
                        category = line
                    # Address usually has numbers and street indicators
                    if re.search(r"\d", line) and any(s in line.lower() for s in ["st", "ave", "blvd", "rd", "dr", "ln", "block", "sector", "road", "street"]):
                        addr = line

                # Now click to open detail panel for more info (website, full address)
                website = ""
                try:
                    clickable = item.locator("button.listingContent_fjvwG, button").first
                    if clickable.count() > 0:
                        clickable.click(timeout=4000)
                        page.wait_for_timeout(3500)

                        # Look for website link in detail panel
                        web_links = page.evaluate("""() => {
                            const links = document.querySelectorAll('a[href]');
                            return Array.from(links)
                                .map(a => ({href: a.href, text: a.textContent.trim()}))
                                .filter(l => l.href.startsWith('http') &&
                                    !l.href.includes('bing.com') &&
                                    !l.href.includes('microsoft.com') &&
                                    !l.href.includes('go.microsoft') &&
                                    !l.href.includes('bingplaces.com') &&
                                    !l.href.includes('openstreetmap.org'))
                                .slice(0, 10);
                        }""")
                        for wl in web_links:
                            href = wl.get("href", "")
                            text = wl.get("text", "").lower()
                            if "website" in text or "visit" in text or "open" in text:
                                website = href
                                break
                        if not website and web_links:
                            website = web_links[0].get("href", "")

                        # Try to get full address from detail
                        if not addr:
                            addr = page.evaluate("""() => {
                                const panels = document.querySelectorAll(
                                    '[class*="detail"], [class*="panel"], [class*="sidebar"], [class*="entity"]'
                                );
                                for (const p of panels) {
                                    const text = p.textContent || '';
                                    if (text.length > 20) return text.substring(0, 500);
                                }
                                return '';
                            }""")

                        # Go back to list
                        try:
                            page.keyboard.press("Escape")
                            page.wait_for_timeout(1500)
                        except Exception:
                            pass

                except Exception:
                    pass

                # Visit business website to find email
                email = ""
                if website:
                    try:
                        email = extract_email_from_website(
                            page,
                            website if website.startswith("http") else f"https://{website}",
                        )
                        # Navigate back to Bing Maps
                        page.goto(
                            f"https://www.bing.com/maps/search?style=r&q={search_query.replace(' ', '+')}",
                            wait_until="domcontentloaded",
                            timeout=30000,
                        )
                        page.wait_for_timeout(4000)
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

        browser.close()

    # Fallback to Google Search if Bing Maps returned no results
    if not leads:
        print("[Scrape] Bing Maps returned no results. Falling back to Google Search...")
        leads = _scrape_google_fallback(business_category, location)

    print(f"[Scrape] Completed. Found {len(leads)} leads for \"{search_query}\"")
    return leads


def _scrape_google_fallback(business_category: str, location: str) -> list[dict]:
    """Fall back to Google Search when Bing Maps returns no results.

    Searches Google for local business listings and extracts name, phone,
    website, and address from the local pack and organic results.
    """
    search_query = f"{business_category} in {location}" if location else business_category
    leads: list[dict] = []
    seen: set[str] = set()

    with sync_playwright() as p:
        browser: Browser = _get_browser(p)
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

        print(f"[Google] Searching: \"{search_query}\"")
        page.goto(
            f"https://www.google.com/search?q={search_query.replace(' ', '+')}&tbm=lcl",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        page.wait_for_timeout(4000)

        # Dismiss consent dialogs
        try:
            for selector in [
                'button:has-text("Accept all")',
                'button:has-text("I agree")',
                '#L2AGLb',
                '#btnN',
            ]:
                btn = page.locator(selector).first
                if btn.count() > 0:
                    btn.click(timeout=3000)
                    page.wait_for_timeout(1000)
                    break
        except Exception:
            pass

        # Extract from Google local pack (the map + list of businesses)
        print("[Google] Extracting local pack results...")
        local_results = page.evaluate("""() => {
            const results = [];
            // Try local pack items
            const items = document.querySelectorAll('.VkpGBb, .rllt__details, [data-attrid="kc:/local:one box"]');
            for (const item of items) {
                const text = item.textContent || '';
                if (text.length > 5) {
                    results.push({
                        text: text.substring(0, 500),
                        tag: item.tagName,
                        class: item.className.substring(0, 100)
                    });
                }
            }
            // Also try organic results with location info
            const organic = document.querySelectorAll('.g, .tF2Cxc');
            for (const item of organic) {
                const text = item.textContent || '';
                if (text.length > 20 && text.length < 1000) {
                    results.push({
                        text: text.substring(0, 500),
                        tag: item.tagName,
                        class: item.className.substring(0, 100)
                    });
                }
            }
            return results.slice(0, 20);
        }""")

        print(f"[Google] Found {len(local_results)} raw result blocks")

        for block in local_results:
            if len(leads) >= 15:
                break

            text = block.get("text", "")
            if len(text) < 10:
                continue

            # Extract business name — usually the first meaningful line
            business_name = ""
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            for line in lines:
                # Skip lines that are just ratings, hours, or addresses
                if re.match(r"^\d+\.?\s*$", line):
                    continue
                if re.match(r"^[\d:.\s\-–]+(?:AM|PM|am|pm)?", line):
                    continue
                if re.search(r"open|closed|closes|hours", line, re.I):
                    continue
                if len(line) >= 3 and len(line) <= 80:
                    business_name = line
                    break

            if not business_name or len(business_name) < 2:
                continue

            # Skip non-business results
            skip_words = ["people also ask", "related searches", "see more",
                          "reviews", "advertisement", "sponsored"]
            if any(sw in business_name.lower() for sw in skip_words):
                continue

            # Extract phone
            phone = ""
            pm = re.search(r"[\+]?[\d][\d\s\-\(\)]{7,}", text)
            if pm:
                phone = pm.group(0).strip()

            # Extract address — look for street-like patterns
            addr = ""
            for line in lines:
                if re.search(r"\d", line) and any(s in line.lower() for s in
                    ["st", "ave", "blvd", "rd", "dr", "ln", "road", "street",
                     "lane", "drive", "boulevard", "way", "court", "ct", "pl"]):
                    addr = line
                    break
            # Also try lines with common location indicators
            if not addr:
                for line in lines:
                    if any(s in line.lower() for s in
                        ["block", "sector", "floor", "suite", "apt", "unit",
                         "building", "center", "mall", "plaza"]):
                        addr = line
                        break

            # Extract website from links
            website = ""
            try:
                links = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a[href]'))
                        .map(a => ({href: a.href, text: a.textContent.trim()}))
                        .filter(l => l.href.startsWith('http') &&
                            !l.href.includes('google.com') &&
                            !l.href.includes('gstatic.com') &&
                            !l.href.includes('googleapis.com'))
                        .slice(0, 10);
                }""")
                for link in links:
                    href = link.get("href", "")
                    link_text = link.get("text", "").lower()
                    if "website" in link_text or "visit" in link_text:
                        website = href
                        break
                if not website and links:
                    website = links[0].get("href", "")
            except Exception:
                pass

            # Dedup
            dedup_key = f"{business_name.lower()}|{phone}|{website}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            leads.append({
                "business_name": business_name,
                "email": "",
                "phone": phone or "",
                "website": website or "",
                "location": addr or "",
            })
            print(
                f"[Google] Lead {len(leads)}: {business_name} | "
                f"Phone: {phone or 'N/A'} | Web: {website or 'N/A'}"
            )

        # Try to get emails from websites
        print("[Google] Attempting email extraction from websites...")
        for lead in leads:
            if lead["website"]:
                try:
                    email = extract_email_from_website(
                        page,
                        lead["website"] if lead["website"].startswith("http")
                        else f"https://{lead['website']}",
                    )
                    if email:
                        lead["email"] = email
                except Exception:
                    pass

        browser.close()

    print(f"[Google] Fallback completed. Found {len(leads)} leads")
    return leads
