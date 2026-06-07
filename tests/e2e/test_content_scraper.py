"""
E2E test for WebPageExtractor.get_webpage_content.

Reads URLs from a CSV with columns: url, expected (pass|fail), reason.
Runs up to MAX_FETCHES fetches and prints a per-URL report.
Flags unexpected outcomes (regressions) in the summary.

Usage:
    python tests/e2e/test_content_scraper.py --csv tests/e2e/inputs/content_urls.csv
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
PREVIEW_CHARS = 300

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
    parser = argparse.ArgumentParser(description="E2E test: content scraper")
    parser.add_argument("--csv", required=True, help="Path to CSV with url/expected/reason columns")
    args = parser.parse_args()

    rows = load_urls(args.csv)
    total = min(len(rows), MAX_FETCHES)
    print(f"\nContent scraper — testing {total} URLs from {args.csv}\n")

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
                content = extractor.get_webpage_content(url)
                elapsed = time.time() - t0
                v = verdict(True, expected)
                char_count = len(content)
                preview = content[:PREVIEW_CHARS].replace("\n", " ").strip()
                truncated = len(content) > PREVIEW_CHARS
                print(f"  STATUS   : {v} ({elapsed:.1f}s)")
                print(f"  CHARS    : {char_count}")
                print(f"  PREVIEW  : {preview}", end="")
                print(" [truncated]" if truncated else "")
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
