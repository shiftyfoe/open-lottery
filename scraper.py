#!/usr/bin/env python3
"""
Singapore TOTO Historical Results Scraper
Scrapes all draw results from Singapore Pools website.

Draw range: ~40 to current (4195+ as of Jun 2026)
Rate: 1 request/second to be polite to the server
Output: data/toto_results.csv
"""

import base64
import csv
import re
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = "https://www.singaporepools.com.sg/en/product/sr/Pages/toto_results.aspx?sppl={qs}"
DRAW_LIST_URL = "https://www.singaporepools.com.sg/DataFileArchive/Lottery/Output/toto_result_draw_list_en.html"
FIRST_DRAW = 40
OUTPUT_FILE = Path("data/toto_results.csv")
DELAY_SECONDS = 1.0
MAX_RETRIES = 3
FIELDNAMES = ["draw_number", "draw_date", "n1", "n2", "n3", "n4", "n5", "n6", "additional", "jackpot"]


def encode_draw_number(n: int) -> str:
    return base64.b64encode(f"DrawNumber={n}".encode()).decode()


def fetch_draw(n: int):
    qs = encode_draw_number(n)
    url = BASE_URL.format(qs=qs)

    html = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            break
        except urllib.error.URLError as e:
            if attempt == MAX_RETRIES - 1:
                print(f"  ERROR fetching draw {n}: {e}")
                return None
            time.sleep(2 ** attempt)

    if html is None:
        return None

    # Verify we got the right draw (server returns latest draw if number doesn't exist)
    actual_draw = re.search(r"Draw No\. (\d+)", html)
    if not actual_draw or int(actual_draw.group(1)) != n:
        return None  # Draw doesn't exist (cancelled or pre-digitization)

    draw_date = ""
    date_m = re.search(r"drawDate'>([^<]+)<", html)
    if date_m:
        raw_date = date_m.group(1).strip()
        # Skip placeholder dates (year 0001 = no historical date in system)
        draw_date = "" if "0001" in raw_date else raw_date

    # Winning numbers (6 for modern draws, 5 for early draws pre-draw ~100)
    numbers = re.findall(r"class='win\d'>(\d+)", html)

    additional = ""
    add_m = re.search(r"class='additional'>(\d+)", html)
    if add_m:
        additional = add_m.group(1)

    jackpot = ""
    prize_m = re.search(r"Group 1 Prize.*?<td[^>]*>([$,\d]+)</td>", html, re.DOTALL)
    if prize_m:
        jackpot = prize_m.group(1).replace(",", "").replace("$", "")

    return {
        "draw_number": n,
        "draw_date": draw_date,
        "n1": numbers[0] if len(numbers) > 0 else "",
        "n2": numbers[1] if len(numbers) > 1 else "",
        "n3": numbers[2] if len(numbers) > 2 else "",
        "n4": numbers[3] if len(numbers) > 3 else "",
        "n5": numbers[4] if len(numbers) > 4 else "",
        "n6": numbers[5] if len(numbers) > 5 else "",
        "additional": additional,
        "jackpot": jackpot,
    }


def get_latest_draw_number() -> int:
    req = urllib.request.Request(DRAW_LIST_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    draws = re.findall(r"value='(\d+)'", html)
    return max(int(d) for d in draws) if draws else 0


def get_last_saved_draw() -> int:
    """Return the highest draw number already in the CSV (0 if file is empty/missing)."""
    if not OUTPUT_FILE.exists():
        return 0
    last = 0
    with open(OUTPUT_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            n = int(row["draw_number"])
            if n > last:
                last = n
    return last


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    print("Fetching latest draw number...")
    latest = get_latest_draw_number()
    if not latest:
        print("ERROR: could not determine latest draw number")
        raise SystemExit(1)

    last_saved = get_last_saved_draw()
    start_from = max(FIRST_DRAW, last_saved + 1)

    print(f"Latest draw on site: {latest}")
    print(f"Last saved draw:     {last_saved or 'none (first run)'}")
    print(f"Fetching draws {start_from} to {latest} ({latest - start_from + 1} draws)")

    if start_from > latest:
        print("Already up to date.")
        return

    write_header = not OUTPUT_FILE.exists() or OUTPUT_FILE.stat().st_size == 0

    with open(OUTPUT_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()

        fetched = 0
        missing = 0

        for n in range(start_from, latest + 1):
            result = fetch_draw(n)
            if result:
                writer.writerow(result)
                f.flush()
                fetched += 1
                if fetched % 50 == 0:
                    pct = (n - start_from + 1) / (latest - start_from + 1) * 100
                    print(f"  [{pct:.0f}%] draw {n}/{latest} — {fetched} fetched, {missing} not found")
            else:
                missing += 1
                print(f"  Draw {n}: not found (cancelled/non-existent)")

            time.sleep(DELAY_SECONDS)

    print(f"\nDone: {fetched} new draws saved, {missing} not found.")
    print(f"Output: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
