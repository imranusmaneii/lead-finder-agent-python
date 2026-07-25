"""Lead Finder Agent — CLI entry point.

Usage:
    python main.py
    python main.py "coffee shops in America"

The agent:
1. Parses the user prompt into business category + location
2. Scrapes Bing Maps for matching businesses
3. Extracts business name, phone, website, address, and email
4. Saves results to an Excel file
5. Prints a summary
"""

import sys
from parse_prompt import parse_prompt
from scrape_leads import scrape_leads
from build_excel import build_excel, get_excel_filename


def main() -> None:
    # Get prompt from command-line argument or interactive input
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = input("Enter your search prompt (e.g. 'coffee shops in America'): ").strip()

    if not prompt:
        print("Error: No prompt provided.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Lead Finder Agent")
    print(f"{'='*60}")
    print(f"  Prompt: {prompt}")

    # Step 1: Parse the prompt
    business_category, location = parse_prompt(prompt)
    if not business_category:
        print("Error: Could not understand the search prompt.")
        print("Try something like 'coffee shops in New York' or 'dentists in Chicago'.")
        sys.exit(1)

    query_display = f"{business_category} in {location}" if location else business_category
    print(f"  Category: {business_category}")
    print(f"  Location: {location or '(not specified)'}")
    print(f"  Search query: {query_display}")
    print(f"{'='*60}\n")

    # Step 2: Scrape leads
    try:
        leads = scrape_leads(business_category, location)
    except Exception as e:
        print(f"\nError during scraping: {e}")
        print("Make sure Playwright and Chromium are installed:")
        print("  pip install -r requirements.txt")
        print("  playwright install chromium")
        sys.exit(1)

    # Step 3: Save to Excel
    if leads:
        filename = build_excel(leads, business_category, location)
        print(f"\n  Excel file saved: {filename}")
    else:
        filename = get_excel_filename(business_category, location)
        print("\n  No leads found. No Excel file generated.")

    # Step 4: Print summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Search query:        {query_display}")
    print(f"  Business category:   {business_category}")
    print(f"  Location:            {location or '(not specified)'}")
    print(f"  Leads collected:     {len(leads)}")
    if leads:
        print(f"  Excel file:          {filename}")
        print(f"  Leads with email:    {sum(1 for l in leads if l.get('email'))}")
        print(f"  Leads with phone:    {sum(1 for l in leads if l.get('phone'))}")
        print(f"  Leads with website:  {sum(1 for l in leads if l.get('website'))}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
