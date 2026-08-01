#!/usr/bin/env python3
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.fetch_google_sheet import fetch_sheet_records

def analyze_xagusd():
    daily_file = Path('/Users/chriseah/tradingview-mcp/daily_brief/2026-07-24.json')
    daily_items = []
    if daily_file.exists():
        with open(daily_file) as f:
            daily_items = json.load(f)

    xag_d1 = next((i for i in daily_items if 'XAGUSD' in str(i.get('symbol') or i.get('name'))), {})

    h1_alerts = fetch_sheet_records('H1')
    h4_alerts = fetch_sheet_records('4H')

    xag_h1 = [a for a in h1_alerts if 'XAGUSD' in str(a.get('Symbol'))]
    xag_h4 = [a for a in h4_alerts if 'XAGUSD' in str(a.get('Symbol'))]

    print("=== D1 DAILY CHART (TRADINGVIEW MCP) ===")
    print(f"Symbol: {xag_d1.get('symbol') or xag_d1.get('name')}")
    print(f"Price: {xag_d1.get('price')}")
    print(f"Bias: {xag_d1.get('bias')}")
    print(f"Structure: {xag_d1.get('structure')}")
    print(f"Alert: {xag_d1.get('alert')}")

    print("\n=== LATEST H4 ALERTS ===")
    for a in xag_h4[:3]:
        print(f"Date: {a.get('Date')} {a.get('Time')} | Direction: {a.get('Direction')} | Signal: {a.get('Signal Type')} | Event: {a.get('Event')}")

    print("\n=== LATEST H1 ALERTS ===")
    for a in xag_h1[:5]:
        print(f"Date: {a.get('Date')} {a.get('Time')} | Direction: {a.get('Direction')} | Signal: {a.get('Signal Type')} | Event: {a.get('Event')}")

if __name__ == "__main__":
    analyze_xagusd()
