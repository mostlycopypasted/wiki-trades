#!/usr/bin/env python3
"""
Manages the user-maintained equity watchlist for the equity-news-finder skill
(scripts/equity_watchlist.json) — stocks the user wants monitored for
corporate/dividend/general news on every skill run, independent of whether
they show up in Binni's Bull/Bear Daily Stock Alert sheet that day.

Symbols use the Yahoo Finance ticker scheme (same convention as the alert
sheet's own "Yahoo Symbol" column): bare ticker for US (NVDA), .SI for SGX
(D05.SI), .HK for HKEX (0700.HK), .KS for KRX (000660.KS), etc.

Usage:
    python3 scripts/manage_equity_watchlist.py list
    python3 scripts/manage_equity_watchlist.py add D05.SI --note "Core banking position"
    python3 scripts/manage_equity_watchlist.py remove D05.SI
"""

import argparse
import json
from datetime import date
from pathlib import Path

WATCHLIST_PATH = Path(__file__).resolve().parent / "equity_watchlist.json"

EXCHANGE_SUFFIXES = {
    ".SI": "SGX",
    ".HK": "HKEX",
    ".KS": "KRX",
    ".KQ": "KOSDAQ",
    ".T": "TSE",
    ".L": "LSE",
    ".AX": "ASX",
}


def market_for_symbol(symbol):
    sym = (symbol or "").upper()
    for suffix, market in EXCHANGE_SUFFIXES.items():
        if sym.endswith(suffix):
            return market
    return "US"


def load():
    if not WATCHLIST_PATH.exists():
        return []
    return json.loads(WATCHLIST_PATH.read_text())


def save(entries):
    WATCHLIST_PATH.write_text(json.dumps(entries, indent=2) + "\n")


def cmd_list(args):
    entries = load()
    if not entries:
        print("Watchlist is empty.")
        return
    for e in entries:
        note = f" — {e['note']}" if e.get("note") else ""
        name = f" {e['name']}" if e.get("name") else ""
        print(f"[[{e['symbol']}]]{name} ({e['market']}, added {e['added']}){note}")


def cmd_add(args):
    entries = load()
    symbol = args.symbol.strip().upper()
    if any(e["symbol"] == symbol for e in entries):
        print(f"{symbol} is already on the watchlist.")
        return
    entries.append({
        "symbol": symbol,
        "market": market_for_symbol(symbol),
        "added": date.today().isoformat(),
        "note": args.note or "",
        "name": args.name or "",
        "news_keyword": args.news_keyword or args.name or "",
    })
    save(entries)
    print(f"Added {symbol} ({market_for_symbol(symbol)}) to the watchlist.")


def cmd_remove(args):
    entries = load()
    symbol = args.symbol.strip().upper()
    remaining = [e for e in entries if e["symbol"] != symbol]
    if len(remaining) == len(entries):
        print(f"{symbol} was not on the watchlist.")
        return
    save(remaining)
    print(f"Removed {symbol} from the watchlist.")


def main():
    parser = argparse.ArgumentParser(description="Manage the equity-news-finder watchlist")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List watchlist symbols").set_defaults(func=cmd_list)

    p_add = sub.add_parser("add", help="Add a symbol to the watchlist")
    p_add.add_argument("symbol", help="Yahoo Finance ticker, e.g. D05.SI, NVDA, 000660.KS")
    p_add.add_argument("--note", help="Optional note (e.g. why it's being tracked)")
    p_add.add_argument("--name", help="Company name (shown in listings)")
    p_add.add_argument("--news-keyword", help="Search keyword for moomoo news (defaults to --name)")
    p_add.set_defaults(func=cmd_add)

    p_remove = sub.add_parser("remove", help="Remove a symbol from the watchlist")
    p_remove.add_argument("symbol", help="Yahoo Finance ticker to remove")
    p_remove.set_defaults(func=cmd_remove)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
