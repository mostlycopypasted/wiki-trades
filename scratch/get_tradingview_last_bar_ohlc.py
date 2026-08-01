#!/usr/bin/env python3
import json
import urllib.request
import datetime

symbols = {
    "GBPAUD": {"ticker": "GBPAUD=X", "type": "Active Long Trade (BE Secured @ 1.9070)"},
    "AUDNZD": {"ticker": "AUDNZD=X", "type": "Active Short Trade (BE Secured @ 1.2066)"},
    "EURAUD": {"ticker": "EURAUD=X", "type": "High-Prob ⭐⭐⭐ D-R-H-R Long Setup"},
    "USDSGD": {"ticker": "USDSGD=X", "type": "D-R-H-R Short Setup Zone"},
    "USDJPY": {"ticker": "USDJPY=X", "type": "D-R-H-R Long Setup Zone"},
    "XAUUSD": {"ticker": "GC=F",      "type": "Gold Breakout Watch (Level 4047)"}
}

print("=== REAL-TIME LAST BAR OHLC PRICE ENGINE (NO TRADINGVIEW GUI REQUIRED) ===")
print(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} SGT")
print("=" * 85)

for name, meta in symbols.items():
    ticker = meta["ticker"]
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1h&range=1d"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            result = data['chart']['result'][0]
            timestamps = result['timestamp']
            quote = result['indicators']['quote'][0]
            
            # Extract last closed/current 1H bar
            idx = -1
            open_p = quote['open'][idx]
            high_p = quote['high'][idx]
            low_p = quote['low'][idx]
            close_p = quote['close'][idx]
            bar_time = datetime.datetime.fromtimestamp(timestamps[idx]).strftime('%H:%M SGT')
            
            print(f"📌 [[{name}]] ({meta['type']})")
            print(f"   • Last Bar Timestamp : {bar_time}")
            print(f"   • Open  (O)           : {open_p:.5f}" if "JPY" not in name and "XAU" not in name else f"   • Open  (O)           : {open_p:.2f}")
            print(f"   • High  (H)           : {high_p:.5f}" if "JPY" not in name and "XAU" not in name else f"   • High  (H)           : {high_p:.2f}")
            print(f"   • Low   (L)           : {low_p:.5f}" if "JPY" not in name and "XAU" not in name else f"   • Low   (L)           : {low_p:.2f}")
            print(f"   • Close (C / Current) : {close_p:.5f}" if "JPY" not in name and "XAU" not in name else f"   • Close (C / Current) : {close_p:.2f}")
            print("-" * 85)
    except Exception as e:
        print(f"❌ {name}: Failed to fetch OHLC bar data ({e})")
