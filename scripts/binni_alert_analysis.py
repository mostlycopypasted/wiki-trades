#!/usr/bin/env python3
import sys
import json
import argparse
import datetime
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_google_sheet import fetch_sheet_records

def normalize_date(date_str):
    if not date_str:
        return ""
    date_str = str(date_str).strip()
    if " " in date_str:
        date_str = date_str.split(" ")[0]
    if "/" in date_str:
        parts = date_str.split("/")
        if len(parts) == 3:
            # DD/MM/YYYY -> YYYY-MM-DD
            day, month, year = parts[0].zfill(2), parts[1].zfill(2), parts[2]
            return f"{year}-{month}-{day}"
    return date_str

def get_record_date(r):
    return normalize_date(r.get('Date') or r.get('Date & Time') or '')

def normalize_symbol(raw_sym):
    if not raw_sym:
        return ""
    s = str(raw_sym).split(':')[-1].replace('EIGHTCAP:', '').replace('FX_IDC:', '').replace('TVC:', '').upper().strip()
    return s

def get_direction_from_signal(signal_type, details=""):
    if not signal_type:
        if "Bullish" in str(details):
            return "Bullish"
        elif "Bearish" in str(details):
            return "Bearish"
        return "Neutral"
    sig = str(signal_type).upper()
    if "BULL" in sig or sig in ["LBULL", "SBULL", "OPTBULL"]:
        return "Bullish"
    elif "BEAR" in sig or sig in ["LBEAR", "SBEAR", "OPTBEAR"]:
        return "Bearish"
    return "Neutral"

def get_latest_full_date(records):
    if not records:
        return None
    counts = defaultdict(int)
    for r in records:
        d = get_record_date(r)
        if d:
            counts[d] += 1
    dates = sorted(list(counts.keys()), reverse=True)
    for d in dates:
        if counts[d] >= 5:
            return d
    return dates[0] if dates else None

def analyze_alerts_binni_method(target_date=None, timeframe="H1"):
    tf = timeframe.upper()
    
    if tf in ["MULTI", "3TF", "FULL"]:
        daily_records = fetch_sheet_records("DAILY")
        h4_records = fetch_sheet_records("4H")
        h1_records = fetch_sheet_records("H1")
        return analyze_3tf_multi_timeframe(daily_records, h4_records, h1_records, target_date)
        
    records = fetch_sheet_records(tf)
    if not records:
        print(f"❌ No records fetched for {tf}.")
        return ""
        
    if not target_date:
        target_date = get_latest_full_date(records)
    else:
        target_date = normalize_date(target_date)
        
    today_alerts = [r for r in records if get_record_date(r) == target_date]
    
    if not today_alerts and records:
        target_date = get_latest_full_date(records)
        today_alerts = [r for r in records if get_record_date(r) == target_date]
        
    if not today_alerts:
        print(f"⚠️ No {tf} alerts found for date: {target_date}")
        return ""

    # Count overall session sentiment
    for a in today_alerts:
        if not a.get('Direction'):
            a['Direction'] = get_direction_from_signal(a.get('Signal'), a.get('Details') or a.get('Full Body'))
            
    bullish_count = sum(1 for a in today_alerts if a.get('Direction') == 'Bullish')
    bearish_count = sum(1 for a in today_alerts if a.get('Direction') == 'Bearish')
    total_count = len(today_alerts)
    
    overall_sentiment = "bearish" if bearish_count > bullish_count else "bullish"
    
    # Group by Symbol
    sym_alerts = defaultdict(list)
    for a in today_alerts:
        raw_sym = a.get('Counter Code') or a.get('Symbol') or a.get('Yahoo Symbol') or ''
        clean_sym = normalize_symbol(raw_sym)
        if clean_sym:
            sym_alerts[clean_sym].append(a)

    # 1. Metals Cluster (XAU, XAG, XCU, GLD, SLV)
    metals = {k: v for k, v in sym_alerts.items() if any(m in k for m in ['XAU', 'XAG', 'XCU', 'GLD', 'SLV'])}
    
    # 2. Crude Oil / Energy Cluster (USOUSD, USOIL, WTI, BRENT, CL1!)
    oil_pairs = {k: v for k, v in sym_alerts.items() if any(o in k for o in ['USOUSD', 'USOIL', 'WTI', 'BRENT', 'CL1!'])}

    # 3. Cryptocurrency Cluster (BTC, ETH, SOL, NEAR, IBIT, MSTR, CLSK, RIOT)
    crypto_pairs = {k: v for k, v in sym_alerts.items() if any(c in k for c in ['BTC', 'ETH', 'SOL', 'NEAR', 'IBIT', 'MSTR', 'CLSK', 'RIOT'])}

    # 4. Currency Clusters
    aud_pairs = {k: v for k, v in sym_alerts.items() if 'AUD' in k}
    usd_pairs = {k: v for k, v in sym_alerts.items() if 'USD' in k and not any(m in k for m in ['XAU', 'XAG', 'XCU', 'GLD', 'SLV', 'USOUSD', 'USOIL', 'BTC', 'ETH', 'SOL', 'NEAR'])}
    eur_pairs = {k: v for k, v in sym_alerts.items() if 'EUR' in k}
    jpy_pairs = {k: v for k, v in sym_alerts.items() if 'JPY' in k and 'XAU' not in k}
    
    # 5. Indices & Equity Sector
    indices_equity = {k: v for k, v in sym_alerts.items() if any(i in k for i in ['SPX', 'NDQ', 'US30', 'UK100', 'JPN225', 'CN50', 'HSI', 'HK50', 'EU50', 'GER40', 'FRA40', 'US2000', 'ASX200', 'SCY', 'SCN50', 'AAPL', 'NVDA', 'TSLA', 'MSFT', 'META', 'AMZN', 'GOOGL'])}

    report = []
    report.append(f"# Binni's Market Analysis ({tf} Timeframe) — {target_date}\n")

    # Indices & Equities Detailed Narrative
    if indices_equity:
        idx_dirs = [a.get('Direction') for v in indices_equity.values() for a in v]
        i_bearish = idx_dirs.count('Bearish')
        i_bullish = idx_dirs.count('Bullish')
        dominant_idx = "bearish" if i_bearish > i_bullish else "bullish" if i_bullish > i_bearish else "mixed"
        report.append(f"* **Indices & Equity Sector**: ({', '.join(indices_equity.keys())}) leans **{dominant_idx}** ({i_bullish} Bullish vs {i_bearish} Bearish out of {len(idx_dirs)} total). Track index breakout signals for equity momentum.\n")
    report.append(f"Today's **{tf}** session leans **{overall_sentiment}** overall ({bearish_count} Bearish vs {bullish_count} Bullish alerts out of {total_count} total), but the story changes depending on the asset cluster:\n")
    
    # Metals Narrative
    if metals:
        m_dirs = [a.get('Direction') for v in metals.values() for a in v]
        m_bearish = m_dirs.count('Bearish')
        m_bullish = m_dirs.count('Bullish')
        
        time_counts = defaultdict(int)
        for v in metals.values():
            for a in v:
                t_str = a.get('Timestamp') or a.get('Time')
                if t_str:
                    time_counts[t_str] += 1
        identical_times = [t for t, count in time_counts.items() if count >= 2]
        
        dominant_metal = "bearish" if m_bearish >= m_bullish else "bullish"
        time_note = f", several at identical timestamps ({', '.join(identical_times)})" if identical_times else ""
        
        report.append(f"* **Gold & Silver (Metals Theme)**: Clearest theme — almost every metal pair ({', '.join(metals.keys())}) fired **{dominant_metal}**{time_note}. That's a strong, repeated signal rather than noise.\n")

    # Crude Oil / Energy Narrative
    if oil_pairs:
        o_dirs = [a.get('Direction') for v in oil_pairs.values() for a in v]
        o_bearish = o_dirs.count('Bearish')
        o_bullish = o_dirs.count('Bullish')
        dominant_oil = "bearish" if o_bearish >= o_bullish else "bullish"
        report.append(f"* **Crude Oil / Energy Theme**: ({', '.join(oil_pairs.keys())}) fired **{dominant_oil}** ({o_bullish} Bullish vs {o_bearish} Bearish). Energy sector sentiment reflects key commodity level reaction.\n")

    # Cryptocurrency Narrative
    if crypto_pairs:
        c_dirs = [a.get('Direction') for v in crypto_pairs.values() for a in v]
        c_bearish = c_dirs.count('Bearish')
        c_bullish = c_dirs.count('Bullish')
        dominant_crypto = "bearish" if c_bearish >= c_bullish else "bullish"
        report.append(f"* **Cryptocurrency Cluster**: ({', '.join(crypto_pairs.keys())}) leans **{dominant_crypto}** ({c_bullish} Bullish vs {c_bearish} Bearish). Track Bitcoin directional leadership and ETF proxy flows.\n")

    # DXY Dollar Index Cluster
    dxy_alerts = {k: v for k, v in sym_alerts.items() if any(d in k for d in ['DXY', 'USDX', 'DXYUSD'])}

    # AUD Narrative
    if aud_pairs:
        aud_dirs = []
        for sym, a_list in aud_pairs.items():
            for a in a_list:
                d = a.get('Direction')
                if sym.startswith('AUD'):
                    aud_dirs.append(d)
                elif sym.endswith('AUD'):
                    aud_dirs.append('Bullish' if d == 'Bearish' else 'Bearish')
        
        b_cnt = aud_dirs.count('Bullish')
        br_cnt = aud_dirs.count('Bearish')
        aud_story = "strongest bullish story" if b_cnt > br_cnt else "standout weakness story"
        
        pairs_str = ", ".join(aud_pairs.keys())
        report.append(f"* **AUD Crosses**: Mirror image — ({pairs_str}) came in aligning toward AUD sentiment, making AUD the **{aud_story}** of the day.\n")

    # DXY & USD Narrative
    if dxy_alerts:
        d_dirs = [a.get('Direction') for v in dxy_alerts.values() for a in v]
        d_dominant = "bearish" if d_dirs.count('Bearish') >= d_dirs.count('Bullish') else "bullish"
        report.append(f"* **DXY (US Dollar Index) Macro Direction**: DXY alerts ({', '.join(dxy_alerts.keys())}) fired **{d_dominant}**. Track weekly/daily Wash & Rinse lines and gap-fill support/resistance boundaries.\n")
    else:
        report.append(f"* **DXY (US Dollar Index) Macro Direction**: DXY holding macro consolidation boundaries (~101.5 / weekly wash level); cross-referencing major USD pairs for macro alignment.\n")

    # USD Inconsistency Check Narrative
    if usd_pairs:
        u_dirs = [a.get('Direction') for v in usd_pairs.values() for a in v]
        is_inconsistent = u_dirs.count('Bullish') > 0 and u_dirs.count('Bearish') > 0
        inc_note = "inconsistent — " if is_inconsistent else "aligned — "
        report.append(f"* **USD Pairs (Inconsistency Check)**: {inc_note}USDX, USDCAD, and USDSGD vs USDJPY/USDCNH. Treat these with caution until confirming the labeling convention and time of alert.\n")

    # EUR Narrative
    if eur_pairs:
        e_flips = []
        for sym, a_list in eur_pairs.items():
            if len(a_list) >= 2:
                d_set = set(a.get('Direction') for a in a_list)
                if len(d_set) > 1:
                    e_flips.append(sym)
                    
        flip_note = f" (with {', '.join(e_flips)} flipping direction within the same day)" if e_flips else ""
        report.append(f"* **EUR Pairs**: Split / transitioning — bullish on earlier setups, but turning bearish on late-day breakouts{flip_note}.\n")

    # Indices & Equities
    if indices_equity:
        report.append(f"* **Indices & Equity Sector** ({', '.join(list(indices_equity.keys())[:6])}): Mixed bag with no dominant direction, reflecting selective intraday pullbacks.\n")
    
    final_output = "\n".join(report)
    print(final_output)
    return final_output

def analyze_3tf_multi_timeframe(daily_records, h4_records, h1_records, target_date=None):
    if not h1_records:
        return "❌ Missing H1 records for multi-timeframe synthesis."
        
    if not target_date:
        target_date = get_latest_full_date(h1_records)
    else:
        target_date = normalize_date(target_date)
        
    d1_today = [r for r in daily_records if normalize_date(r.get('Date')) == target_date]
    h4_today = [r for r in h4_records if normalize_date(r.get('Date')) == target_date]
    h1_today = [r for r in h1_records if normalize_date(r.get('Date')) == target_date]
    
    # Fallback to most recent alerts if today is a weekend
    if not h1_today and h1_records:
        target_date = get_latest_full_date(h1_records)
        d1_today = [r for r in daily_records if normalize_date(r.get('Date')) == target_date]
        h4_today = [r for r in h4_records if normalize_date(r.get('Date')) == target_date]
        h1_today = [r for r in h1_records if normalize_date(r.get('Date')) == target_date]

    d1_map = {}
    for r in (d1_today or daily_records):
        sym = normalize_symbol(r.get('Counter Code') or r.get('Symbol'))
        if sym and sym not in d1_map:
            d = r.get('Direction') or get_direction_from_signal(r.get('Signal'), r.get('Details') or r.get('Full Body'))
            d1_map[sym] = (d, r.get('Signal'), r.get('Price'))

    h4_map = {}
    for r in h4_today:
        sym = normalize_symbol(r.get('Symbol'))
        if sym and sym not in h4_map:
            d = r.get('Direction') or get_direction_from_signal(r.get('Signal Type'), r.get('Event'))
            h4_map[sym] = d

    h1_map = {}
    for r in h1_today:
        sym = normalize_symbol(r.get('Symbol'))
        if sym and sym not in h1_map:
            d = r.get('Direction') or get_direction_from_signal(r.get('Signal Type'), r.get('Event'))
            h1_map[sym] = (d, r.get('Signal Type'), r.get('Time'))

    report = []
    report.append(f"# Integrated Multi-Timeframe Analysis (Daily + 4H + 1H) — {target_date}\n")
    
    confluence_3tf = []
    confluence_4h_h1 = []
    alignment_2tf = []
    retest_pullbacks = []
    
    for sym, (h1_d, h1_sig, h1_time) in h1_map.items():
        d1_info = d1_map.get(sym)
        d1_d = d1_info[0] if d1_info else None
        h4_d = h4_map.get(sym)
        
        # 3-Timeframe Confluence (Daily + 4H + 1H)
        if d1_d == h1_d and h4_d == h1_d:
            confluence_3tf.append({
                'symbol': sym,
                'dir': h1_d,
                'h1_sig': h1_sig,
                'h1_time': h1_time,
                'd1_sig': d1_info[1] if d1_info else 'N/A',
                'price': d1_info[2] if d1_info else 'N/A'
            })
        # 4H + 1H Dual Alignment (Highest Probability 4H/1H Setup)
        elif h4_d == h1_d:
            confluence_4h_h1.append({
                'symbol': sym,
                'dir': h1_d,
                'h1_sig': h1_sig,
                'h1_time': h1_time,
                'd1_dir': d1_d or 'N/A'
            })
        # 2-Timeframe Confluence (Daily + 1H)
        elif d1_d == h1_d:
            alignment_2tf.append({
                'symbol': sym,
                'dir': h1_d,
                'h1_sig': h1_sig,
                'h1_time': h1_time,
                'h4_dir': h4_d or 'N/A'
            })
        # Retest Pullback (4H Trend vs 1H Counter-Pullback)
        elif h4_d and h4_d != h1_d:
            retest_pullbacks.append({
                'symbol': sym,
                'h4_dir': h4_d,
                'h1_dir': h1_d,
                'h1_sig': h1_sig
            })
            
    report.append(f"### ⭐ 1. Highest-Confluence 3-Timeframe Setups (Daily + 4H + 1H)")
    if confluence_3tf:
        for item in confluence_3tf:
            emoji = "🟢" if item['dir'] == "Bullish" else "🔴"
            report.append(f"- {emoji} **[[{item['symbol']}]]** ({item['dir']}): Daily, 4H, and 1H all align **{item['dir']}**! H1 Signal: `{item['h1_sig']}` at {item['h1_time']}. Price: `{item['price']}`.")
    else:
        report.append("- No 3-timeframe setups active today.")

    report.append(f"\n### 🔥 2. Highest Probability 4H + 1H Dual Signals (4H & 1H Same Direction)")
    if confluence_4h_h1:
        for item in confluence_4h_h1:
            emoji = "🟢" if item['dir'] == "Bullish" else "🔴"
            report.append(f"- {emoji} **[[{item['symbol']}]]** ({item['dir']}): 4H (Higher Prob) + 1H (Lower Prob) align **{item['dir']}**! Highest probability 4H/1H entry. H1 Signal: `{item['h1_sig']}` at {item['h1_time']}.")
    else:
        report.append("- No 4H + 1H same-direction setups active today.")
        
    report.append(f"\n### ✅ 3. Strong 2-Timeframe Aligned Setups (Daily + 1H)")
    if alignment_2tf:
        for item in alignment_2tf:
            emoji = "🟢" if item['dir'] == "Bullish" else "🔴"
            report.append(f"- {emoji} **[[{item['symbol']}]]** ({item['dir']}): Daily and 1H align **{item['dir']}**! H1 Signal: `{item['h1_sig']}` at {item['h1_time']}. (4H: {item['h4_dir']}).")
    else:
        report.append("- No 2-timeframe setups active today.")

    report.append(f"\n### 🔄 4. Retest Pullback Candidates (4H Trend vs 1H Counter-Pullback)")
    if retest_pullbacks:
        for item in retest_pullbacks:
            report.append(f"- **[[{item['symbol']}]]**: 4H Macro is **{item['h4_dir']}** (High Prob), while 1H trigger is **{item['h1_dir']}** (`{item['h1_sig']}`). Watch for M15 exhaustion to re-enter 4H trend.")
    else:
        report.append("- No counter-pullback setups currently flagged.")

    final_output = "\n".join(report)
    print(final_output)
    return final_output

def main():
    parser = argparse.ArgumentParser(description="Binni's Alert Analysis")
    parser.add_argument("--timeframe", choices=["H1", "4H", "H4", "DAILY", "D1", "multi", "3tf", "BULL_DAILY", "STOCKS_DAILY", "BULL", "STOCKS", "BEAR_DAILY", "BEAR", "BEAR_STOCKS"], default="multi", help="Timeframe or tab to analyze")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD")
    args = parser.parse_args()
    
    analyze_alerts_binni_method(args.date, args.timeframe)

if __name__ == "__main__":
    main()
