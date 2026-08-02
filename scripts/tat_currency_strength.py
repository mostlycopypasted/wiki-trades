#!/usr/bin/env python3
"""
Currency strength derived from TradingView Daily-chart ZigZag market structure.

Reads ~/tradingview-mcp/daily_brief/*.json (populated by scripts/build_daily_bias.py
from a live `tv brief` scan). Each symbol's `structure` field — Bullish / Bearish /
Squeeze / Expand — comes from the last 2 ZigZag pivot labels (HH/HL/LH/LL) on its
Daily chart. A pair's `structure` moves its base currency +1/base and -1/quote
(Bullish) or the reverse (Bearish); Squeeze/Expand contribute no directional score
but are tallied separately since they represent structure that hasn't confirmed a
clean trend (an in-progress "change of structure").

Writes:
  - wiki/notes/currency-strength.md            8 majors, consumed by generate_daily_brief.py
  - wiki/images/currency-strength-graph.svg     8-majors multi-day trend chart
  - wiki/reports/{date}-tat-currency-strength-report.md   deep dive: 8 majors + XAU/XAG,
    full-watchlist change-of-structure
  - wiki/reports/tat_currency_strength_chart.svg           deep-dive trend chart
"""
import argparse
import datetime
import json
from pathlib import Path

WIKI_ROOT = Path("/Users/chriseah/obsidian/wiki-trades")
BRIEF_DIR = Path.home() / "tradingview-mcp" / "daily_brief"
RULES_PATH = Path.home() / "tradingview-mcp" / "rules.json"

CURRENCIES = ["AUD", "NZD", "GBP", "EUR", "USD", "CAD", "CHF", "JPY"]
METALS = ["XAU", "XAG"]
ALL_TARGETS = CURRENCIES + METALS
KNOWN_CCY = set(CURRENCIES) | {"SGD", "CNH"}

COLOR_MAP = {
    "USD": "#22c55e",
    "EUR": "#3b82f6",
    "GBP": "#8b5cf6",
    "AUD": "#f59e0b",
    "NZD": "#14b8a6",
    "CAD": "#ef4444",
    "CHF": "#890d4f",
    "JPY": "#ec4899",
    "XAU": "#eab308",
    "XAG": "#94a3b8",
}


def load_all_daily_briefs(brief_dir_path):
    brief_dir = Path(brief_dir_path)
    json_files = sorted(brief_dir.glob("*.json"))

    daily_data_by_date = {}
    for f in json_files:
        if f.name.startswith("test"):
            continue
        date_str = f.stem
        try:
            with open(f, "r") as fp:
                content = json.load(fp)
                if isinstance(content, list) and len(content) > 0:
                    daily_data_by_date[date_str] = content
        except Exception as e:
            print(f"Warning: Could not read {f.name}: {e}")

    return daily_data_by_date


def clean_symbol(item):
    return str(item.get("symbol", "")).split(":")[-1].upper()


def calculate_strength(daily_items):
    """Returns per-target dicts: scores, pair_counts, squeeze_counts, expand_counts."""
    scores = {c: 0 for c in ALL_TARGETS}
    pair_counts = {c: 0 for c in ALL_TARGETS}
    squeeze_counts = {c: 0 for c in ALL_TARGETS}
    expand_counts = {c: 0 for c in ALL_TARGETS}

    for item in daily_items:
        if item.get("bias") == "error":
            continue

        raw_sym = clean_symbol(item)
        struct = str(item.get("structure", ""))

        if raw_sym in ("XAUUSD", "XAGUSD"):
            legs = [(raw_sym[:3], 1), (raw_sym[3:], -1)]
        elif len(raw_sym) == 6 and raw_sym[:3] in KNOWN_CCY and raw_sym[3:] in KNOWN_CCY:
            legs = [(raw_sym[:3], 1), (raw_sym[3:], -1)]
        else:
            continue

        direction = 1 if struct == "Bullish" else (-1 if struct == "Bearish" else 0)

        for ccy, sign in legs:
            if ccy not in scores:
                continue
            pair_counts[ccy] += 1
            if direction != 0:
                scores[ccy] += direction * sign
            elif struct == "Squeeze":
                squeeze_counts[ccy] += 1
            elif struct == "Expand":
                expand_counts[ccy] += 1

    return scores, pair_counts, squeeze_counts, expand_counts


def watchlist_major_pairs():
    """6-char forex symbols on the live watchlist made entirely of the 8 majors."""
    pairs = set()
    if not RULES_PATH.exists():
        return pairs
    try:
        rules = json.loads(RULES_PATH.read_text())
        symbols = rules.get("watchlist", rules) if isinstance(rules, dict) else rules
        for s in symbols:
            sym = str(s).split(":")[-1].upper()
            if len(sym) == 6 and sym[:3] in CURRENCIES and sym[3:] in CURRENCIES and sym[:3] != sym[3:]:
                pairs.add(sym)
    except Exception as e:
        print(f"Warning: could not read {RULES_PATH}: {e}")
    return pairs


def suggested_pairs(scores, major_pairs, min_gap=4):
    ranked = sorted(CURRENCIES, key=lambda c: scores[c], reverse=True)
    strong = ranked[:3]
    weak = list(reversed(ranked[-3:]))

    buys, sells, seen = [], [], set()
    for s in strong:
        for w in weak:
            if s == w:
                continue
            diff = scores[s] - scores[w]
            if diff < min_gap:
                continue
            sw, ws = f"{s}{w}", f"{w}{s}"
            if sw in major_pairs and sw not in seen:
                buys.append(f"[[{sw}]] (Score Diff: +{diff})")
                seen.add(sw)
            elif ws in major_pairs and ws not in seen:
                sells.append(f"[[{ws}]] (Score Diff: +{diff})")
                seen.add(ws)
    return buys, sells


def structure_changes(data_by_date, dates, symbol_filter=None):
    if len(dates) < 2:
        return [], None, None
    latest, prev = dates[-1], dates[-2]
    latest_map = {clean_symbol(i): i for i in data_by_date[latest]}
    prev_map = {clean_symbol(i): i for i in data_by_date[prev]}

    changes = []
    for sym, item in latest_map.items():
        if symbol_filter is not None and sym not in symbol_filter:
            continue
        old = prev_map.get(sym)
        if not old:
            continue
        old_struct = old.get("structure")
        new_struct = item.get("structure")
        if old_struct and new_struct and old_struct != new_struct:
            changes.append((sym, old_struct, new_struct))
    changes.sort(key=lambda c: c[0])
    return changes, prev, latest


def xml_escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_svg_chart(history_scores, dates, output_path, targets, title, subtitle):
    title, subtitle = xml_escape(title), xml_escape(subtitle)
    width, height = 900, 500
    padding_left, padding_right, padding_top, padding_bottom = 60, 160, 60, 60
    plot_w = width - padding_left - padding_right
    plot_h = height - padding_top - padding_bottom

    all_vals = [history_scores[d][c] for d in dates for c in targets]
    min_val = min(all_vals) if all_vals else -10
    max_val = max(all_vals) if all_vals else 10
    bound = max(abs(min_val), abs(max_val), 5) + 1
    min_val, max_val = -bound, bound

    n_dates = len(dates)

    def get_x(idx):
        if n_dates <= 1:
            return padding_left + plot_w / 2
        return padding_left + (idx / (n_dates - 1)) * plot_w

    def get_y(val):
        ratio = (val - min_val) / (max_val - min_val)
        return (padding_top + plot_h) - ratio * plot_h

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" '
           f'style="background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif;">']

    svg.append(f'<text x="{padding_left}" y="35" fill="#f8fafc" font-size="20" font-weight="bold">{title}</text>')
    svg.append(f'<text x="{padding_left}" y="52" fill="#94a3b8" font-size="12">{subtitle}</text>')

    y_step = 2 if bound <= 8 else 4
    for val in range(min_val, max_val + 1, y_step):
        y = get_y(val)
        line_color = "#334155" if val != 0 else "#64748b"
        stroke_width = "1.5" if val == 0 else "1"
        dash = ' stroke-dasharray="4,4"' if val != 0 else ""
        svg.append(f'<line x1="{padding_left}" y1="{y}" x2="{padding_left + plot_w}" y2="{y}" stroke="{line_color}" stroke-width="{stroke_width}"{dash} />')
        svg.append(f'<text x="{padding_left - 10}" y="{y + 4}" fill="#94a3b8" font-size="11" text-anchor="end">{val:+}</text>')

    for idx, d in enumerate(dates):
        x = get_x(idx)
        svg.append(f'<line x1="{x}" y1="{padding_top}" x2="{x}" y2="{padding_top + plot_h}" stroke="#1e293b" stroke-width="1" />')
        short_date = d.split("-")[-2] + "/" + d.split("-")[-1]
        svg.append(f'<text x="{x}" y="{padding_top + plot_h + 20}" fill="#94a3b8" font-size="11" text-anchor="middle">{short_date}</text>')

    latest_date = dates[-1]
    sorted_targets = sorted(targets, key=lambda c: history_scores[latest_date][c], reverse=True)

    for c in targets:
        color = COLOR_MAP.get(c, "#cccccc")
        points = []
        for idx, d in enumerate(dates):
            val = history_scores[d][c]
            points.append(f"{get_x(idx):.1f},{get_y(val):.1f}")
        svg.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{" ".join(points)}" stroke-linecap="round" stroke-linejoin="round" />')
        for idx, d in enumerate(dates):
            val = history_scores[d][c]
            svg.append(f'<circle cx="{get_x(idx):.1f}" cy="{get_y(val):.1f}" r="4" fill="{color}" stroke="#0f172a" stroke-width="1.5" />')

    legend_x = padding_left + plot_w + 25
    legend_y_start = padding_top + 10
    svg.append(f'<rect x="{legend_x - 10}" y="{padding_top}" width="135" height="{len(targets) * 28 + 20}" fill="#1e293b" rx="8" stroke="#334155" />')
    svg.append(f'<text x="{legend_x}" y="{legend_y_start}" fill="#cbd5e1" font-size="12" font-weight="bold">Currencies &amp; Metals</text>')
    for idx, c in enumerate(sorted_targets):
        ly = legend_y_start + 22 + (idx * 26)
        color = COLOR_MAP.get(c, "#cccccc")
        score = history_scores[latest_date][c]
        svg.append(f'<circle cx="{legend_x + 6}" cy="{ly - 4}" r="5" fill="{color}" />')
        svg.append(f'<text x="{legend_x + 20}" y="{ly}" fill="#f1f5f9" font-size="12" font-weight="500">{c}: <tspan fill="{color}" font-weight="bold">{score:+}</tspan></text>')

    svg.append("</svg>")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(svg), encoding="utf-8")
    print(f"📊 SVG chart written: {output_path}")


def bias_label(score):
    if score >= 3:
        return "Strongly Bullish"
    if score > 0:
        return "Mildly Bullish"
    if score == 0:
        return "Neutral"
    if score >= -2:
        return "Mildly Bearish"
    if score >= -3:
        return "Bearish"
    return "Strongly Bearish"


def write_currency_note(dates, history_scores, data_by_date, major_pairs):
    latest_d = dates[-1]
    scores = history_scores[latest_d]

    lines = [
        "---",
        "kind: note",
        "tags: [trading-instrument, reference]",
        f"updated: {latest_d}",
        "sources: 1",
        "---",
        "",
        "# Currency Strength Tracker",
        "",
        "Currency strength derived from TradingView Daily-chart ZigZag Market Structure "
        "(`ZigZag Multi [TradingFinder]` study) across the 8 major currencies, aggregated "
        f"from {len(major_pairs)} forex pairs on the live watchlist. Recomputed on every "
        f"Daily Brief run from `~/tradingview-mcp/daily_brief/{latest_d}.json`.",
        "",
        "![Currency Strength Trend Graph](../images/currency-strength-graph.svg)",
        "",
        "",
        f"## Latest Readings ({latest_d})",
        "",
        "| Currency | Score | Trend Bias |",
        "| :--- | :--- | :--- |",
    ]

    for cur in sorted(CURRENCIES, key=lambda c: scores[c], reverse=True):
        score = scores[cur]
        lines.append(f"| **{cur}** | {score:+d} | {bias_label(score)} |")

    buys, sells = suggested_pairs(scores, major_pairs)
    lines += [
        "",
        f"## Suggested Pairs to Trade ({latest_d})",
        "",
        f"- **Structure-Aligned Buys** (strong currency vs. weak currency, score gap ≥4): {', '.join(buys) if buys else 'None'}",
        f"- **Structure-Aligned Sells**: {', '.join(sells) if sells else 'None'}",
    ]

    changes, prev_d, _ = structure_changes(data_by_date, dates, symbol_filter=major_pairs)
    lines += ["", f"## Change of Structure Since Last Session ({prev_d} → {latest_d})" if prev_d else "## Change of Structure Since Last Session", ""]
    if not prev_d:
        lines.append("*No prior session data available for comparison.*")
    elif not changes:
        lines.append(f"*No structure changes detected among the 8 majors since {prev_d}.*")
    else:
        lines.append("| Pair | Previous Structure | Current Structure |")
        lines.append("| :--- | :--- | :--- |")
        for sym, old_s, new_s in changes:
            lines.append(f"| **{sym}** | {old_s} | {new_s} |")

    lines += [
        "",
        "## Sources",
        "",
        "- Derived internally from TradingView Daily-chart ZigZag Market Structure "
        "(`ZigZag Multi [TradingFinder]` study) across the 88-symbol watchlist "
        "(`~/tradingview-mcp/rules.json`), computed by `scripts/tat_currency_strength.py` "
        "from `~/tradingview-mcp/daily_brief/*.json`.",
        "",
    ]

    note_path = WIKI_ROOT / "wiki" / "notes" / "currency-strength.md"
    note_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Wrote {note_path}")


def write_deep_dive_report(dates, history_scores, data_by_date, pair_counts, squeeze_counts, expand_counts):
    latest_d = dates[-1]
    scores = history_scores[latest_d]

    report = [
        "# 📈 TAT Currency & Metals Strength Matrix Report",
        f"**Generated Date**: {latest_d} | **Historical Window**: {dates[0]} to {dates[-1]} ({len(dates)} Session Briefs)\n",
        "> This report aggregates Daily ZigZag Market Structure readings across 36 forex "
        "pairs and precious metals ([[XAUUSD]], [[XAGUSD]]) to derive net currency and "
        "metal strength trends.\n",
        "## 📊 1. Multi-Day Strength Trend Chart\n",
        "![TAT Currency Strength Chart](tat_currency_strength_chart.svg)\n",
        "## 🏆 2. Historical Daily Strength Matrix Table\n",
    ]

    header = "| Currency / Metal | " + " | ".join(f"**{d.split('-')[-2]}/{d.split('-')[-1]}**" for d in dates) + " | Latest Trend Bias |"
    sep = "| :--- | " + " | ".join(":---:" for _ in dates) + " | :--- |"
    report += [header, sep]

    sorted_targets = sorted(ALL_TARGETS, key=lambda c: scores[c], reverse=True)
    for c in sorted_targets:
        row_scores = [f"{history_scores[d][c]:+d}" for d in dates]
        name_formatted = f"**{c}**" if c not in METALS else f"⭐ **{c}**"
        report.append(f"| {name_formatted} | " + " | ".join(row_scores) + f" | {bias_label(scores[c])} |")

    report += ["\n---\n", "## 🔍 3. Current Strength Ranking & Divergence Analysis\n", "### 🟢 Top Strongest Assets (Leaders)"]
    for c in sorted_targets[:3]:
        report.append(f"* **{c}**: Net Score = **{scores[c]:+d}** — Squeeze: {squeeze_counts[c]}, Expand: {expand_counts[c]}, Pairs tracked: {pair_counts[c]}.")

    report.append("\n### 🔴 Top Weakest Assets (Laggards)")
    for c in sorted_targets[-3:]:
        report.append(f"* **{c}**: Net Score = **{scores[c]:+d}** — Squeeze: {squeeze_counts[c]}, Expand: {expand_counts[c]}, Pairs tracked: {pair_counts[c]}.")

    report.append("\n### ⚡ Asymmetric Divergence Trade Recommendations (High R:R)")
    report.append("The highest probability short-term setups occur when pairing the **Strongest Leaders** against the **Weakest Laggards**:\n")
    for strong in sorted_targets[:3]:
        for weak in sorted_targets[-3:]:
            if strong == weak:
                continue
            diff = scores[strong] - scores[weak]
            if diff < 4:
                continue
            if strong in METALS and weak == "USD":
                report.append(f"* **Long [[{strong}USD]]**: Score Diff = **+{diff}** (Strong {strong} [{scores[strong]:+d}] vs Weak USD [{scores['USD']:+d}])")
            elif strong not in METALS and weak not in METALS:
                report.append(f"* **Long [[{strong}{weak}]]** (or Short [[{weak}{strong}]]): Net Score Gap = **+{diff}** (Strong {strong} [{scores[strong]:+d}] vs Weak {weak} [{scores[weak]:+d}])")

    changes, prev_d, _ = structure_changes(data_by_date, dates)
    report.append("\n---\n")
    report.append("## 🔍 4. Change of Structure Since Last Session (Full 88-Symbol Watchlist)\n")
    if not prev_d:
        report.append("*No prior session data available for comparison.*")
    elif not changes:
        report.append(f"*No structure changes detected since {prev_d}.*")
    else:
        report.append(f"Comparing {prev_d} → {latest_d}:\n")
        report.append("| Symbol | Previous Structure | Current Structure |")
        report.append("| :--- | :--- | :--- |")
        for sym, old_s, new_s in changes:
            report.append(f"| **{sym}** | {old_s} | {new_s} |")

    full_md = "\n".join(report)
    report_file_path = WIKI_ROOT / "wiki" / "reports" / f"{latest_d}-tat-currency-strength-report.md"
    report_file_path.write_text(full_md, encoding="utf-8")
    print(f"✅ Deep-dive report saved to: {report_file_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=datetime.datetime.now().strftime("%Y-%m-%d"),
                         help="Informational label only; the data window is whatever dates exist in ~/tradingview-mcp/daily_brief/")
    parser.parse_args()

    data_by_date = load_all_daily_briefs(BRIEF_DIR)
    dates = sorted(data_by_date.keys())
    if not dates:
        print(f"No daily_brief data found in {BRIEF_DIR}. Run scripts/build_daily_bias.py first.")
        return
    print(f"Found {len(dates)} Daily Brief dates: {', '.join(dates)}")

    history_scores = {}
    pair_counts_by_date, squeeze_by_date, expand_by_date = {}, {}, {}
    for d in dates:
        scores, pair_counts, squeeze_counts, expand_counts = calculate_strength(data_by_date[d])
        history_scores[d] = scores
        pair_counts_by_date[d] = pair_counts
        squeeze_by_date[d] = squeeze_counts
        expand_by_date[d] = expand_counts

    latest_d = dates[-1]
    major_pairs = watchlist_major_pairs()

    # Majors-only chart + note (consumed by generate_daily_brief.py)
    generate_svg_chart(
        history_scores, dates, WIKI_ROOT / "wiki" / "images" / "currency-strength-graph.svg",
        CURRENCIES, "Currency Strength Trend History",
        "Aggregated score based on Daily ZigZag Market Structure (8 majors)",
    )
    write_currency_note(dates, history_scores, data_by_date, major_pairs)

    # Deep-dive: 8 majors + XAU/XAG, full-watchlist change-of-structure
    generate_svg_chart(
        history_scores, dates, WIKI_ROOT / "wiki" / "reports" / "tat_currency_strength_chart.svg",
        ALL_TARGETS, "TAT Currency & Metals Strength Multi-Day Trend",
        "Aggregated score based on Daily ZigZag Market Structure & Trend Bars",
    )
    write_deep_dive_report(dates, history_scores, data_by_date, pair_counts_by_date[latest_d], squeeze_by_date[latest_d], expand_by_date[latest_d])


if __name__ == "__main__":
    main()
