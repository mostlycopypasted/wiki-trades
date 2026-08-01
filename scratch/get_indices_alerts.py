#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.fetch_google_sheet import fetch_sheet_records
from scripts.binni_alert_analysis import get_latest_full_date, normalize_date

indices_symbols = {'JPN225', 'CN50', 'NDQ100', 'GER40', 'UK100', 'US2000', 'SPX500', 'US30', 'HK50', 'ASX200', 'FRA40', 'EU50', 'SCY', 'SCN50'}

h1_records = fetch_sheet_records("H1")
h4_records = fetch_sheet_records("4H")
daily_records = fetch_sheet_records("DAILY")

latest_date = get_latest_full_date(h1_records)

print(f"=== INDICES TAT ALERTS LOGGED TODAY ({latest_date}) ===")

print("\n📊 1-HOUR (H1) INDICES ALERTS:")
print("-" * 75)
h1_indices = [r for r in h1_records if normalize_date(r.get('Date')) == latest_date and any(idx in str(r.get('Symbol', '')).upper() for idx in indices_symbols)]
for i, r in enumerate(h1_indices, 1):
    sym = r.get('Symbol') or 'N/A'
    time_str = r.get('Time') or 'N/A'
    dir_str = r.get('Direction') or 'N/A'
    sig_type = r.get('Signal Type') or 'N/A'
    event = r.get('Event') or 'N/A'
    print(f"{i:02d}. [{time_str}] {sym:<18} | {dir_str:<8} | Signal: {sig_type:<9} | {event}")

print("\n📊 4-HOUR (4H) INDICES ALERTS:")
print("-" * 75)
h4_indices = [r for r in h4_records if normalize_date(r.get('Date')) == latest_date and any(idx in str(r.get('Symbol', '')).upper() for idx in indices_symbols)]
for i, r in enumerate(h4_indices, 1):
    sym = r.get('Symbol') or 'N/A'
    time_str = r.get('Time') or 'N/A'
    dir_str = r.get('Direction') or 'N/A'
    sig_type = r.get('Signal Type') or 'N/A'
    event = r.get('Event') or 'N/A'
    print(f"{i:02d}. [{time_str}] {sym:<18} | {dir_str:<8} | Signal: {sig_type:<9} | {event}")

print("\n📊 DAILY INDICES ALERTS:")
print("-" * 75)
d_indices = [r for r in daily_records if normalize_date(r.get('Date')) == latest_date and any(idx in str(r.get('Symbol', '')).upper() for idx in indices_symbols)]
for i, r in enumerate(d_indices, 1):
    sym = r.get('Symbol') or 'N/A'
    time_str = r.get('Time') or 'N/A'
    dir_str = r.get('Direction') or 'N/A'
    sig_type = r.get('Signal Type') or 'N/A'
    event = r.get('Event') or 'N/A'
    print(f"{i:02d}. [{time_str}] {sym:<18} | {dir_str:<8} | Signal: {sig_type:<9} | {event}")
