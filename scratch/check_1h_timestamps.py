#!/usr/bin/env python3
import json
import urllib.request
import datetime

symbols = ["GBPAUD", "EURUSD", "USDJPY", "XAUUSD"]

for sym in symbols:
    ticker = f"{sym}=X" if "XAU" not in sym else "GC=F"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1h&range=1d"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quote = result['indicators']['quote'][0]
        
        print(f"=== {sym} Raw 1H Bars ===")
        for i in range(len(timestamps)):
            dt = datetime.datetime.fromtimestamp(timestamps[i], tz=datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8)))
            o = quote['open'][i]
            h = quote['high'][i]
            l = quote['low'][i]
            c = quote['close'][i]
            if o is not None:
                print(f"Bar [{i:02d}] {dt.strftime('%Y-%m-%d %H:%M SGT')} | O: {o:.5f} | H: {h:.5f} | L: {l:.5f} | C: {c:.5f}")
        print()
