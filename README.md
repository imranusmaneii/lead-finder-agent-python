# Lead Finder Agent

A Python script that accepts a natural-language prompt describing the type of leads to find and a target location, then uses browser automation to scrape business listings from Bing Maps (with Google Search fallback) and saves the results as an Excel file.

## How It Works

1. You type a prompt like `"coffee shops in America"`
2. The agent parses out the business category (`coffee shops`) and location (`America`)
3. It launches a headless Chromium browser via Playwright
4. It opens Bing Maps, searches for the query, and scrolls through results
5. For each business found, it extracts: **name, phone, website, address**
6. It visits each business website to try to find an **email address**
7. If Bing Maps returns no results, it automatically falls back to **Google Search**
8. Results are saved to an Excel file like `leads_coffee_shops_America.xlsx`

## Install

```bash
pip install -r requirements.txt
playwright install chromium
```

## Run

```bash
# Interactive prompt
python main.py

# Or pass the prompt directly
python main.py "coffee shops in America"
python main.py "dentists in New York"
python main.py "burger shop in Karachi"

# With custom output filename
python main.py --output my_leads.xlsx "restaurants in Paris"

# Using the -p flag
python main.py -p "gyms in Dubai"

# Show version
python main.py --version
```

## CLI Options

| Flag | Description |
|---|---|
| `prompt` | Positional arg — the search prompt |
| `-p`, `--prompt-flag` | Alternative way to pass the search prompt |
| `-o`, `--output` | Custom output Excel filename |
| `-v`, `--version` | Show version and exit |

## Output

After execution, you will see:

- A printed summary showing the search query, number of leads collected, and the Excel filename
- An Excel file saved in the current directory (e.g., `leads_coffee_shops_America.xlsx`)

The Excel file contains columns:
| Business Name | Email | Phone Number | Website | Location |
|---|---|---|---|---|

## Running Tests

```bash
# Install test dependency
pip install pytest

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ -v --tb=short
```

## Project Structure

```
main.py              # CLI entry point — orchestrates the pipeline (argparse)
parse_prompt.py      # Extracts business category + location from NL prompt
scrape_leads.py      # Playwright browser automation (Bing Maps + Google fallback)
build_excel.py       # Generates the .xlsx output file with openpyxl
tests/               # Unit tests
  test_parse_prompt.py   # 20 tests for prompt parsing
  test_build_excel.py    # 13 tests for Excel generation
requirements.txt     # Python dependencies
README.md            # This file
```

## How the Excel File Is Generated

The Excel file is created in-memory using openpyxl and saved to disk in the current working directory. The file is never generated server-side — everything runs locally on your machine.

## Known Limitations

- Bing Maps is the primary data source. If it returns no results, the agent falls back to Google Search.
- Email extraction is best-effort — only attempted if a website URL was found, and many sites block or don't expose email addresses in their HTML.
- Lead count is capped at ~15 per search to stay within reasonable execution time.
- Bing Maps / Google DOM selectors may occasionally change if the providers update their layout.
- Browser automation requires Chromium to be installed via `playwright install chromium`.
