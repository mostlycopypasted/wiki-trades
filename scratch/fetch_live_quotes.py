#!/usr/bin/env python3
import json
import urllib.request

symbols = {
    "GBPAUD": "GBPAUD=X",
    "AUDNZD": "AUDNZD=X",
    "EURAUD": "EURAUD=X",
    "USDSGD": "USDSGD=X"
}

print("Fetching live prices...")
for name, ticker in symbols.items():
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            meta = data['chart']['result'][0]['meta']
            price = meta.get('regularMarketPrice')
            prev_close = meta.get('previousClose')
            print(f"{name}: Current Price = {price} | Prev Close = {prev_close}")
    except Exception as e:
        print(f"{name}: Failed ({e})")
