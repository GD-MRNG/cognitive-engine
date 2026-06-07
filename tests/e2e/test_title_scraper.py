"""
E2E test for WebPageExtractor.get_webpage_title.

Reads URLs from a CSV with columns: url, expected (pass|fail), reason.
Runs up to MAX_FETCHES fetches and prints a per-URL report.
Flags unexpected outcomes (regressions) in the summary.

Usage:
    python tests/e2e/test_title_scraper.py --csv tests/e2e/inputs/title_urls.csv
"""

import argparse
import csv
import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.web import WebPageExtractor

MAX_FETCHES = 20
MIN_TITLE_CHARS = 5  # titles shorter than this are likely garbage (e.g. "404", "...")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def load_urls(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "url" not in (reader.fieldnames or []):
            raise ValueError(f"CSV must have a 'url' column. Found: {reader.fieldnames}")
        rows = []
        for row in reader:
            url = row["url"].strip()
            if not url:
                continue
            rows.append({
                "url": url,
                "expected": row.get("expected", "pass").strip() or "pass",
                "reason": row.get("reason", "").strip(),
            })
        return rows


def verdict(actual_ok: bool, expected: str) -> str:
    if expected == "fail":
        return "EXPECTED FAIL" if not actual_ok else "UNEXPECTED PASS"
    return "OK" if actual_ok else "UNEXPECTED FAIL"


def main():
    parser = argparse.ArgumentParser(description="E2E test: title scraper")
    parser.add_argument("--csv", required=True, help="Path to CSV with url/expected/reason columns")
    args = parser.parse_args()

    rows = load_urls(args.csv)
    total = min(len(rows), MAX_FETCHES)
    print(f"\nTitle scraper — testing {total} URLs from {args.csv}\n")

    extractor = WebPageExtractor()
    results = []

    try:
        for i, row in enumerate(rows[:MAX_FETCHES], start=1):
            url, expected, reason = row["url"], row["expected"], row["reason"]
            print(f"--- [{i}/{total}] {url} ---")
            if expected == "fail" and reason:
                print(f"  EXPECTED : fail ({reason})")
            t0 = time.time()
            try:
                title = extractor.get_webpage_title(url)
                elapsed = time.time() - t0
                actual_ok = bool(title) and len(title) >= MIN_TITLE_CHARS
                v = verdict(actual_ok, expected)
                print(f"  STATUS   : {v} ({elapsed:.1f}s)")
                print(f"  TITLE    : {title!r} ({len(title)} chars)")
                if not actual_ok:
                    print(f"  NOTE     : title too short (min {MIN_TITLE_CHARS} chars)")
                results.append((url, v))
            except Exception as e:
                elapsed = time.time() - t0
                v = verdict(False, expected)
                print(f"  STATUS   : {v} ({elapsed:.1f}s)")
                print(f"  ERROR    : {e}")
                results.append((url, v))
            print()
    finally:
        extractor.manager.quit_driver()

    regressions = [r for r in results if "UNEXPECTED" in r[1]]
    print(f"{'=' * 60}")
    print(f"SUMMARY: {total} URLs")
    counts = {}
    for _, v in results:
        counts[v] = counts.get(v, 0) + 1
    for v, n in sorted(counts.items()):
        print(f"  {v:<20} {n}")
    if regressions:
        print(f"\nREGRESSIONS ({len(regressions)}):")
        for url, v in regressions:
            print(f"  {v}: {url}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
