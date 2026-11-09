#!/usr/bin/env python3
"""Fixture checks for the Signal Judge Phase 2 (docs/design/signal-judge.md, Verification 1-2).

    python3 scratch/check_signal_judge.py

No network, no TradingView: the sheet, Yahoo, the chart pass and tv_session.sh's external commands
are stubbed, and every data dir points at a temp dir.
"""

import contextlib
import datetime as dt
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="sjudge_"))
for k, sub in (("SIGNAL_JUDGE_DATA_DIR", "data"), ("SIGNAL_JUDGE_REPORT_DIR", "report"),
               ("SIGNAL_JUDGE_RUNS_DIR", "runs"), ("SIGNAL_CASES_DIR", "cases")):
    os.environ[k] = str(TMP / sub)
    (TMP / sub).mkdir()
os.environ["SIGNAL_JUDGE_NO_LOG"] = "1"
os.environ["SIGNAL_JUDGE_TFLOW_RETRY_S"] = "0"
os.environ["SIGNAL_JUDGE_LOCK_WAIT"] = "2"

from scripts import signal_cases as SC  # noqa: E402
from scripts import signal_judge as SJ  # noqa: E402
from scripts import signal_judge_stats as ST  # noqa: E402

SGT = SC.SGT
N = 0


def ok(cond, msg):
    global N
    if not cond:
        raise AssertionError(msg)
    N += 1


def t(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=SGT) if "+" not in s else dt.datetime.fromisoformat(s)


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = SJ.main(argv)
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------- grid, nominal close, market hours
ok(SC.nominal_close("EURUSD", "4H", t("2026-11-03T06:00:04")) == t("2026-11-03T06:00"), "FX 4H std 06:00")
ok(SC.nominal_close("EURUSD", "4H", t("2026-10-28T05:00:03")) == t("2026-10-28T05:00"), "FX 4H DST 05:00")
for s_ in ("15:00:04", "14:59:58", "15:16:00"):
    ok(SC.nominal_close("XAGUSD" if False else "NDQ100", "1H", t("2026-11-03T" + s_)) == t("2026-11-03T15:00"), f"1H {s_}")
ok(SC.nominal_close("XAUUSD", "1H", t("2026-11-03T10:01:05")) == t("2026-11-03T10:01"), "XAUUSD :01 grid")
ok(SC.nominal_close("GER40", "1H", t("2026-11-03T10:15:03")) == t("2026-11-03T10:15"), "GER40 :15")
ok(SC.nominal_close("HK50", "1H", t("2026-11-03T11:15:02")) == t("2026-11-03T11:15"), "HK50 :15")
run = t("2026-11-09T07:01")
ok(abs(SC.market_hours_between(t("2026-11-07T06:00"), run) - 1.0167) < 0.01, "Sat 06:00 FX bar ~1 market hour old")
ok(abs(SC.market_hours_between(t("2026-11-06T23:00"), run) - 8.0167) < 0.01, "Fri 23:00 -> 8.02 mh")
ok(abs(SC.market_hours_between(t("2026-11-06T14:00"), run) - 17.0167) < 0.01, "Fri 14:00 -> 17.02 mh")
ok(SC.market_cutoff(run, 12) == t("2026-11-06T19:01"), f"market_cutoff {SC.market_cutoff(run, 12)}")
ok(SC.market_hours_between(t("2026-11-07T09:59"), t("2026-11-07T10:00")) == 0, "Saturday is closed")

# ---------------------------------------------------------------- oil, classes
ok(SC.instrument_class("USOUSD") == "oil" and SC.canon_instrument("USOIL") == "USOUSD", "oil class + alias")
ok(SC.yahoo_ticker("USOUSD") == "CL=F", "oil ticker")
ok(SC.is_judged_pair("EURUSD", "4H") and not SC.is_judged_pair("EURUSD", "1H"), "FX 4H only")
ok(SC.is_judged_pair("XAUUSD", "1H") and not SC.is_judged_pair("XAUUSD", "4H"), "metals 1H only")
ok(SC.is_judged_pair("GER40", "1H") and SC.is_judged_pair("USOUSD", "1H"), "untracked + oil 1H")


def row(sym, sig, time_, d="2026-11-03", direc="Bullish", price="1.1", ev=""):
    return {"Date": d, "Time": time_, "Symbol": sym, "Direction": direc, "Signal Type": sig, "Signal Price": price, "Event": ev}


rows = {"4H": [row("EIGHTCAP:EURUSD", "LBull", "10:00:04", price="1.1000"),
               row("EIGHTCAP:XAUUSD", "LBull", "10:00:04"),
               row("EIGHTCAP:BTCUSD", "LBull", "10:00:04")],
        "1H": [row("EIGHTCAP:XAUUSD", "LBull", "10:01:04", price="2650.0"),
               row("EIGHTCAP:XAUUSD", "Tflow LBull", "10:01:05", price="2611.0",
                   ev="Tflow Bullish Signal @Zone (Support Zone x2 (W,M), Zone High: 2640.0, Zone Low: 2630.0): D Level: 2660.0, LL: 2635.0. Filtered: None."),
               row("EIGHTCAP:XAUUSD", "SBull", "10:27:10", price="2655.0"),
               row("EIGHTCAP:EURUSD", "SBull", "10:00:09"),
               row("EIGHTCAP:XCUUSD", "SBull", "10:00:09"),
               row("EIGHTCAP:UKOUSD", "SBull", "10:00:09"),
               row("EIGHTCAP:XAUUSD", "LBull", "", price="1")]}
L = SC.load_judged_alerts(rows, t("2026-11-02T00:00"), t("2026-11-02T00:00"))
keys = sorted(a["key"] for a in L["alerts"])
ok(keys == ["EURUSD|4H|Bull|2026-11-03T10:00:00+08:00", "XAUUSD|1H|Bull|2026-11-03T10:01:00+08:00",
            "XAUUSD|1H|Bull|2026-11-03T10:01:00+08:00#d"], f"judged keys {keys}")
ok(L["counts"] == {"rows_in_window": 9, "out_of_scope": 3, "out_of_tf": 2}, f"counts {L['counts']}")
ok(L["skipped"] == 1, "empty time skipped")
xau = next(a for a in L["alerts"] if a["key"].endswith("10:01:00+08:00"))
ok(xau["signal"] == "Tflow LBull" and xau["signal_price"] == 2650.0 and xau["signal_price_kind"] == "level", "Tflow chosen, plain twin price")
ok(xau["tflow"]["at_zone"] and xau["also_fired"] == ["LBull"], "tflow parsed")
d_ = next(a for a in L["alerts"] if a["key"].endswith("#d"))
ok(d_["delayed"] and d_["parent_key"] == xau["key"], "#d group")
ok(len(L["context"]) >= 4, "context includes out_of_tf")
only_t = SC.load_judged_alerts({"1H": [row("EIGHTCAP:XAUUSD", "Tflow SBull", "10:01:05", price="2611")]}, t("2026-11-02T00:00"), t("2026-11-02T00:00"))
ok(only_t["alerts"][0]["signal_price_kind"] == "tflow", "Tflow-only group -> kind tflow")

# ---------------------------------------------------------------- bars, matching, validation


def mkbars(start, n, step_s, base, slope, amp=0.0, period=3.0):
    out = []
    for i in range(n):
        o = base + slope * i + amp * math.sin(i / period)
        c = base + slope * (i + 0.8) + amp * math.sin((i + 0.8) / period)
        out.append({"time": int((start + dt.timedelta(seconds=step_s * i)).timestamp()), "open": o, "close": c,
                    "high": max(o, c) + abs(slope) * 0.6, "low": min(o, c) - abs(slope) * 0.6})
    return out


def mkread(sym, res, bars, labels, quote, read_at, up=1.0, fp=None):
    return {"state": {"symbol": sym, "resolution": res}, "bars": bars,
            "tat": {"name": "TATbyBinniOngv3|10S|Trend|NoTG|Zones", "total_labels": len(labels),
                    "labels": [{"text": x, "price": None} for x in labels]},
            "indicators": {"studies": [{"name": "TATbyBinniOngv3", "values": {"Up Trend": up, "Down Trend": 1.0 - up}}]},
            "quote": {"last": quote}, "read_at": int(read_at.timestamp() * 1000), "retried_tf": False,
            "relabel_retry": False, "fingerprint": fp or f"{sym}{res}"}


T4 = 14400
read_at = t("2026-11-03T10:18")
eb = mkbars(t("2026-10-24T10:00"), 61, T4, 1.0800, 0.0004, amp=0.004)  # bar 59 = 11-03 06:00-10:00, bar 60 forming
sig_i = 59  # starts 06:00, closes 10:00
eb[sig_i].update(open=1.1003, close=1.1012, high=1.1016, low=1.0998)
eb[sig_i - 1].update(close=1.0996, low=min(eb[sig_i - 1]["low"], 1.0996))
eurr = mkread("EIGHTCAP:EURUSD", "240", eb, ["MajD 1.10000 Sup h4", "MajD 1.11500 Res h4", "MinD 1.09700 Sup D"], 1.1013, read_at)
ok(SJ.validate_read(eurr, "240", "EIGHTCAP:EURUSD", {"price": 1.1013}, True) is None, "valid read")
ok(SJ.validate_read(dict(eurr, state={"symbol": "EIGHTCAP:EURUSD", "resolution": "60"}), "240", "EIGHTCAP:EURUSD", None, False)
   == "timeframe not confirmed", "wrong TF")
ok(SJ.validate_read(dict(eurr, state={"symbol": "EIGHTCAP:GBPUSD", "resolution": "240"}), "240", "EIGHTCAP:EURUSD", None, False)
   == "symbol not confirmed", "wrong symbol")
hb = mkbars(t("2026-10-30T02:00"), 61, 3600, 1.1, 0.0001)
ok(SJ.validate_read(dict(eurr, bars=hb), "240", "EIGHTCAP:EURUSD", None, False) == "bar spacing mismatch", "spacing")
ok(SJ.validate_read(eurr, "240", "EIGHTCAP:EURUSD", {"price": 1.20}, True) == "quote mismatch", "quote mismatch")
ok(SJ.validate_read(dict(eurr, tat=None), "240", "EIGHTCAP:EURUSD", None, False) == "TAT study not loaded", "TAT not loaded -> NO_DATA")
db = mkbars(t("2026-09-20T06:00"), 40, 86400, 1.07, 0.001)
ok(SJ.validate_read(mkread("EIGHTCAP:EURUSD", "1D", db, [], 1.1, read_at), "D", "EIGHTCAP:EURUSD", None, False) is None, "D == 1D")
ok(SJ.labels_stale(eurr, "EIGHTCAP:EURUSD240"), "same fingerprint as previous -> stale")
ok(not SJ.labels_stale(eurr, "other"), "different fingerprint -> fresh")
ok(SJ.labels_stale(mkread("EIGHTCAP:EURUSD", "240", eb, ["MajD 1.30000 Sup h4", "MajD 1.31000 Res h4"], 1.1013, read_at), None),
   "median level 18% from quote -> stale")

bars = SJ.to_bars(eurr)
closes = SJ.bar_closes(bars, T4)
a_eur = next(a for a in L["alerts"] if a["symbol"] == "EURUSD")
i, how = SJ.match_signal_bar(a_eur, bars, closes, T4)
ok(i == sig_i and how == "time", f"on-time match {i} {how}")
late = dict(a_eur, alert_dt=t("2026-11-03T12:05"), delayed=True, signal_price=1.1000, signal_price_kind="level")
i2, how2 = SJ.match_signal_bar(late, bars, closes, T4)
ok(i2 == sig_i and how2 == "cross", f"delayed cross match {i2} {how2}")
late_t = dict(late, signal_price_kind="tflow")
ok(SJ.match_signal_bar(late_t, bars, closes, T4)[1] == "time_fallback", "Tflow price never used for matching")
gap = [b for k, b in enumerate(bars) if k != sig_i]
gi, gh = SJ.match_signal_bar(a_eur, gap, SJ.bar_closes(gap, T4), T4)
ok(gh == "time_fallback", "missing nominal bar -> time_fallback")
ok(SJ.grid_offset(SJ.to_bars({"bars": mkbars(t("2026-11-04T02:00"), 25, T4, 1.1, 0.0001)}), "240", True) == 0, "FX 4H grid ok")
ok(SJ.grid_offset(SJ.to_bars({"bars": mkbars(t("2026-11-04T01:00"), 25, T4, 1.1, 0.0001)}), "240", True) is None, "FX 4H off-grid flagged")
xb = SJ.to_bars({"bars": mkbars(t("2026-11-01T08:01"), 50, 3600, 2600, 1.0)})
ok(SJ.grid_offset(xb, "60", False) == 1, "metal :01 grid observed")

# market open
gold = dict(xau, **{"class": "metal"})
r_break = mkread("EIGHTCAP:XAUUSD", "60", mkbars(t("2026-11-04T05:01"), 30, 3600, 2600, 1.0), [], 2630, t("2026-11-04T06:20"))
ok(SJ.market_closed(gold, r_break, t("2026-11-04T06:20"), 3600), "XAUUSD 17:20 NY break -> closed")
ok(not SJ.market_closed(a_eur, dict(r_break, bars=mkbars(t("2026-11-04T05:00"), 30, 3600, 1.1, 0.0001)), t("2026-11-04T06:20"), 3600),
   "FX not closed by the break rule")
ok(SJ.market_closed(a_eur, eurr, t("2026-11-04T10:18"), T4), "stale last bar -> closed")

# features, prefilter, tags
context = L["context"]
a_eur2 = dict(a_eur, sig_idx=sig_i, matched_by="time", bar_close=closes[sig_i], grid_offset_min=0)
dread = mkread("EIGHTCAP:EURUSD", "D", db, ["MajD 1.09500 Sup D"], 1.1013, read_at)
SJ.DAILY_BRIEF_DIR = TMP / "nobrief"
fb = SJ.build_features(a_eur2, eurr, dread, context, [], t("2026-11-03T10:20"))
ok(fb["tp1"] == 1.115 and fb["sl"] is not None and fb["sl"] < 1.1013, f"levels {fb['tp1']} {fb['sl']}")
ok(fb["features"]["htf"]["bias"] == "bullish" and fb["tags"]["htf"] == "aligned", "htf aligned")
ok(fb["features"]["cross_pair"]["score"] is not None, "fx cross pair scored")
ok(fb["features"]["structure"]["latest_low"] is None or isinstance(fb["features"]["structure"]["latest_low"], float), "swing price")
ok("weekend_gap" not in fb["tags"]["risk_flags"] and fb["judge_flags"] == [], "no weekend gap midweek")
code, detail, rr = SJ.prefilter(fb["sl"], fb["tp1"], 1.1013, True)
ok(code == "PASS" and rr and rr >= 1, f"prefilter {code} {rr}")
ok(SJ.prefilter(1.102, 1.115, 1.1013, True)[0] == "NO_STOP", "stop on wrong side")
ok(SJ.prefilter(1.0990, 1.1020, 1.1013, True)[0] == "RR_LT_1", "RR < 1")
ok(SJ.prefilter(1.0990, None, 1.1013, True)[1].startswith("OPEN RUN"), "open run")
nodr = mkread("EIGHTCAP:EURUSD", "D", db, [], 1.1, read_at)
nodr["indicators"] = {"studies": []}
ok(SJ.htf_bias_of(nodr) is None, "no TAT study -> htf bias null")
ok(SJ.weekend_between(t("2026-11-07T06:00"), t("2026-11-09T07:20")), "weekend gap detected")

# rank
mk = lambda zone, tfl, tier, rr: {"tflow": {"at_zone": zone} if tfl else None, "base_signal": tier, "rr": rr,
                                  "rr_group": 0, "nominal_close": t("2026-11-03T10:00")}
ranked = sorted([mk(False, False, "OptBull", 5), mk(True, True, "LBull", 1.5), mk(True, True, "LBull", 3.0)], key=SJ.rank_key)
ok([r["rr"] for r in ranked] == [3.0, 1.5, 5], "rank: @Zone first, then rr, plain OptBull last")

# daily brief
bd = TMP / "brief"
bd.mkdir()
(bd / "test_brief_10.md").write_text("x")
p1 = bd / "2026-11-02.json"
p1.write_text(json.dumps([{"symbol": "EIGHTCAP:EURUSD", "bias": "Bearish"}]))
os.utime(p1, (t("2026-11-02T06:40").timestamp(),) * 2)
p2 = bd / "2026-11-03.json"
p2.write_text("{corrupt")
os.utime(p2, (t("2026-11-03T06:40").timestamp(),) * 2)
e_ = SJ.daily_brief_entry("EURUSD", t("2026-11-03T10:20"), bd)
ok(e_ == {"bias": "bearish", "age_days": 1}, f"corrupt newest -> previous day {e_}")
p2.write_text(json.dumps([{"symbol": "EURUSD", "bias": "bullish"}]))
os.utime(p2, (t("2026-11-03T10:30").timestamp(),) * 2)
ok(SJ.daily_brief_entry("EURUSD", t("2026-11-03T10:20"), bd)["age_days"] == 1, "brief still being written -> skipped")

# chart image
imgd = TMP / "img"
imgd.mkdir()
(imgd / "261103-101502_eurusd_4H_chart.png").write_text("x")
ok(SJ.chart_image("EURUSD", "4H", t("2026-11-03T10:20"), imgd).endswith("261103-101502_eurusd_4H_chart.png"), "uppercase TF image")

# ---------------------------------------------------------------- tracker / walk


def entry(**kw):
    e = {"key": "K", "symbol": "EURUSD", "tf": "1H", "direction": "Bullish", "tracked": True, "verdict": "take",
         "entry_ref": {"time": "2026-11-03T10:18:00+08:00", "price": 1.1000}, "sl": 1.0990, "tp1": 1.1020,
         "price_basis": 0.0, "retest_level": None, "retest_window_bars": None,
         "outcome": {"status": "OPEN", "entry": None, "fill_time": None, "resolved_time": None, "bars": 0, "r": None,
                     "mfe_r": None, "mae_r": None, "reported": False}}
    e.update(kw)
    return e


def hbars(seq, start="2026-11-03T10:00"):
    return [{"dt": t(start) + dt.timedelta(hours=k), "open": o, "high": h, "low": l, "close": c} for k, (o, h, l, c) in enumerate(seq)]


later = t("2026-11-05T12:00")
e1 = entry()
SJ.walk(e1, hbars([(1.1, 1.1030, 1.0995, 1.1)] + [(1.1, 1.1025, 1.0995, 1.101)] * 3), later)
ok(e1["outcome"]["status"] == "TP1_HIT" and e1["outcome"]["r"] == 2.0, f"TP1 {e1['outcome']}")
ok(e1["outcome"]["bars"] == 1, "bar before the first full hour ignored (10:00 bar skipped)")
e2 = entry()
SJ.walk(e2, hbars([(1.1, 1.1001, 1.1, 1.1), (1.1, 1.1001, 1.0985, 1.099)]), later)
ok(e2["outcome"]["status"] == "SL_HIT" and e2["outcome"]["r"] == -1.0, "SL first")
e3 = entry()
SJ.walk(e3, hbars([(1.1, 1.1, 1.1, 1.1), (1.1, 1.1030, 1.0985, 1.1)]), later)
ok(e3["outcome"]["status"] == "SL_HIT", "same bar SL+TP -> SL")
e4 = entry(direction="Bearish", sl=1.1010, tp1=1.0980)
SJ.walk(e4, hbars([(1.1, 1.1005, 1.0995, 1.0995)] * 26), later)
ok(e4["outcome"]["status"] == "EXPIRED" and e4["outcome"]["r"] > 0, f"short EXPIRED R sign {e4['outcome']}")
e5 = entry(tp1=None)
SJ.walk(e5, hbars([(1.1, 1.1005, 1.0995, 1.1002)] * 26), later)
ok(e5["outcome"]["status"] == "OPEN_RUN_EXPIRED", "open run expired")
e6 = entry(verdict="wait_retest", retest_level=1.0995, retest_window_bars=3)
SJ.walk(e6, hbars([(1.1, 1.1, 1.1, 1.1), (1.1, 1.1025, 1.0994, 1.102)]), later)
ok(e6["outcome"]["status"] == "TP1_HIT" and e6["outcome"]["entry"] == 1.0995 and e6["outcome"]["bars"] == 1,
   f"fill then TP on fill bar {e6['outcome']}")
e7 = entry(verdict="wait_retest", retest_level=1.0995, retest_window_bars=2)
SJ.walk(e7, hbars([(1.1, 1.1, 1.1, 1.1), (1.1, 1.1010, 1.0998, 1.1), (1.1, 1.1015, 1.0998, 1.1)]), later)
ok(e7["outcome"]["status"] == "NO_FILL" and e7["outcome"]["mfe_r"] == 3.0, f"NO_FILL mfe in |retest-sl| {e7['outcome']}")
e8 = entry(price_basis=10.0)
SJ.walk(e8, hbars([(0, 0, 0, 0), (11.1, 11.1030, 11.0995, 11.1)]), later)
ok(e8["outcome"]["status"] == "TP1_HIT", "basis subtracted")
e9 = entry()
SJ.walk(e9, hbars([(1.1, 1.1001, 1.0999, 1.1)] * 3), t("2026-11-14T10:00"))
ok(e9["outcome"]["status"] == "NO_DATA", "10 days open -> NO_DATA")
e10 = entry(tf="4H")
SJ.walk(e10, hbars([(1.1, 1.1005, 1.0995, 1.1)] * 30), later)
ok(e10["outcome"]["status"] == "OPEN", "4H window is 120 bars, still open after 29")

# ---------------------------------------------------------------- scorecard


def sc_entry(verdict, basis, status, r=None, mfe=None, prefilter="PASS"):
    return {"tracked": True, "alert_time": "2026-11-03T10:00:00+08:00", "verdict": verdict, "prefilter": prefilter,
            "judge": {"basis": basis} if basis else None, "outcome": {"status": status, "r": r, "mfe_r": mfe}}


es = [sc_entry("take", "precedent", "TP1_HIT", 2.0, 2.5), sc_entry("take", "precedent", "SL_HIT", -1.0, 0.3),
      sc_entry("take", "precedent", "OPEN"), sc_entry("take", "own_analysis", "EXPIRED", 0.4, 1.0),
      sc_entry("take", "own_analysis", "OPEN_RUN_EXPIRED", 1.2, 1.5), sc_entry("wait_retest", "precedent", "NO_FILL", 0, 3.0),
      sc_entry("skip", "own_analysis", "NO_DATA"), sc_entry(None, None, "SL_HIT", -1.0, 0.2, prefilter="RR_LT_1"),
      sc_entry("pending", None, "OPEN"), dict(sc_entry("take", "precedent", "TP1_HIT", 3, 3), tracked=False)]
sc = ST.scorecard(es, t("2026-11-01T00:00"))["rows"]
ok(sc["take (precedent)"] == {"n": 3, "resolved": 2, "tp1_pct": 50, "avg_r": 0.5, "avg_mfe_r": 1.4, "no_fill": 0}, f"take prec {sc['take (precedent)']}")
ok(sc["take (own)"]["resolved"] == 2 and sc["take (own)"]["tp1_pct"] == 0 and sc["take (own)"]["avg_r"] == 0.8, "take own")
ok(sc["wait_retest (precedent)"]["no_fill"] == 1 and sc["wait_retest (precedent)"]["resolved"] == 0, "no fill excluded")
ok(sc["filtered"]["resolved"] == 1 and sc["skip (own)"]["resolved"] == 0, "filtered + NO_DATA excluded")

# ---------------------------------------------------------------- verdict validation
CK = SJ.checklist_ids()
ok({"R01", "R13", "R25"} <= CK, "checklist ids")
surv = {"key": "K", "tf": "1H", "direction": "Bullish", "sl": 1.0990, "entry_ref": {"price": 1.1000}, "atr": 0.0010}
good = {"key": "K", "verdict": "take", "basis": "precedent", "confidence": "medium", "retest_level": None,
        "retest_window_bars": None, "controlling_cases": ["c1"], "distinguished": [], "doctrine": ["R01"],
        "reason": "fine", "dissent": None, "question_for_binni": None}
V = lambda **kw: SJ.validate_verdict(dict(good, **kw), surv, {"c1", "c2"}, CK)
ok(V()[1] is None, "valid precedent verdict")
ok(V(basis="own_analysis", controlling_cases=[], doctrine=["R01", "R08"])[1] is None, "valid own verdict")
for kw, why in ((dict(verdict="buy"), "enum"), (dict(controlling_cases=["zz"]), "unknown case"),
                (dict(doctrine=["R99"]), "unknown R-id"), (dict(verdict="no_ruling"), "no question"),
                (dict(reason="a|b"), "pipe"), (dict(basis="own_analysis"), "own with controlling"),
                (dict(basis="own_analysis", controlling_cases=[], doctrine=["R01"]), "own one R-id"),
                (dict(controlling_cases=[]), "precedent without case"),
                (dict(verdict="wait_retest", retest_level=1.0980, retest_window_bars=3), "retest 1 ATR beyond SL")):
    ok(V(**kw)[1] is not None, f"rejects {why}")
v_, e_, w_ = V(verdict="wait_retest", retest_level=1.09895, retest_window_bars=3)
ok(e_ is None and abs(v_["retest_level"] - 1.0991) < 1e-9 and w_, f"snap within 0.1 ATR {v_['retest_level']}")
ok(V(verdict="no_ruling", question_for_binni="which?", basis="own_analysis", controlling_cases=[], doctrine=["R01", "R02"])[1] is None,
   "no_ruling own")

# ---------------------------------------------------------------- doctrine citations resolve
txt = SJ.CHECKLIST.read_text()
for m in re.finditer(r"\*\*(R\d+)\*\*.*?\(see (.*)\)\s*$", txt, re.M):
    for page, claims in re.findall(r"\[[^\]]+\]\(\.\./\.\./\.\./\.\./wiki/concepts/([a-z-]+)\.md\)((?: claim \d+,?)*)", m.group(2)):
        body = (ROOT / "wiki" / "concepts" / f"{page}.md").read_text()
        sec = re.search(r"^## key claims\s*$(.*?)^## ", body, re.M | re.I | re.S)
        ok(sec is not None, f"{m.group(1)}: {page} has Key claims")
        items = [ln for ln in sec.group(1).splitlines() if re.match(r"^(- |\d+\. )", ln)]
        for n_ in re.findall(r"\d+", claims):
            ok(1 <= int(n_) <= len(items), f"{m.group(1)}: {page} claim {n_} exists ({len(items)} claims)")
ok(len(CK) >= 15, "at least 15 rules")

# ---------------------------------------------------------------- ledger shards
SJ.write_ledger([{"key": "EURUSD|4H|Bull|2026-11-01T02:00:00+08:00#d", "prepass_key": "EURUSD|4H|Bull|2026-11-01T02:00:00+08:00#d", "run_id": "a"}])
ok((TMP / "data" / "ledger-2026-11.json").exists(), "shard by month")
SJ.write_ledger([{"key": "EURUSD|4H|Bull|2026-10-31T22:00:00+08:00", "prepass_key": "EURUSD|4H|Bull|2026-11-01T02:00:00+08:00#d", "run_id": "b"}],
                ["EURUSD|4H|Bull|2026-11-01T02:00:00+08:00#d"])
nov = json.loads((TMP / "data" / "ledger-2026-11.json").read_text())["entries"]
octo = json.loads((TMP / "data" / "ledger-2026-10.json").read_text())["entries"]
ok(nov == [] and len(octo) == 1, "re-key moves entry across month shards")
dup = SJ.collapse([{"key": "x", "prepass_key": "p", "run_id": "1"}, {"key": "y", "prepass_key": "p", "run_id": "2"}])
ok([e["key"] for e in dup] == ["y"], "crash duplicate collapsed")
(TMP / "data" / "ledger-2026-09.json").write_text("{bad")
try:
    SJ.load_ledger(["2026-09"])
    ok(False, "corrupt shard should raise")
except SJ.Exit as ex:
    ok(ex.code == 5, "corrupt shard -> exit 5")
(TMP / "data" / "ledger-2026-09.json").unlink()
for f in TMP.joinpath("data").glob("ledger-*.json"):
    f.unlink()

# ---------------------------------------------------------------- end to end: run -> verdicts -> apply
cases = [{"id": "c-eur", "note": "wiki/AHH Session Notes/2026-10-30-ahh-access-time.md", "date": "2026-10-30",
          "session_type": "ahh-access-time", "presenter": "binni", "opportunity_no": 1, "section": "x", "instrument": "EURUSD",
          "asset_class": "fx", "tf": "4h", "direction": "long", "verdict": "take", "condition": None, "setup": ["breakout"],
          "location": [], "structure": "with_trend", "htf": "aligned", "risk_flags": [], "signal_named": None, "levels": "1.1000",
          "quote": "Euro dollar long above 1.10", "timestamp": None, "quote_in_raw": True, "hindsight": None}]
(TMP / "cases" / "cases.jsonl").write_text("\n".join(json.dumps(c) for c in cases) + "\n")

xb = mkbars(t("2026-10-29T06:01"), 101, 3600, 2580, 0.7, amp=6)  # last start 11-03 11:01? 06:01 + 100h = 11-02 10:01 ... adjust below
start = t("2026-11-03T10:01") - dt.timedelta(hours=99)
xb = mkbars(start, 101, 3600, 2580, 0.7, amp=6)
xi = 98  # start 09:01, close 10:01
xb[xi].update(open=2647.0, close=2652.0, high=2653.0, low=2646.0)
xau60 = mkread("EIGHTCAP:XAUUSD", "60", xb, ["MajD 2650.00 Sup h1", "MajD 2700.00 Res h4"], 2652.0, read_at, fp="x60")
xau240 = mkread("EIGHTCAP:XAUUSD", "240", mkbars(t("2026-10-25T02:00"), 60, T4, 2550, 2.0), ["MajD 2640.00 Sup h4"], 2652.0, read_at, fp="x240")
eurd = mkread("EIGHTCAP:EURUSD", "D", db, ["MajD 1.09500 Sup D"], 1.1013, read_at, fp="ed")
passf = TMP / "pass.json"
passf.write_text(json.dumps({"items": {"EIGHTCAP:XAUUSD": {"60": xau60, "240": xau240},
                                       "EIGHTCAP:EURUSD": {"240": dict(eurr, fingerprint="e240"), "D": eurd}},
                             "errors": [], "fatal": None}))


def fake_tabs():
    return rows, {"1H": "ok", "4H": "ok"}, {"1H": False, "4H": False}


ybar = [{"dt": b_["dt"] - dt.timedelta(minutes=1), "open": b_["open"] + 10, "high": b_["high"] + 10, "low": b_["low"] + 10,
         "close": b_["close"] + 10} for b_ in SJ.to_bars(xau60)]
SC.fetch_tabs = fake_tabs
SJ.yahoo_bars = lambda tk, *a, **k: ((ybar, {"price": 2662.0, "time": read_at.timestamp()}) if tk == "GC=F"
                                     else ([], {"price": 1.1013, "time": read_at.timestamp()}))
SC.load_calendar = lambda *a, **k: ([], [])
SJ.chart_image = lambda *a, **k: None
NOW = "2026-11-03T10:20:00+08:00"
code, out, err = run_main(["run", "--ignore-skip-window", "--now", NOW, "--pass-file", str(passf)])
ok(code == 0 and out.count("\n") == 1 and out.startswith("PACKET "), f"run stdout one line ({code}) {out} {err[-800:]}")
pk_path = Path(out.split()[1])
pk_path = pk_path if pk_path.is_absolute() else ROOT / pk_path
P = json.loads(pk_path.read_text())
c = P["counts"]
ok(c["groups"] == c["already_seen_pre"] + c["stale"] + c["chart_candidates"], f"identity 1 {c}")
ok(c["chart_candidates"] == c["already_seen_post"] + c["duplicate_delayed"] + c["closed"] + c["no_data"] + c["no_stop"]
   + c["rr_lt_1"] + c["pass"], f"identity 2 {c}")
ok(c["recorded"] == c["stale"] + c["closed"] + c["no_data"] + c["no_stop"] + c["rr_lt_1"] + c["pass"], "identity 3")
ok(c["pass"] == c["judged"] + c["unjudged_cap"], "identity 4")
ok(c["duplicate_delayed"] == 1, f"#d XAUUSD row matched the parent bar -> duplicate {c}")
sv = {s["symbol"]: s for s in P["survivors"]}
ok(set(sv) == {"EURUSD", "XAUUSD"}, f"survivors {set(sv)} filtered {P['filtered']}")
ok(sv["EURUSD"]["has_precedents"] and not sv["XAUUSD"]["has_precedents"], "EURUSD has a precedent, XAUUSD none")
ok(sv["XAUUSD"]["features"]["tflow"]["at_zone"] and sv["XAUUSD"]["signal"] == "Tflow LBull", "XAUUSD Tflow @Zone")
led = SJ.load_ledger(["2026-11"])
xe = next(e for e in led if e["symbol"] == "XAUUSD")
ok(abs(xe["price_basis"] - 10.0) < 1e-6, f"price basis Yahoo :00 vs TV :01 {xe['price_basis']}")
ok(any(r[1] == "10:27:10" for r in xe["row_times"]), "late row merged into parent row_times")
brief = (ROOT / P["brief_path"] if not Path(P["brief_path"]).is_absolute() else Path(P["brief_path"])).read_text()
ok("## S1 —" in brief and "## S2 —" in brief and "None — own analysis required" in brief, "brief sections")
ok(max(len(x) for x in brief.splitlines()) <= 400 and "unscored" in brief, "brief lines <= 400, null hindsight unscored")

# second run: nothing new -> already seen
code2, out2, _ = run_main(["run", "--ignore-skip-window", "--now", NOW, "--pass-file", str(passf)])
P2 = json.loads((ROOT / out2.split()[1] if not Path(out2.split()[1]).is_absolute() else Path(out2.split()[1])).read_text())
ok(P2["run_id"].endswith("_2") and P2["counts"]["already_seen_pre"] == 2 and not P2["survivors"], f"rerun already seen {P2['counts']}")

vpath = Path(P["verdicts_path"]) if Path(P["verdicts_path"]).is_absolute() else ROOT / P["verdicts_path"]
vpath.write_text(json.dumps({"run_id": P["run_id"], "verdicts": [
    {"key": sv["EURUSD"]["key"], "verdict": "take", "basis": "precedent", "confidence": "medium", "retest_level": None,
     "retest_window_bars": None, "controlling_cases": ["c-eur"], "distinguished": [], "doctrine": ["R04", "R08"],
     "reason": "4H LBull with trend, Binni long above 1.10", "dissent": None, "question_for_binni": None},
    {"key": sv["XAUUSD"]["key"], "verdict": "wait_retest", "basis": "own_analysis", "confidence": "low",
     "retest_level": 2650.0, "retest_window_bars": 4, "controlling_cases": [], "distinguished": [], "doctrine": ["R02", "R06"],
     "reason": "Tflow @Zone, entry extended; wait for the h1 level", "dissent": None, "question_for_binni": None}]}))
code, out, err = run_main(["apply", "--packet", str(pk_path)])
ok(code == 0 and out.startswith("REPORT"), f"apply ({code}) {err[-600:]}")
rep = (TMP / "report" / "2026-11-03-signal-judge.md").read_text()
ok(rep.startswith("---\ntype: report") and "# ⚖️ Signal Judge — 2026-11-03 [" in rep, "report header with time")
ok(f"<!-- signal-judge-run:{P['run_id']} -->" in rep and "## 🕒 Signal Judge Run — [" in rep, "marker + run heading")
ok("| [[EURUSD]] (🟢 Bull) | 4H |" in rep and "✅ Take (medium)" in rep and "| Binni |" in rep, "EURUSD row")
ok("Own analysis" in rep and "⏳ Wait for retest @ 2650" in rep, "XAUUSD own wait row")
ok("AHH Access Time 2026-10-30 · EURUSD](<../" in rep, "precedent link angle-bracketed")
ok("TOC:START" in rep or "Table of Contents" in rep, "toc")
ok(not re.search(r"^#+ .*\[\[", rep, re.M) and not re.search(r"!\[[^\]]*\[", rep), "no wikilinks in headings / alt text")
led = {e["key"]: e for e in SJ.load_ledger(["2026-11"])}
ok(led[sv["EURUSD"]["key"]]["judge"]["basis"] == "precedent" and led[sv["XAUUSD"]["key"]]["verdict"] == "wait_retest", "ledger verdicts")
code, out, _ = run_main(["apply", "--packet", str(pk_path)])
ok(code == 0 and "already applied" in out, "apply idempotent")
ok((TMP / "report" / "2026-11-03-signal-judge.md").read_text() == rep, "report unchanged on second apply")

# apply guards
dry = TMP / "dry"
dry.mkdir()
code, out, _ = run_main(["run", "--dry-run", "--out", str(dry), "--ignore-skip-window", "--now", NOW, "--pass-file", str(passf)])
dpk = Path(out.split()[1]) if Path(out.split()[1]).is_absolute() else ROOT / out.split()[1]
DP = json.loads(dpk.read_text())
ok(DP["dry_run"] and "diagnostics" in DP, "dry-run packet with diagnostics")
code, _, _ = run_main(["apply", "--packet", str(dpk)])
ok(code == 2, "dry-run packet refused")
other = dict(P, data_dir="elsewhere", run_id="zz")
op = TMP / "runs" / "zz_packet.json"
op.write_text(json.dumps(other))
ok(run_main(["apply", "--packet", str(op)])[0] == 2, "other data dir refused")
saved = os.environ.pop("SIGNAL_JUDGE_RUNS_DIR")
ok(run_main(["track"])[0] == 6, "test dirs without RUNS_DIR -> exit 6")
os.environ["SIGNAL_JUDGE_RUNS_DIR"] = saved
code, out, _ = run_main(["stats", "--json"])
ok(code == 0 and "take (precedent)" in out, "stats json")
code, out, _ = run_main(["run", "--now", "2026-11-07T10:00:00+08:00"])
ok(code == 10 and out.strip() == "SKIPPED weekend", "weekend skip")

# duplicate verdicts + missing verdict
code, out, err = run_main(["run", "--ignore-skip-window", "--now", NOW, "--pass-file", str(passf), "--symbol", "EURUSD"])
# (nothing new for EURUSD -> zero survivors; apply still writes a section)
p3 = Path(out.split()[1]) if Path(out.split()[1]).is_absolute() else ROOT / out.split()[1]
code, out, err = run_main(["apply", "--packet", str(p3)])
ok(code == 0, f"zero-survivor apply {err[-300:]}")
ok((TMP / "report" / "2026-11-03-signal-judge.md").read_text().count("## 🕒 Signal Judge Run") == 2, "second section appended")

# ---------------------------------------------------------------- review round 1 regressions
me = {"signal": "LBull", "also_fired": [], "row_times": [["2026-11-03", "10:00:04", "X"]], "verdict": "take"}
ok(SJ.merge_rows(me, {"signal": "LBull", "also_fired": [], "row_times": [["2026-11-03", "10:00:04", "X"]]}) is False
   and me["also_fired"] == [], "same signal seen again -> no change, own signal not in also_fired")
mu = {"signal": "LBull", "also_fired": [], "row_times": [], "verdict": "pending", "tflow": False}
SJ.merge_rows(mu, {"signal": "Tflow LBull", "also_fired": ["LBull"], "row_times": [], "tflow": {"at_zone": True}})
ok(mu["signal"] == "Tflow LBull" and mu["also_fired"] == ["LBull"], f"Tflow upgrade also_fired {mu['also_fired']}")
vv, ee, _ = SJ.validate_verdict(dict(good, dissent="a\nb | c", distinguished=[{"case_id": "c2", "why": "x\ny"}]), surv, {"c1", "c2"}, CK)
ok(ee is None and vv["dissent"] == "a b / c" and vv["distinguished"][0]["why"] == "x y", "free-text fields flattened")
# a retryable entry already re-keyed (K1 '#d' -> K2) is retried, not swallowed as already_seen
K2 = sv["EURUSD"]["key"]
eK = dict(SJ.load_ledger(["2026-11"])[0])
eK = next(e for e in SJ.load_ledger(["2026-11"]) if e["key"] == K2)
eK = dict(eK, prepass_key=K2 + "#d", delayed=True, parent_key=None, prefilter="CLOSED", retryable=True, attempts=0,
          verdict=None, judge=None, alert_time="2026-11-03T10:15:00+08:00", signal_price=1.1000, signal_price_kind="level")
SJ.write_ledger([eK])
rows_no_eur = {t_: [r_ for r_ in rs if "EURUSD" not in r_["Symbol"]] for t_, rs in rows.items()}
SC.fetch_tabs = lambda: (rows_no_eur, {"1H": "ok", "4H": "ok"}, {"1H": False, "4H": False})
code, out, err = run_main(["run", "--ignore-skip-window", "--now", NOW, "--pass-file", str(passf), "--symbol", "EURUSD"])
P4 = json.loads((Path(out.split()[1]) if Path(out.split()[1]).is_absolute() else ROOT / out.split()[1]).read_text())
eK2 = next(e for e in SJ.load_ledger(["2026-11"]) if e["key"] == K2)
ok(P4["counts"]["retried"] == 1 and P4["counts"]["already_seen_post"] == 0 and eK2["prefilter"] == "PASS" and eK2["attempts"] == 1,
   f"re-keyed retry reaches the pre-filter {P4['counts']} {eK2['prefilter']} {eK2['attempts']}")
# a merge into a retryable stored entry survives that entry's own retry (rows + Tflow upgrade kept)
eK3 = next(e for e in SJ.load_ledger(["2026-11"]) if e["key"] == K2)
eK3 = dict(eK3, prefilter="CLOSED", retryable=True, attempts=0, verdict=None, judge=None,
           row_times=eK3["row_times"] + [["2026-11-03", "10:20:00", "EIGHTCAP:EURUSD"]],
           signal="Tflow LBull", tflow=True, tflow_event={"at_zone": True}, at_zone=True, also_fired=["LBull"])
SJ.write_ledger([eK3])
SC.fetch_tabs = fake_tabs  # the EURUSD sheet row is present: the retry is driven by it, not rebuilt from the ledger
code, out, err = run_main(["run", "--ignore-skip-window", "--now", NOW, "--pass-file", str(passf), "--symbol", "EURUSD"])
P5 = json.loads((Path(out.split()[1]) if Path(out.split()[1]).is_absolute() else ROOT / out.split()[1]).read_text())
ok(P5["counts"]["retried"] == 1, f"a retryable entry is picked up once per run {P5['counts']}")
eK4 = next(e for e in SJ.load_ledger(["2026-11"]) if e["key"] == K2)
ok(any(r[1] == "10:20:00" for r in eK4["row_times"]) and eK4["signal"] == "Tflow LBull" and "Tflow LBull" not in eK4["also_fired"],
   f"retry keeps merged rows and Tflow upgrade {eK4['signal']} {eK4['also_fired']}")
# two sheet rows (on-time + late '#d') both pointing at one retryable entry -> retried once, rows folded
eK5 = next(e for e in SJ.load_ledger(["2026-11"]) if e["key"] == K2)
eK5 = dict(eK5, prepass_key=K2 + "#d", prefilter="CLOSED", retryable=True, attempts=0, verdict=None, judge=None,
           row_times=[["2026-11-03", "10:15:00", "EIGHTCAP:EURUSD"]])
SJ.write_ledger([eK5])
rows_two = {t_: list(rs) for t_, rs in rows.items()}
rows_two["4H"] = rows_two["4H"] + [row("EIGHTCAP:EURUSD", "LBull", "10:15:00", price="1.1000")]
SC.fetch_tabs = lambda: (rows_two, {"1H": "ok", "4H": "ok"}, {"1H": False, "4H": False})
code, out, err = run_main(["run", "--ignore-skip-window", "--now", NOW, "--pass-file", str(passf), "--symbol", "EURUSD"])
P6 = json.loads((Path(out.split()[1]) if Path(out.split()[1]).is_absolute() else ROOT / out.split()[1]).read_text())
eur_entries = [e for e in SJ.load_ledger(["2026-11"]) if e["symbol"] == "EURUSD"]
ok(P6["counts"]["retried"] == 1 and len([s_ for s_ in P6["survivors"] if s_["symbol"] == "EURUSD"]) <= 1 and len(eur_entries) == 1,
   f"one entry retried once {P6['counts']} entries={[e['key'] for e in eur_entries]}")
ok({r[1] for r in eur_entries[0]["row_times"]} >= {"10:00:04", "10:15:00"}, f"both rows kept {eur_entries[0]['row_times']}")
ok(P6["counts"]["groups"] == P6["counts"]["already_seen_pre"] + P6["counts"]["stale"] + P6["counts"]["chart_candidates"], "identity holds with fold")
# a stored '#d' retry that turns out to be its (judged) parent: its stored rows/signals are carried, then it is deleted
base_k = next(e for e in SJ.load_ledger(["2026-11"]) if e["key"] == K2)
SJ.write_ledger([dict(base_k, verdict="take", retryable=False, prefilter="PASS", prepass_key=K2, row_times=[["2026-11-03", "10:00:04", "EIGHTCAP:EURUSD"]]),
                 dict(base_k, key=K2 + "#d", prepass_key=K2 + "#d", parent_key=K2, delayed=True, retryable=True, prefilter="CLOSED",
                      attempts=0, verdict=None, judge=None, alert_time="2026-11-03T10:40:00+08:00", signal="Tflow LBull",
                      tflow=True, tflow_event={"at_zone": True}, row_times=[["2026-11-03", "10:50:00", "EIGHTCAP:EURUSD"]])])
rows_late = {t_: list(rs) for t_, rs in rows.items()}
rows_late["4H"] = rows_late["4H"] + [row("EIGHTCAP:EURUSD", "LBull", "10:40:00", price="1.1000")]
SC.fetch_tabs = lambda: (rows_late, {"1H": "ok", "4H": "ok"}, {"1H": False, "4H": False})  # retry driven by the sheet row
code, out, err = run_main(["run", "--ignore-skip-window", "--now", NOW, "--pass-file", str(passf), "--symbol", "EURUSD"])
eur = [e for e in SJ.load_ledger(["2026-11"]) if e["symbol"] == "EURUSD"]
ok(len(eur) == 1 and eur[0]["key"] == K2, f"#d retry absorbed into its parent, deleted {[e['key'] for e in eur]}")
ok({"10:40:00", "10:50:00"} <= {r[1] for r in eur[0]["row_times"]} and eur[0]["signal"] not in eur[0]["also_fired"] and eur[0]["verdict"] == "take",
   f"stored rows carried, judged parent kept {eur[0]['row_times']} {eur[0]['also_fired']}")
SC.fetch_tabs = fake_tabs

# resolve_key: chained replacement within one run (O absorbed into K's stored copy, then K re-keyed to K2)
k_ledger = {"key": "K"}
k2 = {"key": "K2"}
rep = {"O": k_ledger, "K": k2}
ok(SJ.resolve_key("O", [], rep, {"O", "K"}, {"K": k_ledger, "O": {"key": "O"}}) is k2, "O -> stale K copy -> K2 (chain followed)")
ok(SJ.resolve_key("K", [], rep, {"O", "K"}, {"K": k_ledger}) is k2, "deleted K resolves to its replacement")
ok(SJ.resolve_key("Z", [], {}, {"Z"}, {"Z": {"key": "Z"}}) is None, "a deleted key with no replacement is not resurrected")
rec = {"key": "R"}
ok(SJ.resolve_key("R", [({}, rec)], {}, set(), {"R": {"key": "R"}}) is rec, "this run's recorded entry wins")
loop_a, loop_b = {"key": "A"}, {"key": "B"}
ok(SJ.resolve_key("A", [], {"A": loop_b, "B": loop_a}, {"A", "B"}, {}) in (loop_a, loop_b), "a replacement cycle terminates")

# ---------------------------------------------------------------- tv_session.sh owner / fail / trap (stub PATH)
stub = TMP / "bin"
stub.mkdir()
calls = TMP / "calls.log"
for name, body in (("osascript", "exit 0"), ("pkill", "exit 0"), ("pgrep", "exit 1"), ("open", "exit 0"),
                   ("node", 'case "$*" in *"layout switch"*) exit 1;; *state*) echo \'{"success": true}\';; esac; exit 0'),
                   ("sleep", "exit 0")):
    p_ = stub / name
    p_.write_text(f"#!/bin/bash\necho {name} \"$@\" >> {calls}\n{body}\n")
    p_.chmod(0o755)
env = dict(os.environ, PATH=f"{stub}:/usr/bin:/bin", TV_LOCK_DIR=str(TMP / "tvlock"))


def tvs(action, **kw):
    return subprocess.run(["bash", str(ROOT / "scripts" / "tv_session.sh"), action], env=dict(env, **kw),
                          capture_output=True, text=True, timeout=60)


r = tvs("stop", TV_LOCK_OWNER="x")
ok(r.returncode == 0 and "not the lock owner" in r.stdout and not calls.exists(), "stop without lock leaves TradingView alone")
(TMP / "tvlock").mkdir()
(TMP / "tvlock" / "info").write_text("pid=1 owner=y\n")
r = tvs("stop", TV_LOCK_OWNER="x")
ok("not the lock owner" in r.stdout and not calls.exists(), "foreign lock left alone")
(TMP / "tvlock" / "info").write_text("pid=1 script=x owner=x\n")
r = tvs("stop", TV_LOCK_OWNER="x")
ok(calls.exists() and "osascript" in calls.read_text() and not (TMP / "tvlock").exists(), "owned stop quits and releases")
calls.unlink()
(TMP / "tvlock").mkdir()
(TMP / "tvlock" / "info").write_text("pid=1\n")
penv = dict(env)
(stub / "pgrep").write_text(f"#!/bin/bash\necho pgrep \"$@\" >> {calls}\necho 123\n")
r = tvs("start", TV_LOCK_OWNER="x", TV_LOCK_FAIL_ON_TIMEOUT="1", TV_LOCK_MAX_WAIT_SECS="0")
logtxt = lambda: calls.read_text() if calls.exists() else ""
ok(r.returncode == 75 and (TMP / "tvlock").exists() and "osascript" not in logtxt(), f"busy lock -> 75 {r.returncode} {r.stdout[-200:]}")
(stub / "pgrep").write_text(f"#!/bin/bash\necho pgrep \"$@\" >> {calls}\nexit 1\n")
import shutil  # noqa: E402
shutil.rmtree(TMP / "tvlock")
if calls.exists():
    calls.unlink()
r = tvs("start", TV_LOCK_OWNER="x")
ok(r.returncode == 1 and "osascript" in logtxt() and not (TMP / "tvlock").exists(),
   f"failed owned start quits TradingView ({r.returncode}) {r.stdout[-300:]}")
calls.unlink()
r = tvs("start")
ok(r.returncode == 1 and "osascript" not in logtxt(), f"unowned failed start unchanged (no quit) {r.returncode}")

print(f"OK — {N} checks passed (temp dir {TMP})")
