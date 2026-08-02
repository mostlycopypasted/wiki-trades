#!/usr/bin/env python3
"""
Master Daily Brief Generator Script
Automatically runs a live TradingView Daily-chart ZigZag structure scan to derive
currency strength, daily TAT alert analysis, 3TF synthesis, D-R-H-R setup scanner,
chart screenshot capture via capture_tv_chart.sh, compares results against the
previous Daily Brief report, and generates the complete Daily Brief report in
wiki/reports/daily_brief/YYYY-MM-DD.md.
"""

import sys
import os
import re
import datetime
import subprocess
from pathlib import Path

WIKI_ROOT = Path("/Users/chriseah/obsidian/wiki-trades")

CONF_LABELS = {
    3: "⭐ 3-TF Confluence (D1+H4+H1)",
    2: "✅ 2-TF Alignment (D1+H1)",
}

ENTRY_RE = re.compile(
    r"•\s*\[\[([A-Z0-9]+)\]\]\s*\|\s*(⭐ 3-TF Confluence \(D1\+H4\+H1\)|✅ 2-TF Alignment \(D1\+H1\))\s*\n"
    r"\s*- Closed Bar OHLC:.*\n"
    r"\s*- D1: .*?\|\s*H1 Signal:\s*(\S+)\s*at\s*([\d:]+)\s*\|\s*Event:\s*(.+)"
)


def run_command(cmd, cwd=WIKI_ROOT):
    print(f"🚀 Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    out = res.stdout
    clean_lines = [l for l in out.splitlines() if not l.startswith("  ℹ️") and not l.startswith("🔑") and not l.startswith("✅ Successfully")]
    return "\n".join(clean_lines).strip()


def get_previous_daily_brief(report_dir, today_str):
    brief_files = sorted(list(report_dir.glob("*.md")), reverse=True)
    for bf in brief_files:
        if bf.stem != today_str and re.match(r"^\d{4}-\d{2}-\d{2}$", bf.stem):
            return bf
    return None


def extract_top_setups(file_path):
    if not file_path or not file_path.exists():
        return "No previous report found."
    content = file_path.read_text(encoding="utf-8")
    m = re.search(r"Top Setup\*+:\s*(.*)", content)
    if m:
        return m.group(1).strip()
    return "Previous daily overview"


def parse_drhr_setups(text):
    """Return list of (symbol, direction, confluence_score, conf_label, h1_sig, h1_time, event)."""
    if "SHORT SETUPS" in text:
        long_block, short_block = text.split("SHORT SETUPS", 1)
    else:
        long_block, short_block = text, ""

    results = []
    for symbol, conf_label, h1_sig, h1_time, event in ENTRY_RE.findall(long_block):
        score = 3 if "3-TF" in conf_label else 2
        results.append((symbol, "Long", score, conf_label, h1_sig, h1_time, event.strip()))
    for symbol, conf_label, h1_sig, h1_time, event in ENTRY_RE.findall(short_block):
        score = 3 if "3-TF" in conf_label else 2
        results.append((symbol, "Short", score, conf_label, h1_sig, h1_time, event.strip()))
    return results


def pick_top_setup(setups):
    if not setups:
        return None
    return max(setups, key=lambda s: s[2])


def extract_drhr_counts(text):
    m = re.search(r"Found (\d+) Long Setups and (\d+) Short Setups", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def extract_dual_signal_count(text):
    m = re.search(r"### 🔥 2\..*?\n(.*?)(?=\n###|\Z)", text, re.S)
    if not m:
        return 0
    return len(re.findall(r"^\s*-\s*[🟢🔴]", m.group(1), re.M))


def extract_cs_extremes(text):
    rows = re.findall(r"\*\*([A-Z]{3})\*\*\s*\|\s*([+-]?\d+)\s*\|\s*([^\|\n]+)", text)
    if not rows:
        return None, None
    rows = [(c, int(s), b.strip()) for c, s, b in rows]
    strongest = max(rows, key=lambda x: x[1])
    weakest = min(rows, key=lambda x: x[1])
    return strongest, weakest


def capture_top_setup_screenshot(symbol, timeframe="60"):
    """Batch-launch TradingView, capture one chart for the top setup, then close. Returns relative image path or None."""
    img_dir = WIKI_ROOT / "wiki/images"
    before = set(img_dir.glob("*.png"))
    tv_session = WIKI_ROOT / "scripts/tv_session.sh"
    capture_script = WIKI_ROOT / "scripts/capture_tv_chart.sh"

    run_command(["bash", str(tv_session), "start"])
    run_command(["bash", str(capture_script), f"EIGHTCAP:{symbol}", timeframe])
    run_command(["bash", str(tv_session), "stop"])

    after = set(img_dir.glob("*.png"))
    new_files = sorted(after - before, key=lambda p: p.stat().st_mtime, reverse=True)
    if new_files:
        return f"../../images/{new_files[0].name}"

    # Fall back to the most recent existing screenshot for this symbol, if any.
    existing = sorted(img_dir.glob(f"*{symbol.lower()}*1h*.png"), reverse=True)
    if existing:
        return f"../../images/{existing[0].name}"
    return None


def generate_daily_brief():
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    now_sgt_str = datetime.datetime.now().strftime("%H:%M SGT")
    report_dir = WIKI_ROOT / "wiki/reports/daily_brief"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"{today_str}.md"

    # Find previous daily brief for diff comparison
    prev_brief = get_previous_daily_brief(report_dir, today_str)
    prev_date_str = prev_brief.stem if prev_brief else "Previous Session"
    prev_top_setup = extract_top_setups(prev_brief) if prev_brief else "N/A"
    prev_content = prev_brief.read_text(encoding="utf-8") if prev_brief else ""

    # 1. Live TradingView Daily-chart ZigZag structure scan -> currency strength
    print("📡 1/6 Running live TradingView Daily-chart structure scan (tv brief)...")
    tv_session = WIKI_ROOT / "scripts/tv_session.sh"
    tv_brief_dump = Path(f"/tmp/tv_brief_{today_str}.json")
    run_command(["bash", str(tv_session), "start"])
    run_command(["bash", "-c", f"cd ~/tradingview-mcp && node src/cli/index.js brief -r ./rules.json > {tv_brief_dump}"])
    run_command([sys.executable, str(WIKI_ROOT / "scripts/build_daily_bias.py"), str(tv_brief_dump), "--date", today_str])
    run_command(["bash", str(tv_session), "stop"])

    print("📊 2/6 Computing Currency Strength from ZigZag structure...")
    cs_script = WIKI_ROOT / "scripts/tat_currency_strength.py"
    run_command([sys.executable, str(cs_script), "--date", today_str])

    # 2. Run Daily Alert Analysis & 3TF Synthesis
    print("📈 3/6 Running Daily & 3TF TAT Alert Analysis...")
    analysis_script = WIKI_ROOT / "scripts/binni_alert_analysis.py"
    daily_output = run_command([sys.executable, str(analysis_script), "--timeframe", "DAILY"])
    multi_output = run_command([sys.executable, str(analysis_script), "--timeframe", "3tf"])

    # 3. Run D-R-H-R Scanner
    print("🎯 4/6 Scanning D-R-H-R Setups...")
    drhr_script = WIKI_ROOT / "scripts/scan_drhr_setups.py"
    drhr_output = run_command([sys.executable, str(drhr_script)])

    # 4. Read Currency Strength Note data
    cs_note_path = WIKI_ROOT / "wiki/notes/currency-strength.md"
    cs_table = ""
    if cs_note_path.exists():
        lines = cs_note_path.read_text().splitlines()
        table_lines = []
        capture = False
        for line in lines:
            if "## Latest Readings" in line:
                capture = True
                continue
            elif "## Suggested Pairs" in line:
                table_lines.append("\n### 💡 Suggested Currency Pair Setups\n")
                table_lines.append(line)
                continue
            elif "## Sources" in line:
                break
            if capture and line.strip():
                table_lines.append(line)
        cs_table = "\n".join(table_lines)

    # 5. Derive today's top setup from the actual D-R-H-R scan, and capture its chart
    setups = parse_drhr_setups(drhr_output)
    top = pick_top_setup(setups)
    if top:
        symbol, direction, score, conf_label, h1_sig, h1_time, event = top
        top_setup_line = f"⭐⭐⭐ **[[{symbol}]] {direction}** ({conf_label}, H1 Signal `{h1_sig}` at {h1_time})."
        print(f"📸 5/6 Capturing top setup chart for [[{symbol}]] 1H...")
        top_img_file = capture_top_setup_screenshot(symbol, "60")
        top_setup_section = f"""### {'🟢' if direction == 'Long' else '🔴'} [[{symbol}]] 1H Chart (Top D-R-H-R Setup — {conf_label})
![{symbol} 1H Chart Screenshot]({top_img_file if top_img_file else 'N/A'})""" if top_img_file else f"No screenshot captured for [[{symbol}]]."
    else:
        symbol = None
        top_setup_line = "No qualifying D-R-H-R setup found today."
        top_setup_section = "No qualifying setup to screenshot today."

    # Currency strength extremes (today vs previous)
    strongest, weakest = extract_cs_extremes(cs_table)
    if strongest:
        cs_summary_line = (
            f"Strongest: **{strongest[0]}** ({strongest[1]:+d}, {strongest[2]}) | "
            f"Weakest: **{weakest[0]}** ({weakest[1]:+d}, {weakest[2]})"
        )
    else:
        cs_summary_line = "Derived from live TradingView Daily-chart ZigZag structure (`tat_currency_strength.py`)."

    prev_strongest, prev_weakest = extract_cs_extremes(prev_content)
    prev_cs_str = f"{prev_strongest[0]} ({prev_strongest[1]:+d})" if prev_strongest else "N/A"
    curr_cs_str = f"{strongest[0]} ({strongest[1]:+d})" if strongest else "N/A"

    prev_long_n, prev_short_n = extract_drhr_counts(prev_content)
    curr_long_n, curr_short_n = extract_drhr_counts(drhr_output)
    prev_counts_str = f"{prev_long_n}L / {prev_short_n}S" if prev_long_n is not None else "N/A"
    curr_counts_str = f"{curr_long_n}L / {curr_short_n}S" if curr_long_n is not None else "N/A"
    if prev_long_n is not None and curr_long_n is not None:
        counts_shift = f"{curr_long_n - prev_long_n:+d} Long / {curr_short_n - prev_short_n:+d} Short"
    else:
        counts_shift = "N/A"

    prev_dual_n = extract_dual_signal_count(prev_content)
    curr_dual_n = extract_dual_signal_count(multi_output)

    # 6. Build the Differences & Changes Highlights table entirely from parsed data (no fabricated narrative)
    diff_rows = [
        ("Top Flagged Setup", prev_top_setup, top_setup_line, "See setup detail above"),
        ("Strongest Currency", prev_cs_str, curr_cs_str, "Mechanically derived from scoreboard"),
        ("D-R-H-R Setup Count", prev_counts_str, curr_counts_str, counts_shift),
        ("4H+1H Dual Signal Count", str(prev_dual_n), str(curr_dual_n), f"{curr_dual_n - prev_dual_n:+d}"),
    ]
    diff_table = "\n".join(
        f"| **{label}** | {prev} | {curr} | {shift} |" for label, prev, curr, shift in diff_rows
    )

    report_content = f"""# 📅 Daily Trading Brief — {today_str} [{now_sgt_str}]

## 📌 Executive Overview
- **Report Date**: {today_str}
- **Currency Strength Meter**: {cs_summary_line}
- **Top Setup**: {top_setup_line}

---

## 🔄 Differences & Changes Highlights (vs {prev_date_str} Brief)

| Metric / Focus Area | Previous Brief ({prev_date_str}) | Current Brief ({today_str}) | Shift |
| :--- | :--- | :--- | :--- |
{diff_table}

---

## 📊 Currency Strength Scoreboard & Trend Graph

![Currency Strength Trend Graph](../../images/currency-strength-graph.svg)

{cs_table}

---

## 📈 Daily & Multi-Timeframe TAT Alert Synthesis

{multi_output.strip()}

---

## 🎯 High-Probability D-R-H-R Reversal Setups

{drhr_output.strip()}

---

## 📸 Top Setup Chart Screenshot

{top_setup_section}

---

## 📚 Bookkeeping Discipline Applied
- **Daily Brief Filed**: `wiki/reports/daily_brief/{today_str}.md`
- **SVG Graph Output**: `wiki/images/currency-strength-graph.svg`
"""

    report_file.write_text(report_content, encoding="utf-8")
    print(f"✅ Daily Brief with Differences & Changes Highlights generated: {report_file}")
    return report_file, symbol, direction if top else None


if __name__ == "__main__":
    generate_daily_brief()
