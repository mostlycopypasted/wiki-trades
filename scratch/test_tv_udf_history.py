#!/usr/bin/env python3
import json
import urllib.request
import datetime

def fetch_tv_1h_history(symbol):
    """Fetch exact 1H candles directly from TradingView UDF history endpoint."""
    clean_sym = symbol.split(':')[-1].upper()
    tv_symbol = f"EIGHTCAP:{clean_sym}"
    
    # Try scanner column for 60m / 1h bar or UDF history
    url = f"https://scanner.tradingview.com/forex/scan"
    payload = {
        "symbols": {"tickers": [tv_symbol]},
        "columns": [
            "name",
            "open|60",
            "high|60",
            "low|60",
            "close|60",
            "open",
            "high",
            "low",
            "close"
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
                    'open_1h': vals[1],
                    'high_1h': vals[2],
                    'low_1h': vals[3],
                    'close_1h': vals[4],
                    'open_daily': vals[5],
                    'high_daily': vals[6],
                    'low_daily': vals[7],
                    'close_daily': vals[8]
                }
    except Exception as e:
        print(f"Error: {e}")
        return None

res = fetch_tv_1h_history("GBPAUD")
print("=== TRADINGVIEW SCANNER 1H COLUMNS TEST ===")
print(res)
