#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.fetch_google_sheet import fetch_sheet_records

h1_records = fetch_sheet_records("H1")
gbpaud_h1 = [r for r in h1_records if 'GBPAUD' in str(r.get('Symbol', '')).upper()]

print("=== GBPAUD 1H TAT ALERTS & SUPPORT/RESISTANCE LEVELS LOGICAL BREAKDOWN ===")
print(f"Total H1 Alerts for GBPAUD: {len(gbpaud_h1)}\n")

print("Recent 1H Alerts:")
print("-" * 85)
for i, r in enumerate(gbpaud_h1[:10], 1):
    date_str = r.get('Date') or 'N/A'
    time_str = r.get('Time') or 'N/A'
    dir_str = r.get('Direction') or 'N/A'
    sig_type = r.get('Signal Type') or 'N/A'
    event = r.get('Event') or 'N/A'
    details = r.get('Details') or r.get('Full Body') or 'N/A'
    print(f"{i:02d}. [{date_str} {time_str}] | Direction: {dir_str:<8} | Signal: {sig_type:<9} | Event: {event}")
    print(f"    Details: {details}")
    print("-" * 85)
