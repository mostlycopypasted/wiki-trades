#!/usr/bin/env python3
import glob
import json
import os

files = sorted(glob.glob('/Users/chriseah/obsidian/wiki-trades/wiki/reports/daily_brief/2026-*.json'))
currencies = ['USD', 'EUR', 'GBP', 'AUD', 'NZD', 'CAD', 'CHF', 'JPY']

history = {}

for f in files:
    date_str = os.path.basename(f).replace('.json', '')
    data = json.load(open(f))
    if not isinstance(data, list):
        continue
    
    stats = {c: 0 for c in currencies}
    
    for item in data:
        sym = item.get('symbol', '').split(':')[-1]
        bias = item.get('bias', 'neutral')
        if not sym or bias == 'neutral' or bias == 'error':
            continue
        
        base, quote = None, None
        for c in currencies:
            if sym.startswith(c):
                rem = sym[len(c):]
                for q in currencies:
                    if rem == q:
                        base = c
                        quote = q
                        break
                if base:
                    break
        
        if base and quote:
            if bias == 'bullish':
                stats[base] += 1
                stats[quote] -= 1
            elif bias == 'bearish':
                stats[base] -= 1
                stats[quote] += 1
                
    history[date_str] = stats

dates = [d for d in sorted(history.keys()) if sum(abs(v) for v in history[d].values()) > 0][-5:]

# Generate Mermaid Line Chart
mermaid = [
    '### 📉 Multi-Day Currency Strength Trend Graph (Score Progression)\n',
    '```mermaid',
    'xychart-beta',
    '    title "Multi-Day Currency Strength Trend (Last 5 Sessions)"',
    f'    x-axis [{", ".join(dates)}]',
    '    y-axis "Score Points" -10 --> 10'
]
sorted_currs = sorted(currencies, key=lambda c: history[dates[-1]][c], reverse=True)

for c in sorted_currs[:5]:
    vals = [str(history[d][c]) for d in dates]
    mermaid.append(f'    line "{c}" [{", ".join(vals)}]')
mermaid.append('```\n')

# Generate Matrix Table
matrix = [
    '### 🗓️ 5-Day Currency Strength Score Matrix\n',
    f'| Currency | {" | ".join(dates)} | 5-Day Shift |',
    f'| :--- | {" | ".join([":---:"] * len(dates))} | :--- |'
]

for c in sorted_currs:
    scores = [f'{history[d][c]:+d}' for d in dates]
    diff = history[dates[-1]][c] - history[dates[0]][c]
    shift = f'🟢 Gain (+{diff})' if diff > 0 else (f'🔴 Loss ({diff})' if diff < 0 else '⚪ Stable')
    matrix.append(f'| **{c}** | {" | ".join(scores)} | {shift} |')

# Generate Today's Bar Chart
bar_chart = ['### 📈 Today\'s Relative Strength Bar Chart\n\n```text']
for c in sorted_currs:
    pts = history[dates[-1]][c]
    bar_len = abs(pts)
    if pts > 0:
        bar_str = '🟩 ' + '█' * bar_len + f' (+{pts})'
    elif pts < 0:
        bar_str = '🟥 ' + '░' * bar_len + f' ({pts})'
    else:
        bar_str = '⬜ █ (0)'
    bar_chart.append(f'{c:<4} | {bar_str}')
bar_chart.append('```\n')

full_section = "\n".join([
    "## 📊 Currency Strength Scoreboard & Multi-Day Trend Graph\n",
    "This scoreboard aggregates individual currency strengths based on their **ZigZag Market Structure** (pivot combinations) across 36 forex pairs.\n",
    "\n".join(mermaid),
    "\n".join(matrix),
    "\n".join(bar_chart)
])

print(full_section)

# Update latest md file
latest_md = f'/Users/chriseah/obsidian/wiki-trades/wiki/reports/daily_brief/{dates[-1]}.md'
if os.path.exists(latest_md):
    content = open(latest_md).read()
    if '## 📊 Currency Strength Scoreboard' in content:
        head = content.split('## 📊 Currency Strength Scoreboard')[0]
        tail = '### 🔍 Market Structure Insights' + content.split('### 🔍 Market Structure Insights')[1] if '### 🔍 Market Structure Insights' in content else ''
        new_content = head + full_section + '\n\n' + tail
        open(latest_md, 'w').write(new_content)
        print(f'\n✅ Successfully updated {latest_md} with Multi-Day Trend Graphs for 8 Core Majors!')
