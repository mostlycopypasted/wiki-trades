import os
import re
import sys
import json
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# Resolve paths
script_dir = os.path.dirname(os.path.abspath(__file__))
wiki_root = os.path.abspath(os.path.join(script_dir, "..", "..", "..", ".."))
notes_dir = os.path.join(wiki_root, "wiki", "notes")
os.makedirs(notes_dir, exist_ok=True)

note_path = os.path.join(notes_dir, "economic-calendar.md")

now = datetime.now()
days_since_sunday = (now.weekday() + 1) % 7
this_week_start = (now - timedelta(days=days_since_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
this_week_end = this_week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

next_week_start = this_week_start + timedelta(days=7)
next_week_end = next_week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

# 1. Fetch "This Week" events from Forex Factory XML feed (Red Folder / High Impact only)
this_week_events = []
url_ff = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
req_ff = urllib.request.Request(
    url_ff, 
    headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
)

try:
    with urllib.request.urlopen(req_ff, timeout=15) as response:
        xml_data = response.read()
    root = ET.fromstring(xml_data)
    for event in root.findall('event'):
        impact = event.find('impact').text
        if impact == "High":  # Red Folder events only
            title = event.find('title').text
            country = event.find('country').text
            date_val = event.find('date').text
            time_val = event.find('time').text
            forecast = event.find('forecast').text if event.find('forecast') is not None else ""
            previous = event.find('previous').text if event.find('previous') is not None else ""
            detail_url = event.find('url').text if event.find('url') is not None else ""
            
            try:
                dt_str = f"{date_val} {time_val}"
                dt_utc = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                dt_sgt = dt_utc + timedelta(hours=8)
                date_sgt = dt_sgt.strftime("%Y-%m-%d")
                time_sgt = dt_sgt.strftime("%H:%M")
            except Exception:
                date_sgt = date_val
                time_sgt = time_val
                
            this_week_events.append({
                "date": date_sgt,
                "time": time_sgt,
                "currency": country,
                "event": title,
                "forecast": forecast if forecast is not None else "",
                "previous": previous if previous is not None else "",
                "url": detail_url if detail_url is not None else ""
            })
except Exception as e:
    print(f"Warning/Error fetching Forex Factory feed: {e}")

# Strict Red Folder Filter for TradingView API data
def is_red_folder_event(ev):
    if ev.get('importance') != 1:
        return False
    curr = ev.get('currency', '')
    country = ev.get('country', '')
    title = ev.get('title', '').lower()
    
    # Major currencies only
    if curr not in {'USD', 'EUR', 'GBP', 'JPY', 'AUD', 'NZD', 'CAD', 'CHF', 'CNY'}:
        return False
        
    # Exclude non-Red Folder event categories
    exclude_keywords = [
        'business climate', 'ifo', 'consumer confidence', 'gfk', 
        'durable goods', 'personal spending', 'personal income',
        'building permits', 'housing starts', 'factory orders',
        'trade balance', 'wholesale inventories', 'money supply'
    ]
    if any(k in title for k in exclude_keywords):
        return False
        
    # For EUR, exclude sub-country releases except Germany (DE) and Eurozone (EU) aggregate
    if curr == 'EUR' and country not in {'EU', 'DE'}:
        return False
        
    return True

# Function to fetch events from TradingView API for a date range with strict Red Folder filtering
def fetch_tradingview_red_folder_events(start_dt, end_dt):
    start_utc = (start_dt - timedelta(hours=8)).strftime("%Y-%m-%dT00:00:00.000Z")
    end_utc = (end_dt - timedelta(hours=8)).strftime("%Y-%m-%dT23:59:59.000Z")
    
    tv_url = f"https://economic-calendar.tradingview.com/events?from={start_utc}&to={end_utc}"
    req_tv = urllib.request.Request(
        tv_url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Origin': 'https://www.tradingview.com'
        }
    )
    
    tv_events = []
    try:
        with urllib.request.urlopen(req_tv, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8')).get('result', [])
            for ev in data:
                if is_red_folder_event(ev):
                    dt_utc = datetime.strptime(ev['date'], "%Y-%m-%dT%H:%M:%S.000Z")
                    dt_sgt = dt_utc + timedelta(hours=8)
                    if start_dt <= dt_sgt <= end_dt:
                        tv_events.append({
                            "date": dt_sgt.strftime("%Y-%m-%d"),
                            "time": dt_sgt.strftime("%H:%M"),
                            "currency": ev.get('currency', ''),
                            "event": ev.get('title', ''),
                            "forecast": str(ev.get('forecast')) if ev.get('forecast') is not None else "",
                            "previous": str(ev.get('previous')) if ev.get('previous') is not None else "",
                            "url": "https://www.tradingview.com/economic-calendar/"
                        })
    except Exception as e:
        print(f"Warning/Error fetching TradingView events: {e}")
        
    # Deduplicate
    unique = []
    seen = set()
    for ev in tv_events:
        key = (ev['date'], ev['time'], ev['currency'], ev['event'])
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    return unique

# If Forex Factory failed for this week, fallback to TradingView
if not this_week_events:
    print("Forex Factory feed failed or empty. Falling back to TradingView for This Week...")
    this_week_events = fetch_tradingview_red_folder_events(this_week_start, this_week_end)

# Sort this week events chronologically
this_week_events.sort(key=lambda x: (x["date"], x["time"], x["currency"]))

# 2. Fetch "Next Week" events from TradingView API (Red Folder only)
next_week_events = fetch_tradingview_red_folder_events(next_week_start, next_week_end)
next_week_events.sort(key=lambda x: (x["date"], x["time"], x["currency"]))

# 3. Create Markdown Content
date_str = now.strftime("%Y-%m-%d")
this_week_label = f"{this_week_start.strftime('%Y-%m-%d')} to {this_week_end.strftime('%Y-%m-%d')}"
next_week_label = f"{next_week_start.strftime('%Y-%m-%d')} to {next_week_end.strftime('%Y-%m-%d')}"

markdown_lines = f"""---
kind: note
tags: [session, reference]
updated: {date_str}
sources: 2
---

# Economic Calendar

Strict high-impact economic news releases (Red Folder events only) formatted in Singapore Time (SGT).

## This Week High-Impact Events ({this_week_label})

| Date | Time (SGT) | Currency | Event | Forecast | Previous | Detail |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""

for ev in this_week_events:
    curr = ev['currency']
    detail_link = f"[Detail]({ev['url']})" if ev['url'] else ""
    markdown_lines += f"| {ev['date']} | {ev['time']} | {curr} | {ev['event']} | {ev['forecast']} | {ev['previous']} | {detail_link} |\n"

markdown_lines += f"""
## Next Week High-Impact Events ({next_week_label})

| Date | Time (SGT) | Currency | Event | Forecast | Previous | Detail |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""

for ev in next_week_events:
    curr = ev['currency']
    detail_link = f"[Detail]({ev['url']})" if ev['url'] else ""
    markdown_lines += f"| {ev['date']} | {ev['time']} | {curr} | {ev['event']} | {ev['forecast']} | {ev['previous']} | {detail_link} |\n"

markdown_lines += """
## Sources

- [Forex Factory Calendar](https://www.forexfactory.com/calendar)
- [TradingView Economic Calendar](https://www.tradingview.com/economic-calendar/)
"""

with open(note_path, "w", encoding="utf-8") as f:
    f.write(markdown_lines)

print(f"Economic calendar updated successfully in wiki/notes/economic-calendar.md.")

# Update index.md
subprocess.run([
    "python3", "/Users/chriseah/.gemini/skills/llm-wiki-manager/scripts/update_index.py",
    "--path", wiki_root,
    "--category", "notes",
    "--title", "Economic Calendar",
    "--page-path", "wiki/notes/economic-calendar.md",
    "--summary", "Strict Red Folder economic news releases (This Week & Next Week) in SGT."
], cwd=wiki_root)

# Log the update
subprocess.run([
    "python3", "/Users/chriseah/.gemini/skills/llm-wiki-manager/scripts/append_log.py",
    "--path", wiki_root,
    "--action", "note",
    "--title", "Economic Calendar",
    "--details", "Updated economic calendar note to strictly include Red Folder events only for This Week & Next Week."
], cwd=wiki_root)

# Fix relative links in index.md
index_path = os.path.join(wiki_root, "wiki", "index.md")
if os.path.exists(index_path):
    with open(index_path, "r", encoding="utf-8") as f:
        idx_content = f.read()
    idx_content_fixed = re.sub(r'\]\(\.\./', '](', idx_content)
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(idx_content_fixed)

print("Index updated and log appended.")
