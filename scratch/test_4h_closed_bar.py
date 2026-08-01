#!/usr/bin/env python3
import json
import urllib.request
import datetime

def fetch_4h_closed_bar_exact(symbol="EIGHTCAP:EURAUD"):
    clean_sym = symbol.split(':')[-1].upper()
    ticker = f"{clean_sym}=X"
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1h&range=5d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quote = result['indicators']['quote'][0]
        
        now_sgt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
        
        bars = []
        for i in range(len(timestamps)):
            if quote['open'][i] is not None and quote['close'][i] is not None:
                dt = datetime.datetime.fromtimestamp(timestamps[i], tz=datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8)))
                bars.append({
                    'dt': dt,
                    'open': quote['open'][i],
                    'high': quote['high'][i],
                    'low': quote['low'][i],
                    'close': quote['close'][i]
                })
                
        # Group 1h bars into 4h blocks (17:00 to 21:00 SGT)
        # Find 1h bars from 17:00, 18:00, 19:00, 20:00 SGT today
        today_bars = [b for b in bars if b['dt'].strftime('%Y-%m-%d') == now_sgt.strftime('%Y-%m-%d')]
        bar_17 = next((b for b in today_bars if b['dt'].hour == 17), None)
        bar_18 = next((b for b in today_bars if b['dt'].hour == 18), None)
        bar_19 = next((b for b in today_bars if b['dt'].hour == 19), None)
        bar_20 = next((b for b in today_bars if b['dt'].hour == 20), None)
        
        if bar_17 and bar_20:
            open_4h = bar_17['open']
            high_4h = max(b['high'] for b in [bar_17, bar_18, bar_19, bar_20] if b)
            low_4h = min(b['low'] for b in [bar_17, bar_18, bar_19, bar_20] if b)
            close_4h = bar_20['close']
            
            print(f"=== EXACT 17:00 - 21:00 SGT 4H CLOSED CANDLE ({clean_sym}) ===")
            print(f"   • Open  (O) at 17:00 SGT : {open_4h:.5f}")
            print(f"   • High  (H)             : {high_4h:.5f}")
            print(f"   • Low   (L)             : {low_4h:.5f}")
            print(f"   • Close (C) at 21:00 SGT : {close_4h:.5f}")

fetch_4h_closed_bar_exact("EURAUD")
