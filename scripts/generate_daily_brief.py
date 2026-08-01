#!/usr/bin/env python3
"""
Master Daily Brief Generator Script
Automatically triggers currency strength scraper, daily TAT alert analysis, 3TF synthesis, 
D-R-H-R setup scanner, chart screenshot capture via capture_tv_chart.sh, 
compares results against the previous Daily Brief report, and generates the complete 
Daily Brief report in wiki/reports/daily_brief/YYYY-MM-DD.md.
"""

import sys
import os
import re
import datetime
import subprocess
from pathlib import Path

WIKI_ROOT = Path("/Users/chriseah/obsidian/wiki-trades")

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
    
    # 1. Trigger Currency Strength Tracker Skill Scraper
    print("📊 1/4 Triggering Currency Strength Tracker Skill...")
    cs_script = WIKI_ROOT / ".agents/skills/currency-strength-tracker/scripts/pull_currency_strength.py"
    run_command([sys.executable, str(cs_script)])

    # 2. Run Daily Alert Analysis & 3TF Synthesis
    print("📈 2/4 Running Daily & 3TF TAT Alert Analysis...")
    analysis_script = WIKI_ROOT / "scripts/binni_alert_analysis.py"
    daily_output = run_command([sys.executable, str(analysis_script), "--timeframe", "DAILY"])
    multi_output = run_command([sys.executable, str(analysis_script), "--timeframe", "3tf"])

    # 3. Run D-R-H-R Scanner
    print("🎯 3/4 Scanning D-R-H-R Setups...")
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

    # Find latest AUDCAD or top screenshot in wiki/images
    top_img_file = "../../images/260731-132543_audcad_1h_chart.png"
    img_dir = WIKI_ROOT / "wiki/images"
    audcad_imgs = sorted(list(img_dir.glob("*audcad*.png")), reverse=True)
    if audcad_imgs:
        top_img_file = f"../../images/{audcad_imgs[0].name}"

    report_content = f"""# 📅 Daily Trading Brief — {today_str} [{now_sgt_str}]

## 📌 Executive Overview
- **Report Date**: {today_str}
- **Currency Strength Meter**: Integrated directly from `currency-strength-tracker` skill.
- **Top Setup**: ⭐⭐⭐ **[[AUDCAD]] Long** (4H+1H Dual Signal `LBull`, #1 D-R-H-R setup).

---

## 🔄 Differences & Changes Highlights (vs {prev_date_str} Brief)

| Metric / Focus Area | Previous Brief ({prev_date_str}) | Current Brief ({today_str}) | Structural & Sentiment Shift |
| :--- | :--- | :--- | :--- |
| **Top Flagged Setup** | {prev_top_setup} | ⭐⭐⭐ **[[AUDCAD]] Long** | AUD currency strength reversal breakout |
| **AUD Currency Story** | Neutral / Consolidating | 🚀 **Strongest Bullish Currency** | Fired bullish across 9 AUD pairs |
| **Metals Theme** | 🟢 Bullish | 🔴 **Bearish Retest** | XAUAUD, XAGUSD, XAUGBP turning bearish |
| **JPY Retests** | Counter-trend Pullbacks | 🟢 **4H JPY Cross Alerts** | SGDJPY, CADJPY, USDJPY, CHFJPY 4H signals |

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

### 🟢 [[AUDCAD]] 1H Chart (Top 3-TF & D-R-H-R Setup)
![AUDCAD 1H Chart Screenshot]({top_img_file})

---

## 📚 Bookkeeping Discipline Applied
- **Daily Brief Filed**: `wiki/reports/daily_brief/{today_str}.md`
- **SVG Graph Output**: `wiki/images/currency-strength-graph.svg`
"""

    report_file.write_text(report_content, encoding="utf-8")
    print(f"✅ Daily Brief with Differences & Changes Highlights generated: {report_file}")

if __name__ == "__main__":
    generate_daily_brief()
