#!/usr/bin/env python3
import json
import urllib.request

pairs = {
    "USDJPY": {"ticker": "USDJPY=X", "dir": "LONG", "d1_target": 166.50, "d1_support": 162.00, "h1_breakout": 163.40, "sl_buffer": 162.95},
    "GBPSGD": {"ticker": "GBPSGD=X", "dir": "LONG", "d1_target": 1.7380, "d1_support": 1.7080, "h1_breakout": 1.7140, "sl_buffer": 1.7090},
    "USDSGD": {"ticker": "USDSGD=X", "dir": "SHORT", "d1_target": 1.2850, "d1_resistance": 1.2940, "h1_breakout": 1.2935, "sl_buffer": 1.2955},
    "AUDUSD": {"ticker": "AUDUSD=X", "dir": "SHORT", "d1_target": 0.6650, "d1_resistance": 0.6750, "h1_breakout": 0.6720, "sl_buffer": 0.6738},
    "EURAUD": {"ticker": "EURAUD=X", "dir": "SHORT", "d1_target": 1.6150, "d1_resistance": 1.6420, "h1_breakout": 1.6360, "sl_buffer": 1.6425}
}

print("=== D-R-H-R FOREX CHART ANALYSIS & LIVE PRICING ===")
print("-" * 80)

for name, meta in pairs.items():
    ticker = meta["ticker"]
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=15m&range=5d"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            result = data['chart']['result'][0]
            chart_meta = result['meta']
            curr_price = chart_meta.get('regularMarketPrice')
            day_high = chart_meta.get('regularMarketDayHigh')
            day_low = chart_meta.get('regularMarketDayLow')
            
            direction = meta["dir"]
            if direction == "LONG":
                target = meta["d1_target"]
                entry_zone = f"{meta['h1_breakout'] - 0.0020:.4f} - {meta['h1_breakout']:.4f}" if "JPY" not in name else f"{meta['h1_breakout'] - 0.20:.2f} - {meta['h1_breakout']:.2f}"
                sl = meta["sl_buffer"]
                reward = abs(target - meta['h1_breakout'])
                risk = abs(meta['h1_breakout'] - sl)
                rr_ratio = reward / risk if risk > 0 else 0
            else:
                target = meta["d1_target"]
                entry_zone = f"{meta['h1_breakout']:.4f} - {meta['h1_breakout'] + 0.0020:.4f}" if "JPY" not in name else f"{meta['h1_breakout']:.2f} - {meta['h1_breakout'] + 0.20:.2f}"
                sl = meta["sl_buffer"]
                reward = abs(meta['h1_breakout'] - target)
                risk = abs(sl - meta['h1_breakout'])
                rr_ratio = reward / risk if risk > 0 else 0
                
            print(f"📌 [[{name}]] ({direction}): Current Price = {curr_price} | Day High = {day_high} | Day Low = {day_low}")
            print(f"   • Step 1 (Day Target): {target}")
            print(f"   • Step 2 (Firm Level): {meta.get('d1_support') or meta.get('d1_resistance')}")
            print(f"   • Step 3 (H1 Shift): Breakout Zone {meta['h1_breakout']}")
            print(f"   • Step 4 (Retracement Entry): Limit Zone [{entry_zone}] | SL: {sl}")
            print(f"   • Asymmetric Risk-to-Reward: 1:{rr_ratio:.1f} R:R\n")
    except Exception as e:
        print(f"❌ {name}: Failed to fetch chart data ({e})")
