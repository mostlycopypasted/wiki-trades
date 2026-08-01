#!/usr/bin/env python3
import json
import urllib.request

url = "https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?interval=1h&range=1d"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    result = data['chart']['result'][0]
    quote = result['indicators']['quote'][0]
    print("Raw open:", quote['open'][-5:])
    print("Raw close:", quote['close'][-5:])
