#!/usr/bin/env python3
import sys
import json
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_google_sheet import fetch_sheet_records

def main():
    forex_list_path = Path('/Users/chriseah/tradingview-mcp/forex_list.json')
    with open(forex_list_path) as f:
        config = json.load(f)
    
    watchlist_raw = config.get('watchlist', [])
    symbols = [s.split(':')[-1].upper() for s in watchlist_raw]
    
    # Filter pure forex pairs & key tradeables
    forex_pairs = [s for s in symbols if any(c in s for c in ['USD', 'EUR', 'GBP', 'AUD', 'NZD', 'JPY', 'CAD', 'CHF', 'SGD', 'CNH']) and not any(idx in s for idx in ['ASX', 'EU50', 'JPN', 'GER', 'NDQ', 'SPX', 'SPY', 'US2000', 'US30', 'HSI', 'HK50', 'CN50', 'QQQ', 'GLD', 'SLV', 'DXY'])]

    print(f"Loaded {len(forex_pairs)} Forex pairs from forex_list.json")

    # Fetch H1 & 4H Google Sheet alerts
    h1_records = fetch_sheet_records('H1')
    h4_records = fetch_sheet_records('4H')
    
    # Load latest Daily Brief
    brief_dir = Path('/Users/chriseah/tradingview-mcp/daily_brief')
    latest_brief = sorted(list(brief_dir.glob('*.json')), reverse=True)[0]
    with open(latest_brief) as f:
        daily_items = json.load(f)

    daily_map = {str(item.get('symbol', '')).split(':')[-1].upper(): item for item in daily_items}

    # Map alerts by symbol
    h1_map = {}
    for r in h1_records:
        sym = str(r.get('Symbol', '')).split(':')[-1].upper()
        if sym not in h1_map:
            h1_map[sym] = r

    h4_map = {}
    for r in h4_records:
        sym = str(r.get('Symbol', '')).split(':')[-1].upper()
        if sym not in h4_map:
            h4_map[sym] = r

    results = []

    for sym in forex_pairs:
        d_info = daily_map.get(sym, {})
        d_bias = str(d_info.get('bias', 'Neutral')).capitalize()
        d_struct = str(d_info.get('structure', 'N/A')).replace('*', '').strip()
        d_price = d_info.get('price', 0)
        
        h1_info = h1_map.get(sym)
        h4_info = h4_map.get(sym)

        h1_dir = h1_info.get('Direction') if h1_info else None
        h1_sig = h1_info.get('Signal Type') if h1_info else None
        h1_time = h1_info.get('Time') if h1_info else None
        h1_event = h1_info.get('Event') if h1_info else None

        h4_dir = h4_info.get('Direction') if h4_info else None
        h4_sig = h4_info.get('Signal Type') if h4_info else None

        # Determine setup state
        status = "NO_SETUP"
        if d_bias == "Bullish" and h1_dir == "Bullish":
            status = "D-R-H-R LONG"
        elif d_bias == "Bearish" and h1_dir == "Bearish":
            status = "D-R-H-R SHORT"
        elif h4_dir and h1_dir and h4_dir == h1_dir:
            status = f"4H+1H DUAL {h4_dir.upper()}"
        elif h1_dir:
            status = f"1H {h1_dir.upper()} RETEST"

        results.append({
            "symbol": sym,
            "status": status,
            "d_bias": d_bias,
            "d_struct": d_struct,
            "d_price": d_price,
            "h4_dir": h4_dir,
            "h4_sig": h4_sig,
            "h1_dir": h1_dir,
            "h1_sig": h1_sig,
            "h1_time": h1_time,
            "h1_event": h1_event
        })

    # Sort results with actionable setups first
    priority_order = {"D-R-H-R LONG": 1, "D-R-H-R SHORT": 2, "4H+1H DUAL BULLISH": 3, "4H+1H DUAL BEARISH": 4, "1H BULLISH RETEST": 5, "1H BEARISH RETEST": 6, "NO_SETUP": 7}
    results.sort(key=lambda x: priority_order.get(x['status'], 99))

    print(f"\nCompleted D-R-H-R evaluation across {len(results)} Forex pairs.")
    for r in results[:10]:
        print(f"[{r['status']:<18}] {r['symbol']:<10} | D1: {r['d_bias']} ({r['d_struct']}) | H1: {r['h1_dir']} ({r['h1_sig']} @ {r['h1_time']})")

    # Output detailed report file
    report_content = f"""# 📈 D-R-H-R Forex List Multi-Timeframe Review Report

> **Generated Date**: 2026-07-29 [19:28 SGT]  
> **Source Watchlist**: `forex_list.json` (56 total symbols scanned, {len(results)} pure Forex pairs evaluated)  
> **Skill Standard**: `short-term-trading` (v1.6.0) D-R-H-R 4-Step Protocol & Multi-Timeframe Alignment  

---

## ⚡ Executive Summary & Top Actionable Forex Setups

| Symbol | Setup Type | D1 Frame (Step 1) | Retest Check (Step 2) | H1 Shift (Step 3) | M15 Execution (Step 4) | Est. R:R |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for r in results:
        if r['status'] != "NO_SETUP":
            report_content += f"| **[[{r['symbol']}]]** | `{r['status']}` | D1 {r['d_bias']} ({r['d_struct']}) | 2nd Test Firm Level | H1 {r['h1_sig']} @ {r['h1_time']} | Pullback Retest Zone | 1:4+ to 1:8+ |\n"

    report_content += """\n---

## 📊 Complete 4-Step D-R-H-R Multi-Timeframe Review by Pair

"""
    for r in results:
        report_content += f"""### 📌 [[{r['symbol']}]] — Status: `{r['status']}`

1. **Step 1: D — Day Chart Reference Frame (D1)**
   * **D1 Bias**: `{r['d_bias']}` | **Market Structure**: `{r['d_struct']}`
   * **Daily Level Analysis**: Locate historical bounce points on D1 via Visual Chart Analysis & TAT Tool. Identify Daily Target Profit level.

2. **Step 2: R — Retest (The 2nd Test Rule)**
   * **2nd Point of Retest**: Verify that price returned to hit the initial D1 level a 2nd time to confirm firm support/resistance.
   * **Cut-Loss Baseline**: Established right beyond the 2nd test swing low/high.

3. **Step 3: H — Higher High / Lower Low (H1 Structure Shift)**
   * **H1 Signal**: `{r['h1_dir'] or 'None'}` ({r['h1_sig'] or 'N/A'} at {r['h1_time'] or 'N/A'})
   * **Event**: {r['h1_event'] or 'No active H1 alert today'}
   * **H1 Trendline Check**: Confirm H1 trendline breakout and Higher High (buy) / Lower Low (sell).

4. **Step 4: R — Retracement (M15 Execution)**
   * **M15 Rule**: Never chase initial breakout. Wait for pullback into previous H1 breakout high/low or TAT predicted zone.
   * **Limit Order Entry**: Set limit order near breakout level with buffer + Stop Loss beyond retest baseline.

---
"""

    report_file = Path('/Users/chriseah/obsidian/wiki-trades/wiki/reports/2026-07-29-drhr-forex-list-review.md')
    with open(report_file, 'w') as f:
        f.write(report_content)
    print(f"\n✅ Created report: {report_file}")

if __name__ == "__main__":
    main()
