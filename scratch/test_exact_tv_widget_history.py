#!/usr/bin/env python3
import json
import urllib.request
import datetime

def fetch_tv_exact_chart_bar(symbol="EIGHTCAP:GBPAUD", timeframe="60"):
    """
    Fetch exact TradingView chart candles directly from TradingView's chart widget data feed.
    """
    now_ts = int(datetime.datetime.now().timestamp())
    from_ts = now_ts - 86400 * 2
    
    urls = [
        f"https://tvc4.forexpros.com/udf/data_feed/history?symbol={symbol}&resolution={timeframe}&from={from_ts}&to={now_ts}",
        f"https://widgetdata.tradingview.com/udf/data_feed/history?symbol={symbol}&resolution={timeframe}&from={from_ts}&to={now_ts}",
        f"https://price-api.tradingview.com/udf/data_feed/history?symbol={symbol}&resolution={timeframe}&from={from_ts}&to={now_ts}"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.tradingview.com/'
    }
    
    for url in urls:
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
                    print(f"=== SUCCESS FROM {url.split('/')[2]} ===")
                    for i in range(len(t)):
                        dt = datetime.datetime.fromtimestamp(t[i], tz=datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8)))
                        print(f"Bar [{i:02d}] {dt.strftime('%Y-%m-%d %H:%M SGT')} | O: {o[i]:.5f} | H: {h[i]:.5f} | L: {l[i]:.5f} | C: {c[i]:.5f}")
                    return data
        except Exception as e:
            pass
    print("❌ Could not connect to TV UDF endpoints directly.")
    return None

fetch_tv_exact_chart_bar("EIGHTCAP:GBPAUD", "60")
