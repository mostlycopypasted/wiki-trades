#!/usr/bin/env python3
import json
import urllib.request

def fetch_tradingview_eightcap_ohlc(symbol, timeframe="1h"):
    """Fetch exact EIGHTCAP broker OHLC data directly from TradingView API."""
    clean_sym = symbol.split(':')[-1].upper()
    tv_symbol = f"EIGHTCAP:{clean_sym}"
    
    url = "https://scanner.tradingview.com/forex/scan"
    payload = {
        "symbols": {"tickers": [tv_symbol]},
        "columns": [
            "name",
            "open",
            "high",
            "low",
            "close",
            "change"
        ]
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Content-Type': 'application/json'
    }
    
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data and 'data' in data and len(data['data']) > 0:
                vals = data['data'][0]['d']
                return {
                    'symbol': tv_symbol,
                    'open': vals[1],
                    'high': vals[2],
                    'low': vals[3],
                    'close': vals[4]
                }
    except Exception as e:
        print(f"Error fetching {tv_symbol}: {e}")
        return None

symbols = ["GBPAUD", "EURAUD", "AUDNZD", "USDSGD", "USDJPY", "XAUUSD"]

print("=== DIRECT TRADINGVIEW EIGHTCAP BROKER DATA ENGINE ===")
for sym in symbols:
    res = fetch_tradingview_eightcap_ohlc(sym)
    if res:
        print(f"📌 {res['symbol']}")
        print(f"   • Open  (O) : {res['open']:.5f}" if "JPY" not in sym and "XAU" not in sym else f"   • Open  (O) : {res['open']:.2f}")
        print(f"   • High  (H) : {res['high']:.5f}" if "JPY" not in sym and "XAU" not in sym else f"   • High  (H) : {res['high']:.2f}")
        print(f"   • Low   (L) : {res['low']:.5f}" if "JPY" not in sym and "XAU" not in sym else f"   • Low   (L) : {res['low']:.2f}")
        print(f"   • Close (C) : {res['close']:.5f}" if "JPY" not in sym and "XAU" not in sym else f"   • Close (C) : {res['close']:.2f}")
        print("-" * 65)
