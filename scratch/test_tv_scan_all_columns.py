#!/usr/bin/env python3
import json
import urllib.request
import datetime

url = "https://scanner.tradingview.com/forex/scan"
payload = {
    "symbols": {"tickers": ["EIGHTCAP:GBPAUD"]},
    "columns": [
        "name",
        "open|60", "high|60", "low|60", "close|60",
        "open|240", "high|240", "low|240", "close|240",
        "open", "high", "low", "close"
    ]
}
headers = {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'}
req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    vals = data['data'][0]['d']
    print("1H Scanner Column (open|60):", vals[1])
    print("1H High (high|60):", vals[2])
    print("1H Low (low|60):", vals[3])
    print("1H Close (close|60):", vals[4])
    print("4H Scanner Column (open|240):", vals[5])
    print("Daily Open (open):", vals[9])
