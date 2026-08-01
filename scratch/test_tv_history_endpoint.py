#!/usr/bin/env python3
import json
import urllib.request
import datetime

def fetch_tv_chart_history(symbol="EIGHTCAP:GBPAUD", resolution="60"):
    """Fetch exact historical candles directly from TradingView chart endpoint."""
    now_ts = int(datetime.datetime.now().timestamp())
    from_ts = now_ts - (86400 * 2) # last 2 days
    
    # TV chart history endpoint
    url = f"https://benchmarks.tradingview.com/udf/data_feed/history?symbol={symbol}&resolution={resolution}&from={from_ts}&to={now_ts}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data and data.get('s') == 'ok':
                t = data['t']
                o = data['o']
                h = data['h']
                l = data['l']
                c = data['c']
                
                print(f"=== TRADINGVIEW {symbol} {resolution}m CHART HISTORY ===")
                for i in range(len(t)):
                    dt = datetime.datetime.fromtimestamp(t[i], tz=datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8)))
                    print(f"Bar [{i:02d}] {dt.strftime('%Y-%m-%d %H:%M SGT')} | O: {o[i]:.5f} | H: {h[i]:.5f} | L: {l[i]:.5f} | C: {c[i]:.5f}")
            else:
                print("TV History response:", data)
    except Exception as e:
        print(f"Error fetching TV history: {e}")

fetch_tv_chart_history("EIGHTCAP:GBPAUD", "60")
