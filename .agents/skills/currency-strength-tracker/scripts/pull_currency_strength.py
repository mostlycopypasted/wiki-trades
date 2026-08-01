import os
import re
import sys
import subprocess
import urllib.request
from datetime import datetime

# Resolve paths relative to script location
script_dir = os.path.dirname(os.path.abspath(__file__))
resources_dir = os.path.abspath(os.path.join(script_dir, "..", "resources"))
os.makedirs(resources_dir, exist_ok=True)

images_dir = os.path.abspath(os.path.join(script_dir, "..", "..", "..", "..", "wiki", "images"))
os.makedirs(images_dir, exist_ok=True)
notes_dir = os.path.abspath(os.path.join(script_dir, "..", "..", "..", "..", "wiki", "notes"))
os.makedirs(notes_dir, exist_ok=True)

csv_path = os.path.join(resources_dir, "currency_strength_history.csv")
svg_path = os.path.join(images_dir, "currency-strength-graph.svg")
note_path = os.path.join(notes_dir, "currency-strength.md")


import ssl

# 1. Fetch live page
url = "https://www.marketsmadeclear.com/Resources/Currency-Strength/Currency-Strength-Meter.aspx"
req = urllib.request.Request(
    url, 
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
)

try:
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=context) as response:
        html = response.read().decode('utf-8')
except Exception as e:
    print(f"Error fetching url: {e}")
    sys.exit(1)


# 2. Parse Date and Strengths
week_match = re.search(r'Currency Strength Meter readings for week starting\s+([\d.]+)', html)
if week_match:
    week_str = week_match.group(1)
    dt = datetime.strptime(week_str, "%d.%m.%Y")
    date_str = dt.strftime("%Y-%m-%d")
else:
    date_str = datetime.now().strftime("%Y-%m-%d")

currencies = ['Eur', 'Gbp', 'Aud', 'Nzd', 'Usd', 'Cad', 'Chf', 'Jpy']
data = {}
for cur in currencies:
    pattern = rf'id="ctl00_ctl00_mainContent_rightColumn_CurrencyMatrix_td{cur}For"[^>]*>[\s\n]*([+-]?\d+)'
    val_match = re.search(pattern, html, re.DOTALL)
    if val_match:
        data[cur.upper()] = int(val_match.group(1))
    else:
        pattern_fb = rf'id="ctl00_ctl00_mainContent_rightColumn_CurrencyMatrix_td{cur}For"[^>]*>\s*([+-]?\d+)\s*'
        val_match = re.search(pattern_fb, html)
        if val_match:
            data[cur.upper()] = int(val_match.group(1))
        else:
            data[cur.upper()] = 0

# Parse suggested trading pairs
def clean_pairs(text):
    if not text:
        return "None"
    cleaned = re.sub(r'<[^>]*>', ' ', text)
    cleaned = cleaned.replace('&nbsp;', ' ')
    pairs = re.findall(r'\b[A-Z]{6}\b', cleaned.upper())
    if not pairs:
        return "None"
    return ", ".join([f"[[{p}]]" for p in pairs])

trending_buys = "None"
trending_sells = "None"
counter_buys = "None"
counter_sells = "None"

tb_match = re.search(r'trending</span>\s+buys\s+this\s+week[^<]*</strong>[^<]*</div>[\s\n]*<div[^>]*>[\s\n]*(.*?)[\s\n]*</div>', html, re.DOTALL | re.IGNORECASE)
if tb_match:
    trending_buys = clean_pairs(tb_match.group(1))

ts_match = re.search(r'trending</span>\s+sells\s+this\s+week[^<]*</strong>[^<]*<br\s*/?>[\s\n]*(.*?)[\s\n]*</div>', html, re.DOTALL | re.IGNORECASE)
if ts_match:
    trending_sells = clean_pairs(ts_match.group(1))

cb_match = re.search(r'counter trend</span>\s+buys\s+this\s+week[^<]*</strong>[^<]*<br\s*/?>[\s\n]*(.*?)[\s\n]*</div>', html, re.DOTALL | re.IGNORECASE)
if cb_match:
    counter_buys = clean_pairs(cb_match.group(1))

cs_match = re.search(r'counter trend</span>\s+sells\s+this\s+week[^<]*</strong>[^<]*<br\s*/?>[\s\n]*(.*?)[\s\n]*</div>', html, re.DOTALL | re.IGNORECASE)
if cs_match:
    counter_sells = clean_pairs(cs_match.group(1))

# Auto-generate entity page for any missing suggested trading pair
def ensure_entity(ticker):
    slug = ticker.lower()
    entities_dir = os.path.abspath(os.path.join(script_dir, "..", "..", "..", "..", "wiki", "entities"))
    entity_path = os.path.join(entities_dir, f"{slug}.md")
    
    if not os.path.exists(entity_path):
        content = f"""---
kind: instrument
tags: [trading-instrument]
updated: {date_str}
sources: 1
---

# {ticker.upper()}

> {ticker.upper()} Forex Pair.

## Background

Tracked for trading setups and key technical levels.

## Key positions / contributions / events

- **{date_str}**: Suggested pair to trade based on Currency Strength Meter readings. (see [Currency Strength Tracker](../notes/currency-strength.md))

## Sources

- [Currency Strength Tracker](../notes/currency-strength.md)
"""
        with open(entity_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Created stub entity page for missing pair: {ticker}")
        
        # Update index.md for this new entity
        wiki_root = os.path.abspath(os.path.join(script_dir, "..", "..", "..", ".."))
        subprocess.run([
            "python3", "/Users/chriseah/.gemini/skills/llm-wiki-manager/scripts/update_index.py",
            "--path", wiki_root,
            "--category", "entities",
            "--title", ticker.upper(),
            "--page-path", f"wiki/entities/{slug}.md",
            "--summary", f"{ticker.upper()} Forex Pair."
        ], cwd=wiki_root)

# Resolve and ensure entities exist for all parsed pairs
all_tickers = []
for text in [trending_buys, trending_sells, counter_buys, counter_sells]:
    if text != "None":
        tickers = re.findall(r'[A-Z]{6}', text)
        all_tickers.extend(tickers)

for ticker in set(all_tickers):
    ensure_entity(ticker)

# 3. Read/Update CSV
csv_rows = []
if os.path.exists(csv_path):
    with open(csv_path, "r", encoding="utf-8") as f:
        csv_rows = [line.strip().split(",") for line in f.readlines() if line.strip()]

header = ["Date"] + [c.upper() for c in currencies]

if not csv_rows or csv_rows[0] != header:
    csv_rows = [header]

date_exists_idx = -1
for idx, row in enumerate(csv_rows):
    if idx > 0 and row[0] == date_str:
        date_exists_idx = idx
        break

if date_exists_idx == -1:
    new_row = [date_str] + [str(data[c.upper()]) for c in currencies]
    csv_rows.append(new_row)
    csv_rows_sorted = [csv_rows[0]] + sorted(csv_rows[1:], key=lambda x: x[0])
    with open(csv_path, "w", encoding="utf-8") as f:
        for row in csv_rows_sorted:
            f.write(",".join(row) + "\n")
    print(f"Updated CSV history with date {date_str}.")
else:
    csv_rows_sorted = [csv_rows[0]] + sorted(csv_rows[1:], key=lambda x: x[0])
    print(f"Date {date_str} exists in history. Regenerating SVG trend graph & note...")


print(f"Updated CSV history with date {date_str}.")

# 4. Generate SVG Graph
history_data = csv_rows_sorted[1:]
if not history_data:
    print("No history data to plot.")
    sys.exit(0)

width = 900
height = 500
padding_left = 60
padding_right = 160
padding_top = 50
padding_bottom = 60

chart_width = width - padding_left - padding_right
chart_height = height - padding_top - padding_bottom

y_min = -7
y_max = 7
def get_y_coord(val):
    val_clamped = max(y_min, min(y_max, val))
    pct = (val_clamped - y_min) / (y_max - y_min)
    return padding_top + chart_height - (pct * chart_height)

def get_x_coord(index, total):
    if total <= 1:
        return padding_left + chart_width / 2
    return padding_left + (index / (total - 1)) * chart_width

colors = {
    'EUR': '#f92472',
    'GBP': '#4caf50',
    'AUD': '#67daef',
    'NZD': '#e040fb',
    'USD': '#fd971e',
    'CAD': '#ae81ff',
    'CHF': '#890d4f',
    'JPY': '#fb71a3'
}

svg_lines = []
svg_lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background-color: #0f172a; font-family: Inter, system-ui, -apple-system, sans-serif;">')

svg_lines.append("""
<style>
  .grid-line { stroke: #334155; stroke-width: 1; stroke-dasharray: 4,4; }
  .axis-line { stroke: #475569; stroke-width: 1.5; }
  .axis-text { fill: #94a3b8; font-size: 11px; }
  .title-text { fill: #f8fafc; font-size: 16px; font-weight: 700; }
  .line-series { fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; transition: opacity 0.2s, stroke-width 0.2s; }
  .line-series:hover { stroke-width: 4; opacity: 1 !important; }
  .series-dot { stroke-width: 2; transition: r 0.2s; }
  .series-dot:hover { r: 6; }
  .legend-text { fill: #cbd5e1; font-size: 12px; font-weight: 500; cursor: pointer; }
  .legend-item:hover text { fill: #ffffff; }
</style>
""")

svg_lines.append(f'<text x="{padding_left}" y="30" class="title-text">Currency Strength Trend History</text>')

for y_val in range(y_min, y_max + 1, 2):
    y_coord = get_y_coord(y_val)
    svg_lines.append(f'<line x1="{padding_left}" y1="{y_coord}" x2="{width - padding_right}" y2="{y_coord}" class="grid-line" />')
    label_sign = "+" if y_val > 0 else ""
    svg_lines.append(f'<text x="{padding_left - 10}" y="{y_coord + 4}" text-anchor="end" class="axis-text">{label_sign}{y_val}</text>')

zero_y = get_y_coord(0)
svg_lines.append(f'<line x1="{padding_left}" y1="{zero_y}" x2="{width - padding_right}" y2="{zero_y}" class="axis-line" />')

num_dates = len(history_data)
for idx, row in enumerate(history_data):
    x_coord = get_x_coord(idx, num_dates)
    date_val = row[0]
    try:
        date_formatted = datetime.strptime(date_val, "%Y-%m-%d").strftime("%d/%m")
    except:
        date_formatted = date_val
    svg_lines.append(f'<text x="{x_coord}" y="{height - padding_bottom + 20}" text-anchor="middle" class="axis-text">{date_formatted}</text>')
    svg_lines.append(f'<line x1="{x_coord}" y1="{height - padding_bottom}" x2="{x_coord}" y2="{height - padding_bottom + 5}" class="axis-line" />')

for cur_idx, cur in enumerate(currencies):
    cur_upper = cur.upper()
    col = colors[cur_upper]
    points = []
    for idx, row in enumerate(history_data):
        val = int(row[cur_idx + 1])
        x_coord = get_x_coord(idx, num_dates)
        y_coord = get_y_coord(val)
        points.append((x_coord, y_coord, val))
    
    if len(points) > 1:
        path_d = f"M {points[0][0]} {points[0][1]}"
        for pt in points[1:]:
            path_d += f" L {pt[0]} {pt[1]}"
        svg_lines.append(f'<path d="{path_d}" class="line-series" stroke="{col}" id="series-{cur_upper}" />')
    
    for pt_idx, pt in enumerate(points):
        svg_lines.append(f'<circle cx="{pt[0]}" cy="{pt[1]}" r="4" fill="#0f172a" stroke="{col}" class="series-dot" id="dot-{cur_upper}-{pt_idx}"><title>{cur_upper}: {pt[2]} ({history_data[pt_idx][0]})</title></circle>')

legend_start_y = padding_top + 20
for cur_idx, cur in enumerate(currencies):
    cur_upper = cur.upper()
    col = colors[cur_upper]
    y_coord = legend_start_y + (cur_idx * 30)
    svg_lines.append(f'<circle cx="{width - padding_right + 30}" cy="{y_coord - 4}" r="6" fill="{col}" />')
    latest_val = int(history_data[-1][cur_idx + 1])
    latest_sign = "+" if latest_val > 0 else ""
    svg_lines.append(f'<g class="legend-item" onclick="var el=document.getElementById(\'series-{cur_upper}\'); if(el.style.opacity==\'0.1\'){{el.style.opacity=\'1\';}}else{{el.style.opacity=\'0.1\';}}"><text x="{width - padding_right + 45}" y="{y_coord}" class="legend-text">{cur_upper} ({latest_sign}{latest_val})</text></g>')

svg_lines.append('</svg>')

with open(svg_path, "w", encoding="utf-8") as f:
    f.write("\n".join(svg_lines))

print("SVG trend graph generated successfully.")

# 5. Generate dynamically updated wiki/notes/currency-strength.md
markdown_lines = f"""---
kind: note
tags: [trading-instrument, reference]
updated: {date_str}
sources: 1
---

# Currency Strength Tracker

Weekly currency strength meter readings and trend analysis compiled from marketsmadeclear.com.

![Currency Strength Trend Graph](../images/currency-strength-graph.svg)


## Latest Readings (Week of {date_str})

| Currency | Score | Trend Bias |
| :--- | :--- | :--- |
"""

sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)
for cur_upper, score in sorted_data:
    if score >= 3:
        bias = "Strongly Bullish"
    elif score > 0:
        bias = "Mildly Bullish"
    elif score == 0:
        bias = "Neutral"
    elif score >= -2:
        bias = "Mildly Bearish"
    elif score >= -3:
        bias = "Bearish"
    else:
        bias = "Strongly Bearish"
    score_sign = "+" if score > 0 else ""
    markdown_lines += f"| **{cur_upper}** | {score_sign}{score} | {bias} |\n"

markdown_lines += f"""
## Suggested Pairs to Trade (Week of {date_str})

- **Possible Trending Buys**: {trending_buys}
- **Possible Trending Sells**: {trending_sells}
- **Possible Counter Trend Buys**: {counter_buys}
- **Possible Counter Trend Sells**: {counter_sells}

## Sources

- [Markets Made Clear CSM](https://www.marketsmadeclear.com/Resources/Currency-Strength/Currency-Strength-Meter.aspx)
"""

with open(note_path, "w", encoding="utf-8") as f:
    f.write(markdown_lines)

# Fix relative link prefixes in index.md
wiki_root = os.path.abspath(os.path.join(script_dir, "..", "..", "..", ".."))
index_path = os.path.join(wiki_root, "wiki", "index.md")
if os.path.exists(index_path):
    with open(index_path, "r", encoding="utf-8") as f:
        idx_content = f.read()
    idx_content_fixed = re.sub(r'\]\(\.\./', '](', idx_content)
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(idx_content_fixed)

print("wiki/notes/currency-strength.md regenerated successfully with suggested trading pairs.")
