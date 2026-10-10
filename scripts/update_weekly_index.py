#!/usr/bin/env python3
"""
update_weekly_index.py

Generates and refreshes the human-readable 'This Week's Reports' navigation section
at the very top of wiki/index.md.

Finds all reports generated during the current trading week (Monday to Sunday) across:
- 1H + 4H TAT Alert Analysis (wiki/reports/tat_analysis/)
- Daily Signals Snapshots (wiki/reports/daily-signals/)
- Daily Briefs (wiki/reports/daily_brief/)
- TAT Currency & Metals Strength Matrix (wiki/reports/)
- Market Sentiment Scans (wiki/reports/market-sentiment/)
- Equity News Scans (wiki/reports/equitynews/)

Usage:
  python3 scripts/update_weekly_index.py
  python3 scripts/update_weekly_index.py --date 2026-09-24
"""

import argparse
import datetime
import os
import re
import sys
from pathlib import Path

WIKI_ROOT = Path("/Users/chriseah/obsidian/wiki-trades")
INDEX_FILE = WIKI_ROOT / "wiki/index.md"
REPORTS_DIR = WIKI_ROOT / "wiki/reports"

START_MARKER = "<!-- WEEKLY_INDEX:START -->"
END_MARKER = "<!-- WEEKLY_INDEX:END -->"


def parse_args():
    parser = argparse.ArgumentParser(description="Update weekly reports index in wiki/index.md")
    parser.add_argument("--date", help="Reference date YYYY-MM-DD (defaults to today)")
    return parser.parse_args()


def extract_report_summary(fpath: Path, r_type: str) -> tuple[str, str]:
    """Extract (timestamp_str, summary_str) from a report markdown file."""
    if not fpath.exists():
        return "", ""

    txt = fpath.read_text(encoding="utf-8")
    clean_txt = re.sub(r"[\*\_]", "", txt)

    timestamps = re.findall(r"\[(\d\d:\d\d\s+SGT)\]", txt)
    t_str = timestamps[-1] if timestamps else ""
    if len(timestamps) > 1:
        time_label = f"{timestamps[0]} initial, latest {timestamps[-1]} update"
    elif timestamps:
        time_label = timestamps[0]
    else:
        time_label = ""

    summary = ""
    if r_type == "tat_analysis":
        m_1h = re.findall(r"1H\s+alert\s+volume\s+([^\n]+?\))", clean_txt, re.IGNORECASE)
        h1_info = ""
        if m_1h:
            m = re.search(r"(\d+)\s+prints[^\(]*\(([\d\w\s/]+)", m_1h[-1])
            if m:
                h1_info = f"1H {m.group(1)} prints ({m.group(2).strip()})"

        m_4h_cnt = re.findall(r"4H\s+alert\s+(?:state|volume)\s+.*?\s+(\d+)\s+prints", clean_txt, re.IGNORECASE)
        m_4h_bias = re.findall(r"4H\s+alert\s+(?:state|volume)\s+[^\(]*\(([\d\w\s/]+)", clean_txt, re.IGNORECASE)
        h4_info = ""
        if m_4h_cnt and m_4h_bias:
            h4_info = f"4H {m_4h_cnt[-1]} prints ({m_4h_bias[-1].strip()})"

        m_dual = re.search(r"(\d+)\s+(?:core\s+)?active\s+⭐⭐⭐\s+dual\s+alignments?", txt)
        dual_info = f"{m_dual.group(1)} ⭐⭐⭐ dual alignments" if m_dual else ""

        parts = [p for p in [h1_info, h4_info, dual_info] if p]
        summary = " • ".join(parts) if parts else "1H+4H Combined Review"

    elif r_type == "daily_signals":
        m = re.search(r"(\d+\s+total\s+(?:new\s+)?signals?[^\n]+?\))", clean_txt, re.IGNORECASE)
        sig_str = m.group(1).strip() if m else "Daily Signals scan"
        summary = f"{time_label} • {sig_str}" if time_label else sig_str

    elif r_type == "daily_brief":
        m_setup = re.search(r"Top Setup\*\*:\s*([^\n\(\)]+)", txt)
        setup_clean = re.sub(r"[\*\_]", "", m_setup.group(1)).strip() if m_setup else ""
        m_csm = re.search(r"Strongest:\s*\*\*([^\*]+)\*\*[^\n\|]*\|\s*Weakest:\s*\*\*([^\*]+)\*\*", txt)
        csm_info = f"CSM {m_csm.group(1).strip()} vs {m_csm.group(2).strip()}" if m_csm else ""
        brief_time = timestamps[0] if timestamps else time_label
        parts = [p for p in [brief_time, f"Top Setup: {setup_clean}" if setup_clean else "", csm_info] if p]
        summary = " • ".join(parts)

    elif r_type == "currency_strength":
        m_briefs = re.search(r"(\d+\s+Session Briefs)", txt)
        b_str = m_briefs.group(1) if m_briefs else ""
        m_strong = re.search(r"Top Strongest Assets.*?^\*\s+\*\*([A-Z]+)\*\*:\s+Net Score\s+=\s+\*\*([+-]?\d+)\*\*", txt, re.MULTILINE | re.DOTALL)
        m_weak = re.findall(r"^\*\s+\*\*([A-Z]+)\*\*:\s+Net Score\s+=\s+\*\*([+-]?\d+)\*\*", txt.split("Top Weakest Assets")[-1], re.MULTILINE)
        c_str = ""
        if m_strong and m_weak:
            c_str = f"{m_strong.group(1)} ({m_strong.group(2)}) vs {m_weak[-1][0]} ({m_weak[-1][1]})"
        parts = [p for p in [f"Daily ZigZag Matrix ({b_str})" if b_str else "Daily ZigZag Matrix", c_str] if p]
        summary = " • ".join(parts)

    elif r_type == "market_sentiment":
        m_run = re.search(r"##\s+🕒\s+Run\s+—\s+(\d\d:\d\d\s+SGT)\s+—\s+([^\n]+)", txt)
        if m_run:
            summary = f"{m_run.group(1)} • {m_run.group(2)}"
        else:
            summary = f"{time_label} • News sentiment scan" if time_label else "News sentiment scan"

    elif r_type == "equity_news":
        m = re.search(r"(\d+\s+Bullish\s*/\s*\d+\s+Bearish[^\n]+?\))", clean_txt)
        scan_info = m.group(1).strip() if m else "Sector alert scan"
        summary = f"{time_label} • {scan_info}" if time_label else scan_info

    return time_label, summary


def scan_reports_for_date(d_str: str) -> list[dict]:
    """Scan all standard report locations for a specific date string (YYYY-MM-DD)."""
    found = []

    # 1. 1H + 4H TAT Alert Report
    tat_path = REPORTS_DIR / "tat_analysis" / f"{d_str}-tat-alert-report.md"
    if tat_path.exists():
        t_str, summary = extract_report_summary(tat_path, "tat_analysis")
        found.append({
            "category": "1H + 4H TAT Alert Analysis",
            "title": f"1H + 4H TAT Alert Report ({t_str})" if t_str else "1H + 4H TAT Alert Report",
            "rel_path": str(tat_path.relative_to(WIKI_ROOT / "wiki")),
            "summary": summary
        })

    # 2. Daily Signals Snapshot
    ds_path = REPORTS_DIR / "daily-signals" / f"{d_str}_Daily_Signals.md"
    if ds_path.exists():
        t_str, summary = extract_report_summary(ds_path, "daily_signals")
        found.append({
            "category": "Daily Signals Snapshot",
            "title": f"Daily Signals Snapshot ({t_str})" if t_str else "Daily Signals Snapshot",
            "rel_path": str(ds_path.relative_to(WIKI_ROOT / "wiki")),
            "summary": summary
        })

    # 3. Daily Brief
    db_path = REPORTS_DIR / "daily_brief" / f"{d_str}.md"
    if db_path.exists():
        t_str, summary = extract_report_summary(db_path, "daily_brief")
        found.append({
            "category": "Daily Trading Brief",
            "title": f"Daily Brief ({t_str})" if t_str else "Daily Brief",
            "rel_path": str(db_path.relative_to(WIKI_ROOT / "wiki")),
            "summary": summary
        })

    # 4. TAT Currency Strength Matrix
    cs_path = REPORTS_DIR / f"{d_str}-tat-currency-strength-report.md"
    if cs_path.exists():
        t_str, summary = extract_report_summary(cs_path, "currency_strength")
        found.append({
            "category": "TAT Currency Strength Matrix",
            "title": "TAT Currency & Metals Strength Matrix",
            "rel_path": str(cs_path.relative_to(WIKI_ROOT / "wiki")),
            "summary": summary
        })

    # 5. Market Sentiment
    ms_path = REPORTS_DIR / "market-sentiment" / f"{d_str}-market-sentiment.md"
    if ms_path.exists():
        t_str, summary = extract_report_summary(ms_path, "market_sentiment")
        found.append({
            "category": "Market Sentiment Scan",
            "title": f"Market Sentiment Scan ({t_str})" if t_str else "Market Sentiment Scan",
            "rel_path": str(ms_path.relative_to(WIKI_ROOT / "wiki")),
            "summary": summary
        })

    # 6. Equity News Scan
    eq_path = REPORTS_DIR / "equitynews" / f"{d_str}_equity-news-scan.md"
    if eq_path.exists():
        t_str, summary = extract_report_summary(eq_path, "equity_news")
        found.append({
            "category": "Equity News Scan",
            "title": f"Equity News Scan ({t_str})" if t_str else "Equity News Scan",
            "rel_path": str(eq_path.relative_to(WIKI_ROOT / "wiki")),
            "summary": summary
        })

    return found


def build_weekly_index_markdown(ref_date: datetime.date) -> str:
    start_of_week = ref_date - datetime.timedelta(days=ref_date.weekday())
    end_of_week = start_of_week + datetime.timedelta(days=6)
    week_num = ref_date.isocalendar()[1]

    days = []
    curr = ref_date
    while curr >= start_of_week:
        days.append(curr)
        curr -= datetime.timedelta(days=1)

    today_str = ref_date.strftime("%Y-%m-%d")
    today_reports = scan_reports_for_date(today_str)

    lines = []
    lines.append(START_MARKER)
    lines.append(f"## 📅 This Week's Reports (Week {week_num}: {start_of_week.strftime('%Y-%m-%d')} to {end_of_week.strftime('%Y-%m-%d')})")
    lines.append("")
    lines.append("> **Quick Navigation**: Direct access to all active reports generated during the current trading week. Automatically updated as new reports and intraday updates are filed.")
    lines.append("")

    # 1. Latest Generated Reports (Today)
    day_name = ref_date.strftime("%A")
    lines.append(f"### 🕒 Latest Generated Reports (Today — {day_name}, {today_str})")
    lines.append("")
    if today_reports:
        for r in today_reports:
            desc = f" — {r['summary']}" if r["summary"] else ""
            lines.append(f"- **{r['category']}**: [{r['title']}]({r['rel_path']}){desc}")
    else:
        lines.append("_No reports generated yet today._")
    lines.append("")

    # 2. Archive by Day
    lines.append("### 📚 Weekly Report Archive by Day")
    lines.append("")

    for d in days:
        d_str = d.strftime("%Y-%m-%d")
        d_name = d.strftime("%A")
        r_list = scan_reports_for_date(d_str)
        is_today = " (Today)" if d == ref_date else ""
        lines.append(f"#### {d_name}, {d_str}{is_today} ({len(r_list)} report{'s' if len(r_list) != 1 else ''})")
        if r_list:
            for r in r_list:
                desc = f" — {r['summary']}" if r["summary"] else ""
                lines.append(f"- [{r['title']}]({r['rel_path']}){desc}")
        else:
            lines.append("- _No reports filed on this day._")
        lines.append("")

    lines.append("---")
    lines.append(END_MARKER)
    return "\n".join(lines)


def update_index_file(block_md: str) -> bool:
    if not INDEX_FILE.exists():
        sys.exit(f"❌ {INDEX_FILE} not found.")

    content = INDEX_FILE.read_text(encoding="utf-8")

    if START_MARKER in content and END_MARKER in content:
        pattern = re.compile(f"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", re.DOTALL)
        new_content = pattern.sub(block_md, content)
    else:
        if "## Sources" in content:
            new_content = content.replace("## Sources", f"{block_md}\n\n## Sources", 1)
        else:
            lines = content.split("\n")
            insert_idx = 0
            for idx, l in enumerate(lines):
                if l.startswith("# "):
                    insert_idx = idx + 2
                    break
            lines.insert(insert_idx, block_md + "\n")
            new_content = "\n".join(lines)

    INDEX_FILE.write_text(new_content, encoding="utf-8")
    return True


def main():
    args = parse_args()
    if args.date:
        ref_date = datetime.datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        ref_date = datetime.date.today()

    block_md = build_weekly_index_markdown(ref_date)
    update_index_file(block_md)
    print(f"✅ Successfully updated weekly reports index in {INDEX_FILE} for date {ref_date}")


if __name__ == "__main__":
    main()
