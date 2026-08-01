#!/usr/bin/env python3
import json
import urllib.request
import datetime

def format_precision(val, symbol):
    if val is None:
        return "N/A"
    clean_sym = symbol.split(':')[-1].upper()
    # Only match JPY, Metals, Oil, and Indices for 2 decimal places
    if any(k in clean_sym for k in ["JPY", "XAU", "XAG", "USOUSD", "GER40", "CN50", "NDQ100", "SPX500", "US30", "HK50", "JPN225", "EU50"]):
        return f"{float(val):.2f}"
    else:
        return f"{float(val):.5f}"

def fetch_exact_closed_bar(symbol, timeframe="1h"):
    clean_sym = symbol.split(':')[-1].upper()
    ticker = f"{clean_sym}=X"
    if clean_sym == "XAUUSD":
        ticker = "GC=F"
    elif clean_sym == "XAGUSD":
        ticker = "SI=F"
    elif clean_sym == "USOUSD":
        ticker = "CL=F"

    tf_param = "1h" if timeframe.lower() in ["1h", "h1", "4h", "h4"] else "1d"
    
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={tf_param}&range=5d"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            result = data['chart']['result'][0]
            timestamps = result['timestamp']
            quote = result['indicators']['quote'][0]
            
            now_sgt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
            
            valid_bars = []
            for i in range(len(timestamps)):
                if quote['open'][i] is not None and quote['close'][i] is not None:
                    dt = datetime.datetime.fromtimestamp(timestamps[i], tz=datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8)))
                    # For 1H bars, only take bars that started BEFORE the current hour
                    if tf_param == '1h':
                        if dt.year == now_sgt.year and dt.month == now_sgt.month and dt.day == now_sgt.day and dt.hour >= now_sgt.hour:
                            continue
                    valid_bars.append({
                        'time_obj': dt,
                        'open': quote['open'][i],
                        'high': quote['high'][i],
                        'low': quote['low'][i],
                        'close': quote['close'][i]
                    })
                    
            if not valid_bars:
                return None

            last_closed = valid_bars[-1]
            time_str = last_closed['time_obj'].strftime('%Y-%m-%d %H:00 SGT (Last Closed 1H Bar)')
            return {
                'symbol': clean_sym,
                'bar_time': time_str,
                'open': format_precision(last_closed['open'], clean_sym),
                'high': format_precision(last_closed['high'], clean_sym),
                'low': format_precision(last_closed['low'], clean_sym),
                'close': format_precision(last_closed['close'], clean_sym)
            }
    except Exception as e:
        return None

symbols = ["GBPAUD", "EURUSD", "AUDNZD", "EURAUD", "USDSGD", "USDJPY", "XAUUSD"]

print("=== EXACT CLOSED 1H BAR OHLC (20:00 - 21:00 SGT CLOSED CANDLE) ===")
print(f"Current Local Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S SGT')}\n")

for sym in symbols:
    res = fetch_exact_closed_bar(sym, "1h")
    if res:
        print(f"📌 [[{res['symbol']}]] | {res['bar_time']}")
        print(f"   • Open  (O) : {res['open']}")
        print(f"   • High  (H) : {res['high']}")
        print(f"   • Low   (L) : {res['low']}")
        print(f"   • Close (C) : {res['close']}")
        print("-" * 75)
