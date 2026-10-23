#!/usr/bin/env python3
"""
Appends one entry to wiki/log.md in the wiki's standard format:
  ## [YYYY-MM-DD HH:MM:SS] <action> | <title>
  <body>

Usage:
  python3 scripts/append_log.py --action ingest --title "Equity News Scan (2026-08-22)" --body "..."
  python3 scripts/append_log.py --action update --title "..." --body-file /path/to/body.txt
"""

import argparse
import datetime
import sys
from pathlib import Path

WIKI_ROOT = Path("/Users/chriseah/obsidian/wiki-trades")
LOG_FILE = WIKI_ROOT / "wiki/log.md"


def parse_args():
    parser = argparse.ArgumentParser(description="Append an entry to wiki/log.md")
    parser.add_argument("--action", required=True, help="Action word, e.g. ingest, update, note, query, lint")
    parser.add_argument("--title", required=True, help="Entry title")
    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="Inline body text")
    body_group.add_argument("--body-file", help="Path to a file containing the body text")
    return parser.parse_args()


def main():
    args = parse_args()

    if not LOG_FILE.exists():
        sys.exit(f"❌ {LOG_FILE} does not exist — refusing to create it from scratch (it has a structural header this script shouldn't guess at).")

    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8").strip()
    else:
        body = args.body.strip()

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"## [{timestamp}] {args.action} | {args.title}\n{body}\n"

    current = LOG_FILE.read_text(encoding="utf-8")
    updated = current.rstrip("\n") + "\n\n" + entry
    LOG_FILE.write_text(updated, encoding="utf-8")

    print(f"✅ Logged: {args.action} | {args.title}")


if __name__ == "__main__":
    main()
