#!/usr/bin/env python3
import sys
import json
import argparse
import datetime
import urllib.request
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_google_sheet import fetch_sheet_records

def format_price_precision(val, symbol):
    """Format price preserving exact decimal precision (5 decimals for forex, 2 for JPY/gold/indices)."""
    if val is None:
        return "N/A"
    clean_sym = symbol.split(':')[-1].upper()
    if any(k in clean_sym for k in ["JPY", "XAU", "XAG", "USOUSD", "GER40", "CN50", "NDQ100", "SPX500", "US30", "HK50", "JPN225", "EU50"]):
        return f"{float(val):.2f}"
    else:
        return f"{float(val):.5f}"

def fetch_closed_bar_ohlc(symbol, timeframe="1h"):
    """
    Fetch exact EIGHTCAP broker CLOSED bar OHLC.
    - '1h': returns the last fully completed/closed 1-hour candle (e.g. 20:00-21:00 SGT bar).
    - '4h': returns the 17:00 SGT 4H candle (the 5 PM 4H bar that closed at 21:00 SGT).
    - '1d': returns the last fully completed/closed Daily candle.
    """
    clean_sym = symbol.split(':')[-1].upper()
    ticker = f"{clean_sym}=X"
    if clean_sym == "XAUUSD":
        ticker = "GC=F"
    elif clean_sym == "XAGUSD":
        ticker = "SI=F"
    elif clean_sym == "USOUSD":
        ticker = "CL=F"

    tf_param = "1h"
    range_param = "5d"

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={tf_param}&range={range_param}"
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
                    valid_bars.append({
                        'dt': dt,
                        'open': quote['open'][i],
                        'high': quote['high'][i],
                        'low': quote['low'][i],
                        'close': quote['close'][i]
                    })
                    
            if not valid_bars:
                return None

            tf_lower = timeframe.lower()
            if tf_lower in ["4h", "h4"]:
                # Aggregate 4H closed bar starting at 17:00 SGT (17:00, 18:00, 19:00, 20:00 SGT)
                today_bars = [b for b in valid_bars if b['dt'].strftime('%Y-%m-%d') == now_sgt.strftime('%Y-%m-%d')]
                bar_17 = next((b for b in today_bars if b['dt'].hour == 17), None)
                bar_18 = next((b for b in today_bars if b['dt'].hour == 18), None)
                bar_19 = next((b for b in today_bars if b['dt'].hour == 19), None)
                bar_20 = next((b for b in today_bars if b['dt'].hour == 20), None)

                if bar_17 and bar_20:
                    open_4h = bar_17['open']
                    high_4h = max(b['high'] for b in [bar_17, bar_18, bar_19, bar_20] if b)
                    low_4h = min(b['low'] for b in [bar_17, bar_18, bar_19, bar_20] if b)
                    close_4h = bar_20['close']
                    return {
                        'tf': '4H',
                        'bar_time': '17:00 - 21:00 SGT 4H Closed Candle',
                        'open': open_4h,
                        'high': high_4h,
                        'low': low_4h,
                        'close': close_4h
                    }

            # 1H Closed Bar (Filter out current hour)
            past_h1 = [b for b in valid_bars if not (b['dt'].year == now_sgt.year and b['dt'].month == now_sgt.month and b['dt'].day == now_sgt.day and b['dt'].hour >= now_sgt.hour)]
            if past_h1:
                last_h1 = past_h1[-1]
                return {
                    'tf': '1H',
                    'bar_time': last_h1['dt'].strftime('%Y-%m-%d %H:00 SGT'),
                    'open': last_h1['open'],
                    'high': last_h1['high'],
                    'low': last_h1['low'],
                    'close': last_h1['close']
                }

    except Exception:
        pass

    return None

def scan_drhr_watchlist(target_date=None, custom_watchlist_file=None, timeframe="1h"):
    if not target_date:
        target_date = datetime.date.today().strftime('%Y-%m-%d')
        
    daily_file = Path(f'/Users/chriseah/tradingview-mcp/daily_brief/{target_date}.json')
    daily_data = []
    if daily_file.exists():
        with open(daily_file) as f:
            daily_data = json.load(f)
    else:
        brief_dir = Path('/Users/chriseah/tradingview-mcp/daily_brief')
        json_files = sorted(list(brief_dir.glob('*.json')), reverse=True)
        if json_files:
            daily_file = json_files[0]
            with open(daily_file) as f:
                daily_data = json.load(f)

    filter_symbols = None
    if custom_watchlist_file:
        custom_path = Path(custom_watchlist_file)
        if custom_path.exists():
            with open(custom_path) as cf:
                c_data = json.load(cf)
                if isinstance(c_data, list):
                    filter_symbols = set(s.split(':')[-1].upper() for s in c_data)
                elif isinstance(c_data, dict) and 'watchlist' in c_data:
                    filter_symbols = set(s.split(':')[-1].upper() for s in c_data['watchlist'])
            print(f"🔍 Filtered watchlist by custom file: {custom_path.name} ({len(filter_symbols)} symbols)")

    h1_alerts = fetch_sheet_records('H1')
    h4_alerts = fetch_sheet_records('4H')
    
    h1_today = [r for r in h1_alerts if r.get('Date') == target_date]
    h4_today = [r for r in h4_alerts if r.get('Date') == target_date]
    
    if not h1_today and h1_alerts:
        target_date = h1_alerts[0].get('Date')
        h1_today = [r for r in h1_alerts if r.get('Date') == target_date]
        h4_today = [r for r in h4_alerts if r.get('Date') == target_date]

    daily_items = daily_data if isinstance(daily_data, list) else daily_data.get('results', [])
    
    daily_symbols = {}
    for item in daily_items:
        raw_sym = item.get('symbol') or item.get('name') or ''
        clean_sym = str(raw_sym).split(':')[-1].upper()
        if clean_sym:
            if filter_symbols is None or clean_sym in filter_symbols:
                daily_symbols[clean_sym] = item

    h1_by_sym = {str(a.get('Symbol', '')).split(':')[-1].upper(): a for a in h1_today}
    h4_by_sym = {str(a.get('Symbol', '')).split(':')[-1].upper(): a for a in h4_today}

    long_setups = []
    short_setups = []

    for sym, d_info in daily_symbols.items():
        d_bias = str(d_info.get('bias', '')).capitalize()
        d_struct = str(d_info.get('structure', '')).replace('*', '').strip()
        
        h1_a = h1_by_sym.get(sym)
        h4_a = h4_by_sym.get(sym)
        
        h1_dir = h1_a.get('Direction') if h1_a else None
        h1_sig = h1_a.get('Signal Type') if h1_a else None
        h1_time = h1_a.get('Time') if h1_a else None
        h1_event = h1_a.get('Event') if h1_a else None
        h4_dir = h4_a.get('Direction') if h4_a else None

        effective_bias = d_bias
        if h4_dir and h1_dir and h4_dir == h1_dir:
            effective_bias = h4_dir

        closed_ohlc = fetch_closed_bar_ohlc(sym, timeframe)
        close_price = closed_ohlc['close'] if closed_ohlc else d_info.get('price', 0)

        if effective_bias == 'Bullish' and h1_dir == 'Bullish':
            score_confluence = 3 if h4_dir == 'Bullish' else 2
            long_setups.append({
                'symbol': sym,
                'd_bias': d_bias,
                'd_struct': d_struct,
                'h1_sig': h1_sig,
                'h1_time': h1_time,
                'h4_dir': h4_dir,
                'close_price': close_price,
                'ohlc': closed_ohlc,
                'event': h1_event,
                'confluence': score_confluence
            })
            
        elif effective_bias == 'Bearish' and h1_dir == 'Bearish':
            score_confluence = 3 if h4_dir == 'Bearish' else 2
            short_setups.append({
                'symbol': sym,
                'd_bias': d_bias,
                'd_struct': d_struct,
                'h1_sig': h1_sig,
                'h1_time': h1_time,
                'h4_dir': h4_dir,
                'close_price': close_price,
                'ohlc': closed_ohlc,
                'event': h1_event,
                'confluence': score_confluence
            })

    long_setups.sort(key=lambda x: x['confluence'], reverse=True)
    short_setups.sort(key=lambda x: x['confluence'], reverse=True)

    print(f"=== D-R-H-R WATCHLIST SCAN RESULTS ({target_date}) — [{timeframe.upper()} CLOSED BARS] ===")
    print(f"Total Watchlist Symbols Scanned: {len(daily_symbols)}")
    print(f"Found {len(long_setups)} Long Setups and {len(short_setups)} Short Setups.\n")

    print(f"🟢 HIGH-PROBABILITY D-R-H-R LONG SETUPS ({timeframe.upper()} CLOSED BAR OHLC):")
    for item in long_setups:
        conf_str = "⭐ 3-TF Confluence (D1+H4+H1)" if item['confluence'] == 3 else "✅ 2-TF Alignment (D1+H1)"
        if item['ohlc']:
            o_info = item['ohlc']
            o_str = format_price_precision(o_info['open'], item['symbol'])
            h_str = format_price_precision(o_info['high'], item['symbol'])
            l_str = format_price_precision(o_info['low'], item['symbol'])
            c_str = format_price_precision(o_info['close'], item['symbol'])
            ohlc_str = f"Feed: {o_info['bar_time']} | O: {o_str} | H: {h_str} | L: {l_str} | C: {c_str}"
        else:
            ohlc_str = f"Price: {format_price_precision(item['close_price'], item['symbol'])}"

        print(f"  • [[{item['symbol']}]] | {conf_str}")
        print(f"    - Closed Bar OHLC: {ohlc_str}")
        print(f"    - D1: {item['d_bias']} ({item['d_struct']}) | H1 Signal: {item['h1_sig']} at {item['h1_time']} | Event: {item['event']}")

    print(f"\n🔴 HIGH-PROBABILITY D-R-H-R SHORT SETUPS ({timeframe.upper()} CLOSED BAR OHLC):")
    for item in short_setups:
        conf_str = "⭐ 3-TF Confluence (D1+H4+H1)" if item['confluence'] == 3 else "✅ 2-TF Alignment (D1+H1)"
        if item['ohlc']:
            o_info = item['ohlc']
            o_str = format_price_precision(o_info['open'], item['symbol'])
            h_str = format_price_precision(o_info['high'], item['symbol'])
            l_str = format_price_precision(o_info['low'], item['symbol'])
            c_str = format_price_precision(o_info['close'], item['symbol'])
            ohlc_str = f"Feed: {o_info['bar_time']} | O: {o_str} | H: {h_str} | L: {l_str} | C: {c_str}"
        else:
            ohlc_str = f"Price: {format_price_precision(item['close_price'], item['symbol'])}"

        print(f"  • [[{item['symbol']}]] | {conf_str}")
        print(f"    - Closed Bar OHLC: {ohlc_str}")
        print(f"    - D1: {item['d_bias']} ({item['d_struct']}) | H1 Signal: {item['h1_sig']} at {item['h1_time']} | Event: {item['event']}")

def main():
    parser = argparse.ArgumentParser(description="Scan Watchlist for D-R-H-R Setups with Timeframe Closed Bar Matching")
    parser.add_argument("--watchlist", default=None, help="Path to custom watchlist JSON file")
    parser.add_argument("--timeframe", choices=["1h", "4h", "1d"], default="1h", help="Timeframe of closed bar OHLC (1h, 4h, 1d)")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD")
    args = parser.parse_args()
    
    scan_drhr_watchlist(args.date, args.watchlist, args.timeframe)

if __name__ == "__main__":
    main()
