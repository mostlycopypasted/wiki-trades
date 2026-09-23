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

from report_toc import build_toc

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


ECON_ROW_RE = re.compile(
    r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([\d:]+)\s*\|\s*(\S+)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|$",
    re.M,
)


def extract_todays_events(note_text, today_str):
    """Return today's rows from the economic-calendar note's This Week table."""
    m = re.search(r"## This Week High-Impact Events.*?\n\|.*?\n\|[-: |]+\n(.*?)(?=\n##|\Z)", note_text, re.S)
    if not m:
        return []
    rows = []
    for date, time, currency, event, forecast, previous, actual, detail in ECON_ROW_RE.findall(m.group(1)):
        if date == today_str:
            rows.append((time, currency, event, forecast, previous, actual, detail))
    rows.sort(key=lambda r: r[0])
    return rows


# Currency -> (bank name, keywords identifying that bank's policy events in the
# economic-calendar note's Event column).
BANK_KEYWORDS = {
    "USD": ("Fed", ("fed", "fomc")),
    "EUR": ("ECB", ("ecb",)),
    "GBP": ("BoE", ("boe",)),
    "JPY": ("BoJ", ("boj",)),
    "AUD": ("RBA", ("rba",)),
    "NZD": ("RBNZ", ("rbnz",)),
    "CAD": ("BoC", ("boc",)),
    "CHF": ("SNB", ("snb",)),
}
POLICY_EVENT_KEYWORDS = ("interest rate decision", "rate decision", "monetary policy statement",
                          "press conference", "minutes")

TALLY_ROW_RE = re.compile(
    r"^\|\s*(\S+)\s*\|\s*(.+?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+?)\s*\|$", re.M
)


def check_central_bank_tally_reminders(todays_events, tally_note_path, today_str):
    """Flag banks whose policy event fired today but whose tally row hasn't been
    updated since — a reminder that the conversational stance update was missed,
    not an automatic stance judgment."""
    if not tally_note_path.exists():
        return []
    tally_text = tally_note_path.read_text(encoding="utf-8")
    last_changed = {}
    m = re.search(r"## Current Stances.*?\n\|.*?\n\|[-: |]+\n(.*?)(?=\n##|\Z)", tally_text, re.S)
    if m:
        for bank, _stance, changed_date, _trigger in TALLY_ROW_RE.findall(m.group(1)):
            last_changed[bank] = changed_date

    reminders = []
    flagged_banks = set()
    for _time, currency, event, _forecast, _previous, actual, _detail in todays_events:
        bank_info = BANK_KEYWORDS.get(currency)
        if not bank_info:
            continue
        bank, keywords = bank_info
        event_lower = event.lower()
        is_policy_event = any(k in event_lower for k in keywords) and any(
            k in event_lower for k in POLICY_EVENT_KEYWORDS
        )
        # Require the actual value to have posted — a date match alone doesn't mean
        # the event has actually released yet (e.g. scheduled later today SGT), and
        # re-checking a bank's site before that wastes a fetch on nothing new.
        if not is_policy_event or bank in flagged_banks or not (actual and actual.strip() and actual.strip() != "—"):
            continue
        if last_changed.get(bank, "0000-00-00") < today_str:
            reminders.append(f"- ⚠️ **{bank}** — \"{event}\" fired today but the tally was last updated {last_changed.get(bank, 'never')}. Update `wiki/notes/central-bank-tally.md`.")
            flagged_banks.add(bank)
    return reminders


SENTIMENT_SUMMARY_RE = re.compile(
    r"## (.+?) Summary\n"
    r"Total articles analyzed: (\d+)\n"
    r"Positive: \d+ \(([\d.]+)%\)\n"
    r"Negative: \d+ \(([\d.]+)%\)\n"
    r"Neutral: \d+ \(([\d.]+)%\)"
)
SENTIMENT_OVERALL_RE = re.compile(
    r"## Overall Summary \(All Instruments\)\n"
    r"Total articles analyzed: (\d+)\n"
    r"Positive: \d+ \(([\d.]+)%\)\n"
    r"Negative: \d+ \(([\d.]+)%\)\n"
    r"Neutral: \d+ \(([\d.]+)%\)"
)


def summarize_sentiment_output(text):
    """Condense market_sentiment.py's full headline dump into a per-instrument table.
    The full headline+link detail lives in wiki/reports/market-sentiment/YYYY-MM-DD-market-sentiment.md
    (appended by market_sentiment.py itself); embedding it verbatim here would balloon
    the daily brief (19 instruments x up to ~70 links each)."""
    rows = SENTIMENT_SUMMARY_RE.findall(text)
    if not rows:
        return "No sentiment data returned."

    lines = ["| Instrument | Articles | Positive | Negative | Neutral |", "| :--- | :--- | :--- | :--- | :--- |"]
    for label, total, pos, neg, neu in rows:
        lines.append(f"| {label} | {total} | {pos}% | {neg}% | {neu}% |")

    overall = SENTIMENT_OVERALL_RE.search(text)
    if overall:
        total, pos, neg, neu = overall.groups()
        lines.append("")
        lines.append(f"**Overall ({total} articles)**: {pos}% Positive / {neg}% Negative / {neu}% Neutral")

    return "\n".join(lines)


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
    # Section number shifts (2. with Daily present, 1. without) — match either,
    # since prev_content is yesterday's report and may use the old numbering.
    m = re.search(r"### 🔥 \d+\..*?\n(.*?)(?=\n###|\Z)", text, re.S)
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

    # 1. Refresh the economic calendar (Red Folder events) and pull today's rows
    print("📰 1/9 Refreshing economic calendar (Red Folder events)...")
    econ_script = WIKI_ROOT / ".agents/skills/economic-calendar/scripts/pull_economic_calendar.py"
    run_command([sys.executable, str(econ_script)])
    econ_note_path = WIKI_ROOT / "wiki/notes/economic-calendar.md"
    econ_note_text = econ_note_path.read_text(encoding="utf-8") if econ_note_path.exists() else ""
    todays_events = extract_todays_events(econ_note_text, today_str)
    tally_note_path = WIKI_ROOT / "wiki/notes/central-bank-tally.md"
    tally_reminders = check_central_bank_tally_reminders(todays_events, tally_note_path, today_str)

    # 2. Run market sentiment scan (Google News RSS + VADER across the instrument set)
    print("🗞️ 2/9 Running market sentiment scan...")
    # This machine is Intel/x86_64 macOS, pinned to older transformers/numpy
    # (torch has no wheels past 2.2.2 for this platform) — use the x86 fork.
    # market_sentiment.py is the Apple Silicon original; keep both in sync.
    sentiment_script = WIKI_ROOT / "scripts/market_sentiment_x86.py"
    sentiment_output = run_command([sys.executable, str(sentiment_script)])

    # 3. Live TradingView Daily-chart ZigZag structure scan -> currency strength
    print("📡 3/9 Running live TradingView Daily-chart structure scan (tv brief)...")
    tv_session = WIKI_ROOT / "scripts/tv_session.sh"
    tv_brief_dump = Path(f"/tmp/tv_brief_{today_str}.json")
    run_command(["bash", str(tv_session), "start"])
    # The brief scans forex_list.json, not the 88-symbol rules.json superset: it is
    # a complete drop-in rules file (same schema, default_timeframe D, same layout
    # and bias_criteria) and it is the list the user actually curates. Keeping the
    # scan and the Daily Watchlist Signal Snapshot on one source means an added
    # symbol shows up in both instead of being silently dropped for lack of scan data.
    # --timeout-ms 600000: the CLI's own default (180s) is too short for a live
    # multi-symbol scan, which can legitimately run several minutes.
    run_command(["bash", "-c", f"cd ~/tradingview-mcp && node src/cli/index.js brief --timeout-ms 600000 -r ./forex_list.json > {tv_brief_dump}"])
    if not tv_brief_dump.exists() or tv_brief_dump.stat().st_size == 0:
        # run_command() discards the child's return code, so a timed-out/failed
        # brief scan would otherwise pass an empty file to build_daily_bias.py
        # silently and downstream steps would fall back to stale prior-day data
        # with no trace of why. Skip the call and say so instead.
        print("⚠️ tv brief scan timed out or produced no output — using stale daily-bias data")
    else:
        run_command([sys.executable, str(WIKI_ROOT / "scripts/build_daily_bias.py"), str(tv_brief_dump), "--date", today_str])
    run_command(["bash", str(tv_session), "stop"])

    print("📊 4/9 Computing Currency Strength from ZigZag structure...")
    cs_script = WIKI_ROOT / "scripts/tat_currency_strength.py"
    run_command([sys.executable, str(cs_script), "--date", today_str])

    # 5. Run 4H + 1H Alert Confluence Synthesis
    # The Daily timeframe is deliberately excluded (--no-daily): the Daily alert
    # sheet is owned by the Daily Signals skill (scan_daily_signals.py, 05:45 SGT).
    # The brief's own Daily view comes from the watchlist snapshot in step 7.
    print("📈 5/9 Running 4H + 1H TAT Alert Analysis...")
    analysis_script = WIKI_ROOT / "scripts/binni_alert_analysis.py"
    multi_output = run_command([sys.executable, str(analysis_script), "--timeframe", "3tf", "--no-daily"])

    # 6. Run D-R-H-R Scanner
    print("🎯 6/9 Scanning D-R-H-R Setups...")
    drhr_script = WIKI_ROOT / "scripts/scan_drhr_setups.py"
    drhr_output = run_command([sys.executable, str(drhr_script)])

    # 7. Watchlist TAT signal snapshot (forex_list.json — same list the scan used)
    # Reads the daily_brief/{date}.json already written in step 3 — no extra scan.
    print("🗺️ 7/9 Building watchlist TAT signal snapshot...")
    watchlist_script = WIKI_ROOT / "scripts/watchlist_signals.py"
    watchlist_output = run_command([sys.executable, str(watchlist_script), "--date", today_str])

    # 8. Read Currency Strength Note data
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

    # 9. Derive today's top setup from the actual D-R-H-R scan, and capture its chart
    setups = parse_drhr_setups(drhr_output)
    top = pick_top_setup(setups)
    if top:
        symbol, direction, score, conf_label, h1_sig, h1_time, event = top
        top_setup_line = f"⭐⭐⭐ **[[{symbol}]] {direction}** ({conf_label}, H1 Signal `{h1_sig}` at {h1_time})."
        print(f"📸 8/9 Capturing top setup chart for [[{symbol}]] 1H...")
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

    # Today's high-impact economic events table
    if todays_events:
        econ_rows = "\n".join(
            f"| {time} | {currency} | {event} | {forecast} | {previous} | {actual or '—'} | {detail} |"
            for time, currency, event, forecast, previous, actual, detail in todays_events
        )
        econ_section = f"""| Time (SGT) | Currency | Event | Forecast | Previous | Actual | Detail |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{econ_rows}"""
    else:
        econ_section = "No high-impact (Red Folder) economic events scheduled today."

    tally_reminder_section = (
        "\n".join(tally_reminders) if tally_reminders
        else "No stale tally entries — all today's central bank events are reflected in `wiki/notes/central-bank-tally.md`."
    )

    # 10. Build the Differences & Changes Highlights table entirely from parsed data (no fabricated narrative)
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

## 📰 Today's High-Impact Economic Events

{econ_section}

See [Economic Calendar](../../notes/economic-calendar.md) for the full This Week / Next Week schedule.

---

## 🏦 Central Bank Tally Reminders

{tally_reminder_section}

See [Central Bank Policy Tally](../../notes/central-bank-tally.md) for the current Hawkish/Dovish/Neutral stance per bank.

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

## 🗞️ Market Sentiment (News-Based)

{summarize_sentiment_output(sentiment_output)}

See [Market Sentiment](../../reports/market-sentiment/{today_str}-market-sentiment.md) for the full headline-level breakdown and news-flow summary.

---

## 📈 4H + 1H TAT Alert Synthesis

{multi_output.strip()}

---

## 🗺️ Daily Watchlist Signal Snapshot (forex_list.json)

_Current on-chart TAT signal state for every instrument in `forex_list.json`, read from the same live Daily scan that drove this brief. This is a **snapshot of standing signals**, not a fresh-signal feed — new Daily signals are tracked by the Daily Signals skill in [Daily Signals](../daily-signals/{today_str}_Daily_Signals.md)._

{watchlist_output.strip()}

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
- **Economic Calendar Refreshed**: `wiki/notes/economic-calendar.md`
- **Central Bank Tally Checked**: `wiki/notes/central-bank-tally.md`
- **Market Sentiment Report Updated**: `wiki/reports/market-sentiment/{today_str}-market-sentiment.md`
"""

    toc_block = build_toc(report_content)
    if toc_block:
        title_line, _, rest = report_content.partition("\n")
        report_content = f"{title_line}\n\n{toc_block}\n{rest.lstrip(chr(10))}"

    report_file.write_text(report_content, encoding="utf-8")
    print(f"✅ Daily Brief with Differences & Changes Highlights generated: {report_file}")
    return report_file, symbol, direction if top else None


if __name__ == "__main__":
    generate_daily_brief()
