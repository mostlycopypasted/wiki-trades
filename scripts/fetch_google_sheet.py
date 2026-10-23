#!/usr/bin/env python3
import os
import sys
import json
import csv
import io
import argparse
import urllib.request
from pathlib import Path

SHEET_ID = "1XQc0TFDvihNN7wSNBBJom5rh5W-D6msm24gaMTQ5DaE"
GIDS = {
    "H1": "0",
    "4H": "1105950672",
    "H4": "1105950672",
    "DAILY": "462165474",
    "D1": "462165474",
    "1D": "462165474",
    "BULL_DAILY": "1875176436",
    "BULL": "1875176436",
    "STOCKS_DAILY": "1875176436",
    "STOCKS": "1875176436",
    "BEAR_DAILY": "1088333741",
    "BEAR": "1088333741",
    "BEAR_STOCKS": "1088333741",
    "FOREX_D": "462165474",
    "BATS": "520189562",
    "TV_STOCKS": "520189562",
    "STOCKS_TV": "520189562"
}

# The Telegram-fed tabs above still carry TAT v2 alerts only. TAT v3 Tflow alerts
# ("Tflow OptBull" etc.) reach the email-extract sheet ("TAT Alert Extract_v2"),
# whose Sheet1 holds every timeframe with a Period column. Its Tflow rows are
# folded into the matching tab, limited to exchanges that tab already carries.
EXTRACT_SHEET_ID = "1FIn1L1So1Slid7QKBE3jVSLTRMEqqvcQ16JDSFuoV8Q"
EXTRACT_GID = 0
TFLOW_PERIOD_BY_GID = {"0": "1H", "1105950672": "4H", "462165474": "1D", "520189562": "1D"}
STANDARD_COLUMNS = ["Date", "Time", "Symbol", "Name", "Direction", "Signal Type",
                    "Signal Price", "Event", "Subject"]
_extract_cache = {"at": 0.0, "rows": None}
EXTRACT_TTL = 60  # seconds; one run fetches several tabs back to back

def try_public_csv(gid="0"):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(content))
            records = list(reader)
            print(f"✅ Successfully fetched {len(records)} row(s) via Public Export URL (gid: {gid})!")
            return records
    except Exception as e:
        print(f"  ℹ️ Direct public fetch attempted (gid: {gid}): {e}")
        return None

def _extract_tflow_rows(gc):
    """Tflow rows from the extract sheet, as dicts in the standard tab schema plus Period."""
    import time
    if _extract_cache["rows"] is not None and time.time() - _extract_cache["at"] < EXTRACT_TTL:
        return _extract_cache["rows"]
    values = gc.open_by_key(EXTRACT_SHEET_ID).get_worksheet_by_id(EXTRACT_GID).get_all_values()
    header = values[0] if values else []
    # The header repeats "Symbol" (full and bare), so zip by position, not get_all_records().
    idx = {name: header.index(name) for name in STANDARD_COLUMNS + ["Period"] if name in header}
    rows = []
    for r in values[1:]:
        rec = {name: (r[i] if i < len(r) else "") for name, i in idx.items()}
        if str(rec.get("Signal Type", "")).startswith("Tflow"):
            try:
                rec["Signal Price"] = float(rec["Signal Price"])
            except (TypeError, ValueError):
                pass
            rows.append(rec)
    _extract_cache.update(at=time.time(), rows=rows)
    return rows


def add_extract_tflow(gc, gid, records):
    """Append the extract sheet's Tflow rows for this tab's timeframe and exchanges."""
    period = TFLOW_PERIOD_BY_GID.get(str(gid))
    if not period:
        return records
    try:
        tflow = _extract_tflow_rows(gc)
    except Exception as e:
        print(f"  ⚠️ Tflow supplement skipped (extract sheet unreadable: {e})")
        return records
    exchanges = {str(r.get("Symbol", "")).split(":")[0] for r in records if ":" in str(r.get("Symbol", ""))}
    def key(r):
        hhmm = ":".join(str(r.get("Time", "")).split(":")[:2]).zfill(5)
        return (str(r.get("Symbol")), str(r.get("Signal Type")), str(r.get("Date")), hhmm)
    seen = {key(r) for r in records}
    added = []
    for r in tflow:
        if r.get("Period") != period or str(r.get("Symbol", "")).split(":")[0] not in exchanges:
            continue
        if key(r) in seen:
            continue
        seen.add(key(r))
        added.append({k: r.get(k, "") for k in STANDARD_COLUMNS})
    if added:
        print(f"  ➕ Added {len(added)} Tflow row(s) from the extract sheet ({period})")
    return records + added


def fetch_with_service_account(timeframe="H1"):
    tf = timeframe.upper()
    gid = GIDS.get(tf, "0")
    
    possible_paths = [
        Path("service_account.json"),
        Path("credentials.json"),
        Path.home() / "tradingview-mcp" / "service_account.json",
        Path.home() / "service_account.json"
    ]
    
    cred_file = None
    for p in possible_paths:
        if p.exists():
            cred_file = p
            break
            
    if not cred_file:
        return None
        
    print(f"🔑 Using service account credentials from: {cred_file}")
    import gspread
    gc = gspread.service_account(filename=str(cred_file))
    try:
        gc.set_timeout(30)  # gspread has no default timeout; a stalled socket would otherwise hang the caller forever
    except AttributeError:
        pass
    
    spreadsheet = gc.open_by_key(SHEET_ID)
    worksheet = spreadsheet.get_worksheet_by_id(int(gid))
    
    records = worksheet.get_all_records()
    print(f"✅ Successfully fetched {len(records)} row(s) from {tf} tab (gid: {gid}) via Service Account!")
    return add_extract_tflow(gc, gid, records)

def fetch_sheet_records(timeframe="H1"):
    tf = timeframe.upper()
    gid = GIDS.get(tf, "0")
    
    # 1. Try public export
    records = try_public_csv(gid=gid)
    if records is not None:
        return records
        
    # 2. Try service account
    records = fetch_with_service_account(timeframe=tf)
    if records is not None:
        return records

    print(f"\n❌ Could not fetch Google Sheet tab for timeframe: {tf}.")
    return []

def main():
    parser = argparse.ArgumentParser(description="Fetch Google Sheet alert records")
    parser.add_argument("--timeframe", choices=sorted(GIDS.keys()), default="H1", help="Timeframe/tab key to fetch (default: H1)")
    args = parser.parse_args()
    
    records = fetch_sheet_records(args.timeframe)
    if records:
        print("="*60)
        print(json.dumps(records[:5], indent=2))

if __name__ == "__main__":
    main()
