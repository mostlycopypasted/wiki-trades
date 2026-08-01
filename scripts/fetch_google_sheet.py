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
    "BEAR_STOCKS": "1088333741"
}

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
    
    spreadsheet = gc.open_by_key(SHEET_ID)
    worksheet = spreadsheet.get_worksheet_by_id(int(gid))
    
    records = worksheet.get_all_records()
    print(f"✅ Successfully fetched {len(records)} row(s) from {tf} tab (gid: {gid}) via Service Account!")
    return records

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
    parser.add_argument("--timeframe", choices=["H1", "4H", "H4", "DAILY", "D1", "1D"], default="H1", help="Timeframe tab to fetch (default: H1)")
    args = parser.parse_args()
    
    records = fetch_sheet_records(args.timeframe)
    if records:
        print("="*60)
        print(json.dumps(records[:5], indent=2))

if __name__ == "__main__":
    main()
