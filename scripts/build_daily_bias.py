#!/usr/bin/env python3
"""
Builds ~/tradingview-mcp/daily_brief/YYYY-MM-DD.json from a live `tv brief` scan.

`tv brief` (node src/cli/index.js brief) does NOT write this file itself — it only
dumps raw per-symbol indicator/label/quote data to stdout for an LLM to interpret.
scan_drhr_setups.py reads the daily_brief/{date}.json for each symbol's D1 `bias`
(bullish/bearish/neutral) and `structure` (display-only). Without this step the
scanner silently falls back to the most recent existing file, which can be days
stale.

Usage:
    cd ~/tradingview-mcp && node src/cli/index.js brief -r ./rules.json > /tmp/tv_brief.json
    python3 scripts/build_daily_bias.py /tmp/tv_brief.json [--date YYYY-MM-DD]

Note on the TAT trend fields: despite the naming, "Down Trend" is plotted as 1.0
when active and 0.0 when inactive (not -1.0 as the bias_criteria doc text implies).
Bullish = Up Trend == 1.0, Bearish = Down Trend == 1.0, else Neutral.
"""

import argparse
import datetime
import json
import re
from pathlib import Path

ALERT_RE = re.compile(r"(OptBull|LBull|SBull|OptBear|LBear|SBear)")


def load_brief_json(path):
    text = Path(path).read_text(encoding="utf-8")
    # tv brief prints a status line before the JSON and may be followed by an
    # "EXIT:<code>" marker if captured via `cmd > file; echo EXIT:$?`.
    if not text.lstrip().startswith("{"):
        text = text.split("\n", 1)[1]
    text = re.sub(r"\nEXIT:\d+\s*$", "", text)
    return json.loads(text)


def get_bias(symbol_entry):
    for study in symbol_entry.get("indicators", {}).get("studies", []):
        if study["name"].startswith("TATbyBinniOngv2"):
            values = study["values"]
            up = float(values.get("Up Trend", 0) or 0)
            down = float(values.get("Down Trend", 0) or 0)
            if up == 1.0:
                return "bullish"
            if down == 1.0:
                return "bearish"
            return "neutral"
    return "neutral"


def get_structure(symbol_entry):
    studies = symbol_entry.get("zigzagLabels", {}).get("studies", [{}])
    labels = studies[0].get("labels", []) if studies else []
    tags = [l["text"] for l in labels if l.get("text") in ("HH", "HL", "LH", "LL")]
    if len(tags) < 2:
        return "Squeeze"
    a, b = tags[-2], tags[-1]
    if {a, b} == {"HH", "HL"} or (a in ("HH", "HL") and b in ("HH", "HL")):
        return "Bullish"
    if {a, b} == {"LH", "LL"} or (a in ("LH", "LL") and b in ("LH", "LL")):
        return "Bearish"
    return "Squeeze"


def get_alert(symbol_entry):
    studies = symbol_entry.get("tatLabels", {}).get("studies", [{}])
    labels = studies[0].get("labels", []) if studies else []
    matches = [m.group(1) for l in labels for m in [ALERT_RE.search(l.get("text", ""))] if m]
    return matches[-1] if matches else ""


def build(brief_path, target_date):
    data = load_brief_json(brief_path)
    out = []
    for entry in data["symbols_scanned"]:
        quote = entry.get("quote", {})
        price = quote.get("close") or quote.get("last") or 0
        out.append({
            "symbol": entry["symbol"],
            "structure": get_structure(entry),
            "bias": get_bias(entry),
            "price": price,
            "alert": get_alert(entry),
        })

    out_dir = Path.home() / "tradingview-mcp" / "daily_brief"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{target_date}.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    bull = sum(1 for o in out if o["bias"] == "bullish")
    bear = sum(1 for o in out if o["bias"] == "bearish")
    neut = sum(1 for o in out if o["bias"] == "neutral")
    print(f"✅ Wrote {out_path} — {len(out)} symbols ({bull} bullish / {bear} bearish / {neut} neutral)")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("brief_json", help="Path to captured `tv brief` stdout")
    parser.add_argument("--date", default=datetime.datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    build(args.brief_json, args.date)


if __name__ == "__main__":
    main()
