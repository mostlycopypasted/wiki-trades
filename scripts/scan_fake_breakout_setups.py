#!/usr/bin/env python3
"""
Scans the watchlist for Wash & Rinse "Long-Tail Bottom/Top Heavy Wash Candle"
fake-breakout setups (see wiki/concepts/wash-and-rinse.md), in both directions:

  SHORT (bottom-heavy candle): price spikes to a new local high above recent
  structure (a false breakout past resistance / a trendline), then closes back
  in the bottom of its range with a long upper wick. The candle's low becomes
  the green sell wash line. Trigger = a later closed bar closing below that low.

  LONG (top-heavy candle): mirror image — price spikes to a new local low below
  recent structure, then closes back in the top of its range with a long lower
  wick. The candle's high becomes the magenta buy wash line. Trigger = a later
  closed bar closing above that high.

This generalizes the pattern first logged ad-hoc for BTCUSD in the 2026-08-01
Weekly Review (wiki/sources/2026-08-01-weekly-review.md / wiki/entities/btcusd.md)
into a repeatable scan across the full watchlist.

Watchlist source: the latest ~/tradingview-mcp/daily_brief/{date}.json (built by
build_daily_bias.py from a live `tv brief -r rules.json` run) — same convention
as scan_drhr_setups.py.

OHLC source: Yahoo Finance closed bars (no live TradingView MCP session required
for the scan itself). For any NEW signal, cross-check exact wash-line/TAT levels
live via TradingView MCP before acting — see .agents/skills/fake-breakout-scanner/SKILL.md.

Usage:
    python3 scripts/scan_fake_breakout_setups.py --timeframe 4h
    python3 scripts/scan_fake_breakout_setups.py --timeframe 1h --lookback 12
"""

import sys
import json
import argparse
import datetime
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.scan_drhr_setups import format_price_precision

SGT = datetime.timezone(datetime.timedelta(hours=8))
ANCHOR_4H = datetime.datetime(2000, 1, 1, 17, 0, tzinfo=SGT)

CRYPTO_BASES = {"BTC", "ETH", "SOL", "NEAR"}
STOCK_TICKERS = {"TSLA", "NVDA", "MSFT", "META", "AAPL", "AMZN", "GOOGL", "CLSK", "MSTR", "RIOT", "IBIT"}


def yahoo_ticker(symbol):
    clean_sym = symbol.split(':')[-1].upper()
    if clean_sym == "XAUUSD":
        return "GC=F"
    if clean_sym == "XAGUSD":
        return "SI=F"
    if clean_sym == "USOUSD":
        return "CL=F"
    if clean_sym in STOCK_TICKERS:
        return clean_sym
    if clean_sym.endswith("USD") and clean_sym[:-3] in CRYPTO_BASES:
        return f"{clean_sym[:-3]}-USD"
    return f"{clean_sym}=X"


def fetch_1h_bars(symbol, range_param="30d"):
    """Fetch closed 1H bars (oldest -> newest), dropping the still-forming current hour."""
    ticker = yahoo_ticker(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1h&range={range_param}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quote = result['indicators']['quote'][0]
    except Exception:
        return []

    now_sgt = datetime.datetime.now(SGT)
    bars = []
    for i in range(len(timestamps)):
        o, h, l, c = quote['open'][i], quote['high'][i], quote['low'][i], quote['close'][i]
        if None in (o, h, l, c):
            continue
        dt = datetime.datetime.fromtimestamp(timestamps[i], tz=datetime.timezone.utc).astimezone(SGT)
        if dt >= now_sgt.replace(minute=0, second=0, microsecond=0):
            continue  # still-forming current hour
        bars.append({'dt': dt, 'open': o, 'high': h, 'low': l, 'close': c})
    return bars


def aggregate_4h_bars(hourly_bars):
    """Bin closed 1H bars into 4H candles anchored at 17:00 SGT (matches TradingView's 4H boundary)."""
    bins = {}
    for b in hourly_bars:
        bin_id = int((b['dt'] - ANCHOR_4H).total_seconds() // (4 * 3600))
        bins.setdefault(bin_id, []).append(b)

    bars = []
    for bin_id in sorted(bins.keys()):
        group = sorted(bins[bin_id], key=lambda b: b['dt'])
        if len(group) < 4:
            continue  # incomplete bin (still forming or gapped)
        bars.append({
            'dt': group[0]['dt'],
            'open': group[0]['open'],
            'high': max(g['high'] for g in group),
            'low': min(g['low'] for g in group),
            'close': group[-1]['close'],
        })
    return bars


def fetch_daily_bars(symbol, range_param="6mo"):
    ticker = yahoo_ticker(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={range_param}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quote = result['indicators']['quote'][0]
    except Exception:
        return []

    today_sgt = datetime.datetime.now(SGT).date()
    bars = []
    for i in range(len(timestamps)):
        o, h, l, c = quote['open'][i], quote['high'][i], quote['low'][i], quote['close'][i]
        if None in (o, h, l, c):
            continue
        dt = datetime.datetime.fromtimestamp(timestamps[i], tz=datetime.timezone.utc).astimezone(SGT)
        if dt.date() >= today_sgt:
            continue  # today's still-forming daily bar
        bars.append({'dt': dt, 'open': o, 'high': h, 'low': l, 'close': c})
    return bars


def fetch_closed_bars(symbol, timeframe):
    tf = timeframe.lower()
    if tf in ("1d", "d", "daily"):
        return fetch_daily_bars(symbol)
    if tf in ("4h", "h4"):
        return aggregate_4h_bars(fetch_1h_bars(symbol, range_param="60d"))
    return fetch_1h_bars(symbol, range_param="10d")


def detect_fake_breakouts(bars, lookback=10, recent_window=5, wick_ratio=0.4, close_pos_thresh=0.4):
    """
    Check the last `recent_window` closed bars as candidate long-tail wash candles.
    Each candidate is validated against the `lookback` bars strictly before it.
    Returns the most recent qualifying signal, or None.
    """
    n = len(bars)
    if n < lookback + 2:
        return None

    start = max(lookback, n - recent_window)
    best = None
    for i in range(start, n):
        window = bars[i - lookback:i]
        bar = bars[i]
        prior_high = max(b['high'] for b in window)
        prior_low = min(b['low'] for b in window)

        rng = bar['high'] - bar['low']
        if rng <= 0:
            continue
        body_top = max(bar['open'], bar['close'])
        body_bottom = min(bar['open'], bar['close'])
        upper_wick = bar['high'] - body_top
        lower_wick = body_bottom - bar['low']
        close_pos = (bar['close'] - bar['low']) / rng

        later_bars = bars[i + 1:]

        # SHORT: fake breakout above resistance, bottom-heavy close
        if bar['high'] > prior_high and (upper_wick / rng) >= wick_ratio and close_pos <= close_pos_thresh:
            triggered = any(b['close'] < bar['low'] for b in later_bars)
            sig = {
                'direction': 'Short',
                'bar_dt': bar['dt'],
                'spike_price': bar['high'],
                'broken_level': prior_high,
                'wash_line': bar['low'],
                'wick_pct': upper_wick / rng,
                'close_pos': close_pos,
                'triggered': triggered,
                'last_close': bars[-1]['close'],
            }
            if best is None or sig['bar_dt'] >= best['bar_dt']:
                best = sig

        # LONG: fake breakout below support, top-heavy close
        if bar['low'] < prior_low and (lower_wick / rng) >= wick_ratio and close_pos >= (1 - close_pos_thresh):
            triggered = any(b['close'] > bar['high'] for b in later_bars)
            sig = {
                'direction': 'Long',
                'bar_dt': bar['dt'],
                'spike_price': bar['low'],
                'broken_level': prior_low,
                'wash_line': bar['high'],
                'wick_pct': lower_wick / rng,
                'close_pos': close_pos,
                'triggered': triggered,
                'last_close': bars[-1]['close'],
            }
            if best is None or sig['bar_dt'] >= best['bar_dt']:
                best = sig

    return best


def load_watchlist_symbols(target_date=None, custom_watchlist_file=None):
    if not target_date:
        target_date = datetime.date.today().strftime('%Y-%m-%d')

    daily_file = Path(f'/Users/chriseah/tradingview-mcp/daily_brief/{target_date}.json')
    daily_data = []
    if daily_file.exists():
        with open(daily_file) as f:
            daily_data = json.load(f)
    else:
        brief_dir = Path('/Users/chriseah/tradingview-mcp/daily_brief')
        json_files = sorted(brief_dir.glob('*.json'), reverse=True) if brief_dir.exists() else []
        if json_files:
            with open(json_files[0]) as f:
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

    items = daily_data if isinstance(daily_data, list) else daily_data.get('results', [])
    symbols = []
    seen = set()
    for item in items:
        raw_sym = item.get('symbol') or item.get('name') or ''
        clean_sym = str(raw_sym).split(':')[-1].upper()
        if clean_sym and clean_sym not in seen and (filter_symbols is None or clean_sym in filter_symbols):
            seen.add(clean_sym)
            symbols.append(clean_sym)
    return symbols


def scan_watchlist(timeframe="4h", target_date=None, custom_watchlist_file=None, lookback=10, recent_window=5):
    symbols = load_watchlist_symbols(target_date, custom_watchlist_file)

    long_setups = []
    short_setups = []

    for sym in symbols:
        bars = fetch_closed_bars(sym, timeframe)
        sig = detect_fake_breakouts(bars, lookback=lookback, recent_window=recent_window)
        if not sig:
            continue
        sig['symbol'] = sym
        if sig['direction'] == 'Long':
            long_setups.append(sig)
        else:
            short_setups.append(sig)

    long_setups.sort(key=lambda s: (s['triggered'], s['wick_pct']), reverse=True)
    short_setups.sort(key=lambda s: (s['triggered'], s['wick_pct']), reverse=True)

    print(f"=== FAKE BREAKOUT (WASH & RINSE LONG-TAIL) SCAN — {timeframe.upper()} — {len(symbols)} symbols scanned ===")
    print(f"Found {len(long_setups)} Long Setups and {len(short_setups)} Short Setups.\n")

    print("🟢 LONG — Fake Breakdown / Top-Heavy Wash Candle:")
    if not long_setups:
        print("  (none)")
    for s in long_setups:
        status = "⚡ TRIGGERED — wash line broken, watch for rally back into resistance to re-enter" if s['triggered'] else "👀 ARMED — awaiting close above magenta wash line"
        print(f"  • [[{s['symbol']}]] | {status}")
        print(f"    - Bar: {s['bar_dt'].strftime('%Y-%m-%d %H:%M SGT')} | Spiked below prior structure {format_price_precision(s['broken_level'], s['symbol'])} to {format_price_precision(s['spike_price'], s['symbol'])}, closed top-heavy ({s['wick_pct']*100:.0f}% lower wick)")
        print(f"    - Magenta Wash Line (candle high): {format_price_precision(s['wash_line'], s['symbol'])} | Last Close: {format_price_precision(s['last_close'], s['symbol'])}")

    print("\n🔴 SHORT — Fake Breakout / Bottom-Heavy Wash Candle:")
    if not short_setups:
        print("  (none)")
    for s in short_setups:
        status = "⚡ TRIGGERED — wash line broken, watch for rally back into resistance to re-enter (\"sell high, sell high\")" if s['triggered'] else "👀 ARMED — awaiting close below green wash line"
        print(f"  • [[{s['symbol']}]] | {status}")
        print(f"    - Bar: {s['bar_dt'].strftime('%Y-%m-%d %H:%M SGT')} | Spiked above prior structure {format_price_precision(s['broken_level'], s['symbol'])} to {format_price_precision(s['spike_price'], s['symbol'])}, closed bottom-heavy ({s['wick_pct']*100:.0f}% upper wick)")
        print(f"    - Green Wash Line (candle low): {format_price_precision(s['wash_line'], s['symbol'])} | Last Close: {format_price_precision(s['last_close'], s['symbol'])}")


def main():
    parser = argparse.ArgumentParser(description="Scan watchlist for Wash & Rinse long-tail fake-breakout setups (long + short)")
    parser.add_argument("--timeframe", choices=["1h", "4h", "1d"], default="4h", help="Candle timeframe to scan (default: 4h)")
    parser.add_argument("--date", default=None, help="Watchlist date YYYY-MM-DD (defaults to today / latest daily_brief)")
    parser.add_argument("--watchlist", default=None, help="Path to custom watchlist JSON file")
    parser.add_argument("--lookback", type=int, default=10, help="Bars of prior structure to check for a breakout (default: 10)")
    parser.add_argument("--recent", type=int, default=5, help="How many of the most recent closed bars to check as candidates (default: 5)")
    args = parser.parse_args()

    scan_watchlist(args.timeframe, args.date, args.watchlist, args.lookback, args.recent)


if __name__ == "__main__":
    main()
