#!/usr/bin/env python3
"""Checks for the New-York-anchored 4H grid (scan_fake_breakout_setups.bar4h_start)
and validate_h4_signals.signal_bar_window across the US daylight-saving switch.
Run: python3 scratch/check_4h_grid.py (no network)."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.scan_fake_breakout_setups import SGT, bar4h_start, aggregate_4h_bars  # noqa: E402
from scripts.validate_h4_signals import signal_bar_window  # noqa: E402

fails = 0


def ok(cond, msg):
    global fails
    print(("ok   " if cond else "FAIL ") + msg)
    fails += not cond


def t(y, m, d, h, mi=0):
    return dt.datetime(y, m, d, h, mi, tzinfo=SGT)


# US daylight saving (Oct 2026): boundaries 01/05/09/13/17/21 SGT
ok(bar4h_start(t(2026, 10, 28, 6, 1)) == t(2026, 10, 28, 5), "DST: 06:01 sits in the 05:00 bar")
ok(signal_bar_window(t(2026, 10, 28, 5, 1)) == (t(2026, 10, 28, 1), t(2026, 10, 28, 5)), "DST: 05:01 alert -> 01:00-05:00 bar")
ok(signal_bar_window(t(2026, 10, 28, 21, 1)) == (t(2026, 10, 28, 17), t(2026, 10, 28, 21)), "DST: 21:01 alert -> 17:00-21:00 bar")
# US standard time (Nov 2026, after the 2026-11-01 switch): 02/06/10/14/18/22 SGT
ok(signal_bar_window(t(2026, 11, 3, 6, 1)) == (t(2026, 11, 3, 2), t(2026, 11, 3, 6)), "STD: 06:01 alert -> 02:00-06:00 bar")
ok(signal_bar_window(t(2026, 11, 3, 18, 1)) == (t(2026, 11, 3, 14), t(2026, 11, 3, 18)), "STD: 18:01 alert -> 14:00-18:00 bar")
ok(signal_bar_window(t(2026, 11, 4, 2, 0, )) == (t(2026, 11, 3, 22), t(2026, 11, 4, 2)), "STD: 02:00 alert -> 22:00-02:00 bar (crosses midnight SGT)")
ok(bar4h_start(t(2026, 11, 3, 1, 59)) == t(2026, 11, 2, 22), "STD: 01:59 SGT belongs to the previous day's 22:00 bar")
# Week after the March 2027 switch back to daylight saving (2027-03-14)
ok(signal_bar_window(t(2027, 3, 16, 13, 1)) == (t(2027, 3, 16, 9), t(2027, 3, 16, 13)), "DST 2027: 13:01 alert -> 09:00-13:00 bar")

# aggregation: 8 hourly bars from 02:00 SGT on a standard-time day -> two 4H bars at 02:00 and 06:00
hours = [{"dt": t(2026, 11, 3, 2) + dt.timedelta(hours=i), "open": i, "high": i + 1, "low": i - 1, "close": i + 0.5}
         for i in range(8)]
bars = aggregate_4h_bars(hours)
ok([b["dt"] for b in bars] == [t(2026, 11, 3, 2), t(2026, 11, 3, 6)], f"STD aggregation starts {[b['dt'].strftime('%H:%M') for b in bars]}")
ok(bars[0]["open"] == 0 and bars[0]["close"] == 3.5 and bars[0]["high"] == 4, "STD aggregation OHLC")
# same hours shifted one hour earlier on a DST day: 01:00 + 05:00
hours = [dict(h, dt=h["dt"] - dt.timedelta(days=7, hours=1)) for h in hours]
ok([b["dt"] for b in aggregate_4h_bars(hours)] == [t(2026, 10, 27, 1), t(2026, 10, 27, 5)], "DST aggregation starts 01:00/05:00")

print("OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
