#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.fetch_google_sheet import fetch_sheet_records
from scripts.binni_alert_analysis import get_latest_full_date, normalize_date

records = fetch_sheet_records("4H")
latest_date = get_latest_full_date(records)
today_rows = [r for r in records if normalize_date(r.get('Date')) == latest_date]

print(f"Total 4H alerts logged for {latest_date}: {len(today_rows)}")
print("-" * 75)
for i, r in enumerate(today_rows, 1):
    sym = r.get('Symbol') or 'N/A'
    time_str = r.get('Time') or 'N/A'
    dir_str = r.get('Direction') or 'N/A'
    sig_type = r.get('Signal Type') or 'N/A'
    event = r.get('Event') or 'N/A'
    print(f"{i:02d}. [{time_str}] {sym:<18} | {dir_str:<8} | Signal: {sig_type:<9} | {event}")
