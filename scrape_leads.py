"""Scrape business leads from Bing Maps using Playwright browser automation."""

import os
import re
import sys
import time
from playwright.sync_api import sync_playwright, Browser, Page


def _safe_print(msg: str) -> None:
    """Print with encoding fallback for terminals that can't handle Unicode."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


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


def _goto_with_retry(page: Page, url: str, max_attempts: int = 3, **kwargs) -> bool:
    """Navigate to a URL with retry on network errors."""
    kwargs.setdefault("wait_until", "domcontentloaded")
    kwargs.setdefault("timeout", 30000)
    for attempt in range(max_attempts):
        try:
            page.goto(url, **kwargs)
            return True
        except Exception as e:
            if attempt < max_attempts - 1:
                print(f"[Scrape] Navigation retry {attempt+1}/{max_attempts}: {e}")
                time.sleep(2)
            else:
                print(f"[Scrape] Navigation failed after {max_attempts} attempts: {e}")
    return False


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
    has_chrome = any(os.path.exists(path) for path in chrome_paths)

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]

    if has_chrome:
        print("[Scrape] Using system Chrome via channel")
        return p.chromium.launch(
            headless=False,
            channel="chrome",
            args=launch_args,
        )

    print("[Scrape] Using Playwright Chromium")
    return p.chromium.launch(
        headless=True,
        args=launch_args,
    )


def _open_browser_context(p):
    """Open a browser and context, return (browser, context, page)."""
    browser = _get_browser(p)
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
    return browser, context, page


def _dismiss_banners(page: Page) -> None:
    """Dismiss cookie/privacy banners."""
    try:
        for selector in [
            '#bnp_btn_accept',
            '#bnp_btn_dismiss',
            'button:has-text("Accept")',
            'button:has-text("Agree")',
            '#L2AGLb',
        ]:
            btn = page.locator(selector).first
            if btn.count() > 0:
                btn.click(timeout=3000)
                page.wait_for_timeout(1000)
                break
    except Exception:
        pass


def _search_bing_maps(page: Page, search_query: str) -> bool:
    """Navigate to Bing Maps and perform a search. Returns True on success."""
    print("[Scrape] Opening Bing Maps...")
    if not _goto_with_retry(page, "https://www.bing.com/maps"):
        return False
    page.wait_for_timeout(3000)
    _dismiss_banners(page)

    print("[Scrape] Entering search query...")
    search_box = page.locator("#searchBoxInput")
    if search_box.count() == 0:
        search_box = page.locator('input[name="searchbox"]')
    if search_box.count() == 0:
        search_box = page.locator('input[aria-label*="Search"]')
    if search_box.count() == 0:
        print("[Scrape] ERROR: Could not find search box on Bing Maps.")
        return False

    try:
        search_box.click(timeout=5000)
        search_box.fill(search_query)
        page.wait_for_timeout(500)
        search_box.press("Enter")
    except Exception as e:
        print(f"[Scrape] ERROR filling search box: {e}")
        return False

    print("[Scrape] Waiting for results...")
    page.wait_for_timeout(8000)
    return True


def _extract_leads_from_bing(page: Page, search_query: str) -> list[dict]:
    """Extract leads from Bing Maps results page using multiple strategies."""
    leads: list[dict] = []
    seen: set[str] = set()

    # Strategy 1: Try original li-based selectors
    result_items = page.locator("li.listingItem_fPE1q").all()
    if not result_items:
        result_items = page.locator("li[data-key]").all()
    if not result_items:
        # Try broader li selectors with substantial text
        all_li = page.locator("li").all()
        result_items = [
            item for item in all_li
            if (item.text_content() or "").strip() and len((item.text_content() or "").strip()) > 20
        ]

    if result_items:
        print(f"[Scrape] Found {len(result_items)} li result items")
        leads = _extract_from_li_items(page, result_items, search_query, seen)

    # Strategy 2: If no leads, try extracting from body text blocks
    if not leads:
        print("[Scrape] No li items found, trying body text extraction...")
        leads = _extract_from_body_text(page, search_query, seen)

    return leads


def _extract_from_li_items(page: Page, items: list, search_query: str, seen: set) -> list[dict]:
    """Extract leads from li elements (legacy Bing Maps layout)."""
    leads: list[dict] = []

    for i, item in enumerate(items):
        if len(leads) >= 15:
            break
        try:
            card_text = (item.text_content() or "").strip()
            if len(card_text) < 5:
                continue

            business_name = ""
            try:
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

            skip_words = ["item", "filter", "expand", "collapse", "map of", "toggle"]
            if any(sw in business_name.lower() for sw in skip_words):
                continue

            phone = ""
            pm = re.search(r"[\+]?[\d][\d\s\-\(\)]{7,}", card_text)
            if pm:
                phone = pm.group(0).strip()

            addr = _extract_address(card_text, business_name)
            website = _click_and_get_website(page, item)

            email = ""
            if website:
                try:
                    email = extract_email_from_website(
                        page,
                        website if website.startswith("http") else f"https://{website}",
                    )
                    _goto_with_retry(
                        page,
                        f"https://www.bing.com/maps/search?style=r&q={search_query.replace(' ', '+')}",
                    )
                    page.wait_for_timeout(4000)
                except Exception:
                    pass

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
            _safe_print(
                f"[Scrape] Lead {len(leads)}: {business_name} | "
                f"Phone: {phone or 'N/A'} | Web: {website or 'N/A'}"
            )

        except Exception as e:
            _safe_print(f"[Scrape] Error processing li item {i}: {e}")
            continue

    return leads


def _extract_address(text: str, business_name: str) -> str:
    """Try to extract an address from text."""
    addr = ""
    for line in text.split("\n"):
        line = line.strip()
        if not line or line == business_name:
            continue
        if re.search(r"\d", line) and any(s in line.lower() for s in
            ["st", "ave", "blvd", "rd", "dr", "ln", "block", "sector",
             "road", "street", "lane", "drive", "boulevard", "way",
             "court", "ct", "pl"]):
            addr = line
            break
    if not addr:
        for line in text.split("\n"):
            line = line.strip()
            if any(s in line.lower() for s in
                ["block", "sector", "floor", "suite", "apt", "unit",
                 "building", "center", "mall", "plaza"]):
                addr = line
                break
    return addr


def _click_and_get_website(page: Page, item) -> str:
    """Click an item to open detail panel and extract the website URL."""
    website = ""
    try:
        clickable = item.locator("button.listingContent_fjvwG, button").first
        if clickable.count() > 0:
            clickable.click(timeout=4000)
            page.wait_for_timeout(3500)

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

            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(1500)
            except Exception:
                pass
    except Exception:
        pass
    return website


def _extract_from_body_text(page: Page, search_query: str, seen: set) -> list[dict]:
    """Fallback: extract business leads from page body text using JS."""
    leads: list[dict] = []

    # Scroll the results panel to load more
    for _ in range(3):
        try:
            page.evaluate("""() => {
                const panel = document.querySelector('.b_results') ||
                              document.querySelector('#b_results') ||
                              document.querySelector('[class*="sidebar"]') ||
                              document.querySelector('[class*="panel"]');
                if (panel) panel.scrollBy(0, 500);
                else window.scrollBy(0, 500);
            }""")
        except Exception:
            try:
                page.mouse.wheel(0, 500)
            except Exception:
                pass
        page.wait_for_timeout(1500)

    # Extract all divs with substantial text and business-like content
    blocks = page.evaluate("""() => {
        const results = [];
        const allEls = document.querySelectorAll('div, section, li, article, span');
        for (const el of allEls) {
            const text = (el.textContent || '').trim();
            const children = el.children.length;
            // We want leaf-ish elements with meaningful text
            if (text.length > 30 && text.length < 500 && children < 5) {
                const rect = el.getBoundingClientRect();
                if (rect.width > 50 && rect.height > 20) {
                    results.push({
                        text: text.substring(0, 500),
                        tag: el.tagName,
                        cls: (el.className || '').toString().substring(0, 100),
                    });
                }
            }
        }
        return results.slice(0, 50);
    }""")

    print(f"[Scrape] Found {len(blocks)} text blocks for parsing")

    for block in blocks:
        if len(leads) >= 15:
            break
        text = block.get("text", "")
        if len(text) < 20:
            continue

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        business_name = ""

        for line in lines:
            if re.match(r"^\d+\.?\s*$", line):
                continue
            if re.match(r"^[\d:.\s\-]+(?:AM|PM|am|pm)?", line):
                continue
            if re.search(r"open|closed|closes|hours", line, re.I):
                continue
            if 3 <= len(line) <= 80:
                business_name = line
                break

        if not business_name or len(business_name) < 3:
            continue

        skip_words = ["people also ask", "related searches", "see more",
                      "reviews", "advertisement", "sponsored", "sign in",
                      "directions", "zoom", "traffic", "feedback"]
        if any(sw in business_name.lower() for sw in skip_words):
            continue

        phone = ""
        pm = re.search(r"[\+]?[\d][\d\s\-\(\)]{7,}", text)
        if pm:
            phone = pm.group(0).strip()

        addr = _extract_address(text, business_name)

        website = ""
        try:
            links = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a[href]'))
                    .map(a => ({href: a.href, text: a.textContent.trim()}))
                    .filter(l => l.href.startsWith('http') &&
                        !l.href.includes('bing.com') &&
                        !l.href.includes('microsoft.com') &&
                        !l.href.includes('google.com') &&
                        !l.href.includes('gstatic.com'))
                    .slice(0, 15);
            }""")
            for link in links:
                href = link.get("href", "")
                link_text = link.get("text", "").lower()
                if "website" in link_text or "visit" in link_text:
                    website = href
                    break
        except Exception:
            pass

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
        _safe_print(
                f"[Scrape] Lead {len(leads)}: {business_name} | "
                f"Phone: {phone or 'N/A'} | Web: {website or 'N/A'}"
            )

    return leads


def scrape_leads(business_category: str, location: str) -> list[dict]:
    """Search Bing Maps and extract business leads.

    Returns a list of dicts with keys:
        business_name, email, phone, website, location
    """
    search_query = f"{business_category} in {location}" if location else business_category
    print(f"[Scrape] Starting browser automation for: \"{search_query}\"")

    leads: list[dict] = []

    with sync_playwright() as p:
        browser, context, page = _open_browser_context(p)

        try:
            if _search_bing_maps(page, search_query):
                leads = _extract_leads_from_bing(page, search_query)
        except Exception as e:
            print(f"[Scrape] Error during Bing Maps scraping: {e}")

        browser.close()

    if not leads:
        print("[Scrape] Bing Maps returned no results. Falling back to Bing Search...")
        leads = _scrape_google_fallback(business_category, location)

    print(f"[Scrape] Completed. Found {len(leads)} leads for \"{search_query}\"")
    return leads


def _scrape_google_fallback(business_category: str, location: str) -> list[dict]:
    """Fall back to Bing Search when Bing Maps returns no results."""
    search_query = f"{business_category} in {location}" if location else business_category
    leads: list[dict] = []
    seen: set[str] = set()

    with sync_playwright() as p:
        browser, context, page = _open_browser_context(p)

        try:
            search_url = f"https://www.bing.com/search?q={search_query.replace(' ', '+')}&setlang=en"
            print(f"[Fallback] Searching Bing: \"{search_query}\"")
            if not _goto_with_retry(page, search_url):
                browser.close()
                return leads

            page.wait_for_timeout(4000)
            _dismiss_banners(page)

            print("[Fallback] Extracting Bing Search results...")

            results = page.evaluate("""() => {
                const items = [];
                // Organic search results
                for (const el of document.querySelectorAll('.b_algo')) {
                    const titleEl = el.querySelector('h2');
                    const title = titleEl ? titleEl.textContent.trim() : '';
                    const link = (el.querySelector('a') || {}).href || '';
                    const snippetEl = el.querySelector('.b_caption p, .b_algoSlug');
                    const snippet = snippetEl ? snippetEl.textContent.trim() : '';
                    if (title) {
                        items.push({title, snippet: snippet.substring(0, 400), link});
                    }
                }
                // Local pack / Bing Places results
                for (const el of document.querySelectorAll('.b_ans, .b_plist, [class*="placemark"]')) {
                    const text = (el.textContent || '').trim();
                    if (text.length > 20) {
                        items.push({title: '', snippet: text.substring(0, 500), link: ''});
                    }
                }
                return items.slice(0, 20);
            }""")

            print(f"[Fallback] Found {len(results)} Bing Search result blocks")

            # Visit each result page to extract actual business info
            for result in results:
                if len(leads) >= 15:
                    break

                title = result.get("title", "").strip()
                snippet = result.get("snippet", "").strip()
                link = result.get("link", "").strip()

                if not title or len(title) < 3:
                    continue

                skip_words = ["people also ask", "related searches", "see more",
                              "reviews", "advertisement", "sponsored", "sign in",
                              "wikipedia", "youtube", "reddit", "quora",
                              "top 10", "top 7", "best burgers", "best pizza",
                              "best restaurants", "best food", "best coffee",
                              "the best", "best in", "best of"]
                title_lower = title.lower()
                if any(sw in title_lower for sw in skip_words):
                    continue

                # Try to visit the link and extract business info
                if link and link.startswith("http") and not any(j in link for j in JUNK_WEBSITES):
                    try:
                        if _goto_with_retry(page, link, timeout=10000):
                            page.wait_for_timeout(2000)
                            page_content = page.evaluate("""() => {
                                const text = document.body.innerText || '';
                                return text.substring(0, 3000);
                            }""")
                            phone_match = re.search(r"[\+]?[\d][\d\s\-\(\)]{7,}", page_content)
                            phone = phone_match.group(0).strip() if phone_match else ""
                            addr = _extract_address(page_content, title)

                            leads.append({
                                "business_name": title,
                                "email": "",
                                "phone": phone or "",
                                "website": link,
                                "location": addr or "",
                            })
                            _safe_print(
                                f"[Fallback] Lead {len(leads)}: {title} | "
                                f"Phone: {phone or 'N/A'} | Web: {link[:50]}"
                            )
                    except Exception:
                        pass

                    dedup_key = f"{title.lower()}"
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)

            print("[Fallback] Attempting email extraction from websites...")
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

        except Exception as e:
            print(f"[Fallback] Error during Bing Search fallback: {e}")

        browser.close()

    print(f"[Fallback] Completed. Found {len(leads)} leads")
    return leads
