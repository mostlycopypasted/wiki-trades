#!/usr/bin/env python3
"""
Currency strength derived from TradingView 4H-chart ZigZag market structure.

Same scoring as scripts/tat_currency_strength.py (Daily) — each pair's `structure`
(Bullish / Bearish / Squeeze, from the last 2 ZigZag pivot labels HH/HL/LH/LL) moves
its base currency +1 and its quote -1 (Bullish) or the reverse (Bearish); Squeeze
contributes nothing. Only the chart timeframe differs, so the two readings are
directly comparable: Daily = the established trend, 4H = the nearer-term swing.
This module imports the Daily script's scoring, labels and chart code unchanged.

Unlike the Daily brief (one file per day), a 4H structure can change several times
a day, so every scan is its own snapshot: ~/tradingview-mcp/4H_brief/YYYY-MM-DD_HHMM.json.
Run it just after a 4H bar closes (forex 4H bars close 01:00/05:00/09:00/13:00/17:00/
21:00 SGT) so the ZigZag labels are read off a completed bar, not a forming one — the
09:01/13:01/17:01/21:01 SGT TAT review slots line up with that.

Usage:
    python3 scripts/tat_currency_strength_4h.py --scan     # live tv scan, then report
    python3 scripts/tat_currency_strength_4h.py            # re-render from saved snapshots

--scan opens TradingView once (tv_session.sh start/stop, per the Batch TradingView
Session Rule), runs `tv brief` over ~/tradingview-mcp/forex_list.json with its
default_timeframe overridden to 240, and builds the snapshot via build_daily_bias.py.

Writes:
  - wiki/notes/currency-strength-4h.md          8 majors, rewritten in place
  - wiki/images/currency-strength-4h-graph.svg   8-majors trend chart (last 10 scans)
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import tat_currency_strength as daily
from tat_currency_strength import (
    CURRENCIES, WIKI_ROOT, bias_label, calculate_strength, clean_symbol,
    generate_svg_chart, suggested_pairs, watchlist_major_pairs,
)

MCP_DIR = Path.home() / "tradingview-mcp"
BRIEF_DIR = MCP_DIR / "4H_brief"
RULES_PATH = MCP_DIR / "forex_list.json"
SNAPSHOT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}$")
CHART_SNAPSHOTS = 10   # x-axis labels get crowded beyond this


def scan(snapshot_key):
    rules = json.loads(RULES_PATH.read_text())
    rules["default_timeframe"] = "240"
    # `tv brief` refuses a rules file outside the tradingview-mcp project, so the
    # temporary 4H copy lives there and is removed in the finally block.
    rules_tmp = str(MCP_DIR / f"rules_4h_{snapshot_key}.tmp.json")
    Path(rules_tmp).write_text(json.dumps(rules))
    dump = Path(tempfile.gettempdir()) / f"tv_brief_4h_{snapshot_key}.json"
    tv_session = WIKI_ROOT / "scripts" / "tv_session.sh"
    ok = False
    try:
        subprocess.run(["bash", str(tv_session), "start"], check=True)
        with open(dump, "w") as out:
            # --timeout-ms: the CLI default (180s) is too short for a multi-symbol live scan.
            subprocess.run(["node", "src/cli/index.js", "brief", "--timeout-ms", "600000", "-r", rules_tmp],
                           cwd=MCP_DIR, stdout=out, check=True)
        if dump.stat().st_size == 0:
            raise RuntimeError("tv brief produced no output")
        subprocess.run([sys.executable, str(WIKI_ROOT / "scripts" / "build_daily_bias.py"), str(dump),
                        "--date", snapshot_key, "--out-dir", str(BRIEF_DIR)], check=True)
        ok = True
    finally:
        subprocess.run(["bash", str(tv_session), "stop"])
        Path(rules_tmp).unlink(missing_ok=True)
    return ok


def load_snapshots():
    data = {}
    for f in sorted(BRIEF_DIR.glob("*.json")):
        if not SNAPSHOT_RE.match(f.stem):   # skips the older Daily-format files in this folder
            continue
        try:
            content = json.loads(f.read_text())
        except Exception as e:
            print(f"Warning: could not read {f.name}: {e}")
            continue
        if isinstance(content, list) and content:
            data[f.stem] = content
    return data


def pretty(key):
    """2026-10-18_0900 -> '2026-10-18 09:00 SGT'"""
    return f"{key[:10]} {key[11:13]}:{key[13:15]} SGT"


def chart_label(key):
    """Chart x-axis label; generate_svg_chart renders split('-')[-2]/split('-')[-1] -> 'MM/DD HHh'."""
    return f"{key[5:7]}-{key[8:10]} {key[11:13]}h"


def structure_changes(data, keys, symbol_filter):
    if len(keys) < 2:
        return [], None
    prev, latest = keys[-2], keys[-1]
    old_map = {clean_symbol(i): i.get("structure") for i in data[prev]}
    changes = []
    for item in data[latest]:
        sym = clean_symbol(item)
        if sym not in symbol_filter:
            continue
        old, new = old_map.get(sym), item.get("structure")
        if old and new and old != new:
            changes.append((sym, old, new))
    return sorted(changes), prev


def read_daily_note():
    """Daily scores from the published Daily note, not the local daily_brief/*.json:
    the Daily pipeline may run on another machine, leaving this machine's JSONs stale."""
    path = WIKI_ROOT / "wiki" / "notes" / "currency-strength.md"
    if not path.exists():
        return None, None
    text = path.read_text(encoding="utf-8")
    m = re.search(r"## Latest Readings \((\d{4}-\d{2}-\d{2})\)", text)
    scores = {c: int(v) for c, v in re.findall(r"\|\s*\*\*([A-Z]{3})\*\*\s*\|\s*([+-−]?\d+)\s*\|", text.replace("−", "-"))}
    if not m or set(scores) != set(CURRENCIES):
        return None, None
    return scores, m.group(1)


def write_note(keys, history, data, major_pairs):
    latest = keys[-1]
    scores = history[latest]
    lines = [
        "---", "kind: note", "tags: [trading-instrument, reference]",
        f"updated: {latest[:10]}", "sources: 1", "---", "",
        "# Currency Strength Tracker — 4H", "",
        "Currency strength derived from TradingView **4H-chart** ZigZag Market Structure "
        "(`ZigZag Multi [TradingFinder]` study) across the 8 major currencies, aggregated "
        f"from {len(major_pairs)} forex pairs on the live watchlist. Same scoring as the "
        "[Daily tracker](currency-strength.md) — each Bullish pair is +1 base / −1 quote, "
        "each Bearish pair the reverse, Squeeze scores 0 — so a currency that is strong on "
        "both timeframes is a stronger signal than one strong on only one. "
        f"Latest scan: `{pretty(latest)}` (`~/tradingview-mcp/4H_brief/{latest}.json`).", "",
        "![Currency Strength 4H Trend Graph](../images/currency-strength-4h-graph.svg)", "",
        f"## Latest Readings ({pretty(latest)})", "",
        "| Currency | 4H Score | 4H Trend Bias | Daily Score | Daily Bias |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    daily_scores, daily_date = read_daily_note()
    for cur in sorted(CURRENCIES, key=lambda c: scores[c], reverse=True):
        s = scores[cur]
        d = f"{daily_scores[cur]:+d} | {bias_label(daily_scores[cur])}" if daily_scores else "— | —"
        lines.append(f"| **{cur}** | {s:+d} | {bias_label(s)} | {d} |")
    if daily_scores:
        lines += ["", f"*Daily columns are the {daily_date} readings from [currency-strength.md](currency-strength.md), for context.*"]

    buys, sells = suggested_pairs(scores, major_pairs)
    lines += [
        "", f"## Suggested Pairs to Trade ({pretty(latest)})", "",
        f"- **Structure-Aligned Buys** (strong vs. weak on 4H, score gap ≥4): {', '.join(buys) if buys else 'None'}",
        f"- **Structure-Aligned Sells**: {', '.join(sells) if sells else 'None'}",
    ]

    changes, prev = structure_changes(data, keys, major_pairs)
    lines += ["", f"## Change of Structure Since Last Scan ({pretty(prev)} → {pretty(latest)})" if prev
              else "## Change of Structure Since Last Scan", ""]
    if not prev:
        lines.append("*No prior 4H scan available for comparison.*")
    elif not changes:
        lines.append(f"*No structure changes among the 8 majors since {pretty(prev)}.*")
    else:
        lines += ["| Pair | Previous Structure | Current Structure |", "| :--- | :--- | :--- |"]
        lines += [f"| **{s}** | {o} | {n} |" for s, o, n in changes]

    lines += [
        "", "## Recent Scans", "",
        "| Scan (SGT) | " + " | ".join(CURRENCIES) + " |",
        "| :--- |" + " :---: |" * len(CURRENCIES),
    ]
    for k in reversed(keys[-CHART_SNAPSHOTS:]):
        lines.append(f"| {pretty(k)} | " + " | ".join(f"{history[k][c]:+d}" for c in CURRENCIES) + " |")

    lines += [
        "", "## Sources", "",
        "- Derived internally from TradingView 4H-chart ZigZag Market Structure across "
        "`~/tradingview-mcp/forex_list.json`, computed by `scripts/tat_currency_strength_4h.py` "
        "from `~/tradingview-mcp/4H_brief/*.json`. Scoring reused from `scripts/tat_currency_strength.py`.", "",
    ]
    path = WIKI_ROOT / "wiki" / "notes" / "currency-strength-4h.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", action="store_true", help="run a live 4H tv scan first and save it as a new snapshot")
    args = ap.parse_args()

    if args.scan:
        key = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
        print(f"📡 Running live 4H structure scan -> {key}")
        if not scan(key):
            sys.exit("4H scan failed; not rewriting the note.")

    data = load_snapshots()
    keys = sorted(data)
    if not keys:
        sys.exit(f"No 4H snapshots in {BRIEF_DIR}. Run with --scan.")
    print(f"Found {len(keys)} 4H snapshots; latest {keys[-1]}")

    history = {k: calculate_strength(data[k])[0] for k in keys}
    recent = keys[-CHART_SNAPSHOTS:]
    chart_hist = {chart_label(k): history[k] for k in recent}
    generate_svg_chart(
        chart_hist, [chart_label(k) for k in recent],
        WIKI_ROOT / "wiki" / "images" / "currency-strength-4h-graph.svg", CURRENCIES,
        "Currency Strength Trend — 4H",
        "Aggregated score based on 4H ZigZag Market Structure (8 majors)",
    )
    write_note(keys, history, data, watchlist_major_pairs())


if __name__ == "__main__":
    main()
