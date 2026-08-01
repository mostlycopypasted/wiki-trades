#!/usr/bin/env python3
import json
import sys
import os
from pathlib import Path
from collections import defaultdict
import datetime

# Target currencies and metals
CURRENCIES = ["AUD", "NZD", "GBP", "EUR", "USD", "CAD", "JPY"]
METALS = ["XAU", "XAG"]
ALL_TARGETS = CURRENCIES + METALS

COLOR_MAP = {
    "USD": "#22c55e",  # Vibrant Green
    "EUR": "#3b82f6",  # Vibrant Blue
    "GBP": "#8b5cf6",  # Purple
    "AUD": "#f59e0b",  # Amber / Gold-Orange
    "NZD": "#14b8a6",  # Teal
    "CAD": "#ef4444",  # Red
    "JPY": "#ec4899",  # Pink
    "XAU": "#eab308",  # Gold
    "XAG": "#94a3b8",  # Silver
}

def load_all_daily_briefs(brief_dir_path):
    brief_dir = Path(brief_dir_path)
    json_files = sorted(list(brief_dir.glob("*.json")))
    
    daily_data_by_date = {}
    for f in json_files:
        # Ignore test files
        if f.name.startswith("test"):
            continue
        date_str = f.stem
        try:
            with open(f, 'r') as fp:
                content = json.load(fp)
                if isinstance(content, list) and len(content) > 0:
                    daily_data_by_date[date_str] = content
        except Exception as e:
            print(f"Warning: Could not read {f.name}: {e}")
            
    return daily_data_by_date

def calculate_tat_strength(daily_items):
    scores = {c: 0 for c in ALL_TARGETS}
    counts = {c: 0 for c in ALL_TARGETS}
    
    for item in daily_items:
        if item.get("bias") == "error":
            continue
            
        raw_sym = item.get("symbol", "").split(":")[-1].upper()
        struct = str(item.get("structure", ""))
        bias = str(item.get("bias", "")).lower()
        
        # Determine directional score (+1 for bullish, -1 for bearish, 0 for neutral)
        direction = 0
        if struct == "Bullish" or bias == "bullish":
            direction = 1
        elif struct == "Bearish" or bias == "bearish":
            direction = -1
            
        if direction == 0:
            continue

        # Forex Pairs (6 characters)
        if len(raw_sym) == 6 and raw_sym not in ["XAUUSD", "XAGUSD"]:
            base = raw_sym[:3]
            quote = raw_sym[3:]
            
            if base in scores:
                scores[base] += direction
                counts[base] += 1
            if quote in scores:
                scores[quote] -= direction
                counts[quote] += 1
                
        # Gold (XAUUSD) & Silver (XAGUSD)
        elif raw_sym in ["XAUUSD", "XAGUSD"]:
            metal = raw_sym[:3]
            quote = raw_sym[3:]
            
            if metal in scores:
                scores[metal] += direction
                counts[metal] += 1
            if quote in scores:
                scores[quote] -= direction
                counts[quote] += 1

    return scores

def generate_svg_chart(history_scores, dates, output_path):
    width = 900
    height = 500
    padding_left = 60
    padding_right = 160
    padding_top = 60
    padding_bottom = 60

    plot_w = width - padding_left - padding_right
    plot_h = height - padding_top - padding_bottom

    # Find min and max score for scaling
    all_vals = []
    for d in dates:
        for c in ALL_TARGETS:
            all_vals.append(history_scores[d][c])

    min_val = min(all_vals) if all_vals else -10
    max_val = max(all_vals) if all_vals else 10
    
    # Expand scale symmetrically around 0
    bound = max(abs(min_val), abs(max_val), 5) + 1
    min_val, max_val = -bound, bound

    n_dates = len(dates)
    
    def get_x(idx):
        if n_dates <= 1:
            return padding_left + plot_w / 2
        return padding_left + (idx / (n_dates - 1)) * plot_w

    def get_y(val):
        # Inverse Y axis for SVG
        ratio = (val - min_val) / (max_val - min_val)
        return (padding_top + plot_h) - ratio * plot_h

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif;">')
    
    # Header Title
    svg.append(f'<text x="{padding_left}" y="35" fill="#f8fafc" font-size="20" font-weight="bold">TAT Currency &amp; Metals Strength Multi-Day Trend</text>')
    svg.append(f'<text x="{padding_left}" y="52" fill="#94a3b8" font-size="12">Aggregated score based on Daily TAT Market Structure &amp; Trend Bars</text>')

    # Horizontal Grid Lines & Y Axis Labels
    y_step = 2 if bound <= 8 else 4
    for val in range(min_val, max_val + 1, y_step):
        y = get_y(val)
        line_color = "#334155" if val != 0 else "#64748b"
        stroke_width = "1.5" if val == 0 else "1"
        dash = ' stroke-dasharray="4,4"' if val != 0 else ''
        svg.append(f'<line x1="{padding_left}" y1="{y}" x2="{padding_left + plot_w}" y2="{y}" stroke="{line_color}" stroke-width="{stroke_width}"{dash} />')
        svg.append(f'<text x="{padding_left - 10}" y="{y + 4}" fill="#94a3b8" font-size="11" text-anchor="end">{val:+} text-anchor="end"</text>'.replace(' text-anchor="end"', ''))

    # Vertical Date Grid Lines & X Axis Labels
    for idx, d in enumerate(dates):
        x = get_x(idx)
        svg.append(f'<line x1="{x}" y1="{padding_top}" x2="{x}" y2="{padding_top + plot_h}" stroke="#1e293b" stroke-width="1" />')
        short_date = d.split('-')[-2] + '/' + d.split('-')[-1]
        svg.append(f'<text x="{x}" y="{padding_top + plot_h + 20}" fill="#94a3b8" font-size="11" text-anchor="middle">{short_date}</text>')

    # Plot Lines for each Currency / Metal
    latest_date = dates[-1]
    sorted_targets = sorted(ALL_TARGETS, key=lambda c: history_scores[latest_date][c], reverse=True)

    for c in ALL_TARGETS:
        color = COLOR_MAP.get(c, "#cccccc")
        points = []
        for idx, d in enumerate(dates):
            val = history_scores[d][c]
            x = get_x(idx)
            y = get_y(val)
            points.append(f"{x:.1f},{y:.1f}")

        polyline_pts = " ".join(points)
        svg.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{polyline_pts}" stroke-linecap="round" stroke-linejoin="round" />')

        # Add data point circles
        for idx, d in enumerate(dates):
            val = history_scores[d][c]
            x = get_x(idx)
            y = get_y(val)
            svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}" stroke="#0f172a" stroke-width="1.5" />')

    # Legend Panel on the Right Side
    legend_x = padding_left + plot_w + 25
    legend_y_start = padding_top + 10

    svg.append(f'<rect x="{legend_x - 10}" y="{padding_top}" width="135" height="{len(ALL_TARGETS) * 28 + 20}" fill="#1e293b" rx="8" stroke="#334155" />')
    svg.append(f'<text x="{legend_x}" y="{legend_y_start}" fill="#cbd5e1" font-size="12" font-weight="bold">Currencies &amp; Metals</text>')

    for idx, c in enumerate(sorted_targets):
        ly = legend_y_start + 22 + (idx * 26)
        color = COLOR_MAP.get(c, "#cccccc")
        score = history_scores[latest_date][c]
        svg.append(f'<circle cx="{legend_x + 6}" cy="{ly - 4}" r="5" fill="{color}" />')
        svg.append(f'<text x="{legend_x + 20}" y="{ly}" fill="#f1f5f9" font-size="12" font-weight="500">{c}: <tspan fill="{color}" font-weight="bold">{score:+}</tspan></text>')

    svg.append('</svg>')
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write("\n".join(svg))
    print(f"📊 SVG Strength Chart generated at: {output_path}")

def main():
    brief_dir = "/Users/chriseah/tradingview-mcp/daily_brief"
    data_by_date = load_all_daily_briefs(brief_dir)
    
    dates = sorted(list(data_by_date.keys()))
    print(f"Found {len(dates)} Daily Brief dates: {', '.join(dates)}")
    
    history_scores = {}
    for d in dates:
        history_scores[d] = calculate_tat_strength(data_by_date[d])

    # Save SVG Chart
    svg_chart_path = Path("/Users/chriseah/obsidian/wiki-trades/wiki/reports/tat_currency_strength_chart.svg")
    generate_svg_chart(history_scores, dates, svg_chart_path)

    # Build Markdown Analysis Report
    report = []
    report.append("# 📈 TAT Currency & Metals Strength Matrix Report")
    report.append(f"**Generated Date**: 2026-07-26 | **Historical Window**: {dates[0]} to {dates[-1]} ({len(dates)} Session Briefs)\n")
    report.append("> This report aggregates Daily TAT Market Structure & Trend Bar readings across 36 forex pairs and precious metals ([[XAUUSD]], [[XAGUSD]]) to derive net currency and metal strength trends.\n")

    report.append("## 📊 1. Multi-Day Strength Trend Chart\n")
    report.append(f"![TAT Currency Strength Chart](file://{svg_chart_path})\n")
    
    report.append("## 🏆 2. Historical Daily Strength Matrix Table\n")
    
    header = "| Currency / Metal | " + " | ".join(f"**{d.split('-')[-2]}/{d.split('-')[-1]}**" for d in dates) + " | Latest Trend Bias |"
    sep = "| :--- | " + " | ".join(":---:" for _ in dates) + " | :--- |"
    
    report.append(header)
    report.append(sep)

    latest_d = dates[-1]
    sorted_targets = sorted(ALL_TARGETS, key=lambda c: history_scores[latest_d][c], reverse=True)

    for c in sorted_targets:
        row_scores = [f"{history_scores[d][c]:+}" for d in dates]
        cur_score = history_scores[latest_d][c]
        
        status = "🟢 Strongly Bullish" if cur_score >= 3 else ("🟢 Bullish" if cur_score > 0 else ("🔴 Strongly Bearish" if cur_score <= -3 else ("🔴 Bearish" if cur_score < 0 else "⚪ Neutral")))
        
        name_formatted = f"**{c}**" if c not in ["XAU", "XAG"] else f"⭐ **{c}**"
        report.append(f"| {name_formatted} | " + " | ".join(row_scores) + f" | {status} |")

    report.append("\n---\n")
    report.append("## 🔍 3. Current Strength Ranking & Divergence Analysis\n")
    
    report.append("### 🟢 Top Strongest Assets (Leaders)")
    for c in sorted_targets[:3]:
        score = history_scores[latest_d][c]
        report.append(f"* **{c}**: Net Score = **{score:+}** — Demonstrating high structural support across pair combinations.")

    report.append("\n### 🔴 Top Weakest Assets (Laggards)")
    for c in sorted_targets[-3:]:
        score = history_scores[latest_d][c]
        report.append(f"* **{c}**: Net Score = **{score:+}** — Experiencing heavy structural breakdown across pair combinations.")

    report.append("\n### ⚡ Asymmetric Divergence Trade Recommendations (High R:R)")
    report.append("The highest probability short-term setups occur when pairing the **Strongest Leaders** against the **Weakest Laggards**:\n")
    
    for strong in sorted_targets[:3]:
        for weak in sorted_targets[-3:]:
            diff = history_scores[latest_d][strong] - history_scores[latest_d][weak]
            if diff >= 4:
                pair1 = f"{strong}{weak}"
                pair2 = f"{weak}{strong}"
                if strong in ["XAU", "XAG"] or weak in ["XAU", "XAG"]:
                    if strong in ["XAU", "XAG"] and weak == "USD":
                        report.append(f"* **Long [[{strong}USD]]**: Score Diff = **+{diff}** (Strong {strong} [{history_scores[latest_d][strong]:+}] vs Weak USD [{history_scores[latest_d][USD]:+}])")
                else:
                    report.append(f"* **Long [[{strong}{weak}]]** (or Short [[{weak}{strong}]]): Net Score Gap = **+{diff}** (Strong {strong} [{history_scores[latest_d][strong]:+}] vs Weak {weak} [{history_scores[latest_d][weak]:+}])")

    full_md = "\n".join(report)
    print(full_md)

    report_file_path = Path("/Users/chriseah/obsidian/wiki-trades/wiki/reports/2026-07-26-tat-currency-strength-report.md")
    with open(report_file_path, 'w') as f:
        f.write(full_md)
    print(f"✅ Report saved to: {report_file_path}")

if __name__ == '__main__':
    main()
