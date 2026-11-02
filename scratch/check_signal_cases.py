#!/usr/bin/env python3
"""Fixture checks for scripts/signal_cases.py (Signal Judge Phase 1).

No network, no TradingView, no writes outside a temp dir:
    python3 scratch/check_signal_cases.py
"""
import contextlib
import datetime as dt
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="sigcases_"))
os.environ["SIGNAL_CASES_DIR"] = str(TMP / "store")
os.environ["SIGNAL_JUDGE_RUNS_DIR"] = str(TMP / "runs")
sys.path.insert(0, str(ROOT))

import scripts.signal_cases as S  # noqa: E402

SGT = S.SGT
NOTE = ROOT / "wiki" / "AHH Session Notes" / "2026-10-27-ahh-access-time.md"
passed = 0


def ok(cond, msg):
    global passed
    if not cond:
        raise AssertionError(msg)
    passed += 1


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = S.main(argv)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def reset_store():
    for p in (TMP / "store").glob("*"):
        p.unlink()


GBPAUD = {"opportunity_no": 1, "section": "📈 Trading Opportunities", "instrument": "GBPAUD",
          "asset_class": "fx", "tf": "4h", "direction": "short", "verdict": "take", "condition": None,
          "setup": ["trendline_break", "trend_continuation", "laggard"], "location": ["htf_level_behind"],
          "structure": "with_trend", "htf": "aligned", "risk_flags": [], "signal_named": None,
          "levels": "Resistance from higher-timeframe levels",
          "quote": "Today the 4H broke the uptrend line, so look for a short as the continuation of the AUD strength",
          "timestamp": "29:10–29:40"}
GBPJPY = {"opportunity_no": 7, "section": "📈 Trading Opportunities", "instrument": "GBPJPY",
          "asset_class": "fx", "tf": "unspecified", "direction": "long", "verdict": "conditional",
          "condition": "lower timeframe shows support and a clear move above the resistance zone",
          "setup": ["retest"], "location": ["htf_level_behind"], "structure": "unspecified",
          "htf": "aligned", "risk_flags": [], "signal_named": None,
          "levels": "own resistance-turned-support",
          "quote": "Check the lower timeframe for support and a clear move above the resistance zone",
          "timestamp": "43:53–44:20"}


def staged(cases, name="staged.json"):
    p = TMP / name
    p.write_text(json.dumps(cases))
    return str(p)


# ---------------------------------------------------------------- symbols
for s in ("[[US100]]", "NASDAQ", "EIGHTCAP:NDQ100"):
    ok(S.canon_instrument(s) == "NDQ100", f"canon {s}")
ok(S.canon_instrument("JP225") == "JPN225", "JP225")
for s in ("DXY", "TVC:DXY", "USDX"):
    ok(S.canon_instrument(s) == "USDX", f"canon {s}")
ok(S.canon_instrument("GOLD") == "XAUUSD", "GOLD")
ok(S.instrument_class("GBPUSD") == "fx", "fx class")
ok(S.instrument_class("XAUUSD") == "metal", "gold is metal, not fx")
ok(S.instrument_class("US30") == "index", "index class")
ok(S.instrument_class("GER40") == "untracked", "untracked")
ok(S.instrument_class("BTCUSD") == "out", "crypto out")
ok(S.instrument_currencies("XAUJPY") == ["USD", "JPY"], "XAUJPY ccy")
ok(S.instrument_currencies("JPN225") == ["JPY"], "JPN225 ccy")

# ---------------------------------------------------------------- quote check
note_norm = S.norm_text(NOTE.read_text())
ok(S.norm_text(GBPAUD["quote"]) in note_norm, "GBPAUD worked quote")
ok(S.norm_text(GBPJPY["quote"]) in note_norm, "GBPJPY worked quote")
ok(S.norm_text("Binni says buy everything now") not in note_norm, "fabricated quote")
ok(S.norm_text("The user had asked about a [[GBPJPY]] long") in note_norm, "[[ ]] markup quote")
ok(S.norm_text("Today the **4H broke the uptrend line**") in note_norm, "** markup quote")

# ---------------------------------------------------------------- add
code, out, _ = run(["add", "--presenter", "binni", "--note", str(NOTE), "--file", staged([dict(GBPAUD, quote="made up words here")])])
ok(code == 3, f"all-rejected -> 3 (got {code})")
ok(not S.load_done(), "note stays pending after exit 3")
ok((TMP / "runs" / "cases_2026-10-27-ahh-access-time.rejects.json").exists(), "rejects file written")

bad = [dict(GBPAUD, setup=["moonshot"]), dict(GBPJPY, condition=None), dict(GBPAUD, asset_class="index"),
       dict(GBPAUD, opportunity_no=2)]
code, out, err = run(["add", "--presenter", "binni", "--note", str(NOTE), "--file", staged(bad + [GBPAUD, GBPJPY])])
ok(code == 0 and "added 2 of 6 (4 rejected)" in out, f"mixed add ({code}, {out})")
cases = S.load_cases()
ids = sorted(c["id"] for c in cases)
ok(ids == ["2026-10-27-ahh-access-time-gbpaud-1", "2026-10-27-ahh-access-time-gbpjpy-1"], f"ids {ids}")
ok(cases[0]["note"] == "wiki/AHH Session Notes/2026-10-27-ahh-access-time.md", "repo-relative note")
ok(cases[0]["session_type"] == "ahh-access-time" and cases[0]["date"] == "2026-10-27", "derived fields")
ok(all(c["presenter"] == "binni" for c in cases) and S.load_done()["2026-10-27-ahh-access-time"]["presenter"] == "binni",
   "presenter recorded on cases and notes_done")
code_np, _, _ = run(["add", "--note", str(NOTE), "--file", staged([GBPAUD])])
ok(code_np == 2, "missing --presenter -> argparse exit 2")
code_bp, _, _ = run(["add", "--presenter", "bob", "--note", str(NOTE), "--file", staged([GBPAUD])])
ok(code_bp == 2, "unknown presenter -> exit 2")
ok(cases[0]["quote_in_raw"] in (True, False), "raw transcript located for 2026-10-27")
rej = json.loads((TMP / "runs" / "cases_2026-10-27-ahh-access-time.rejects.json").read_text())
reasons = " | ".join(r["reason"] for r in rej)
for frag in ("unknown", "condition required", "asset_class", "does not mention"):
    ok(frag in reasons, f"reject reason {frag}: {reasons}")

rej_before = (TMP / "runs" / "cases_2026-10-27-ahh-access-time.rejects.json").read_text()
code, out, _ = run(["add", "--presenter", "binni", "--note", str(NOTE), "--file", staged([GBPAUD, dict(GBPAUD, tf=["1h"])])])
ok(code == 1, "second add without --replace -> 1")
ok("added" not in out, f"already-done add prints no 'added' line ({out!r})")
ok((TMP / "runs" / "cases_2026-10-27-ahh-access-time.rejects.json").read_text() == rej_before,
   "already-done add leaves the earlier rejects file alone")
for k, v in (("tf", ["1h", "4h"]), ("verdict", {"a": 1}), ("setup", [{"x": 1}]), ("opportunity_no", True),
             ("instrument", ["GBPAUD"]), ("condition", 5)):
    why = S.validate_case(dict(GBPAUD, **{k: v}), note_norm, S.opportunities(NOTE.read_text()))
    ok(isinstance(why, str), f"bad-typed {k} rejected, not crashed ({why})")
why = S.validate_case(dict(GBPAUD, quote="ay the 4H broke the uptrend li"), note_norm, S.opportunities(NOTE.read_text()))
ok(why == "quote not found in note", f"quote cut mid-word rejected ({why})")
for q in ("Downtrend intact", "TP : 1.64055", "wave 3"):
    ok(len(S.quote_tokens(q)) >= 2, f"2-token quote {q!r} passes the length guard")
for q in ("   ", "**", "[[]]", "e", "1.0850", "0.5", "$1,234", "e.g."):
    why = S.validate_case(dict(GBPAUD, quote=q), note_norm, S.opportunities(NOTE.read_text()))
    ok(why and "too short" in why, f"blank/short quote {q!r} rejected ({why})")
code, _, _ = run(["add", "--presenter", "binni", "--note", str(NOTE), "--file", str(TMP / "nope.json")])
ok(code == 2, "unreadable staged -> 2")
code, _, _ = run(["add", "--presenter", "binni", "--note", str(ROOT / "wiki/concepts/tat.md"), "--file", staged([])])
ok(code == 2, "non-session note -> 2")

# --replace hindsight carry-over
cs = S.load_cases()
for c in cs:
    c["hindsight"] = {"status": "favourable", "mfe_atr": 2, "mae_atr": 0.3, "horizon_days": 10,
                      "scored_at": "x", "reason": None}
S.save_cases(cs)
code, _, _ = run(["add", "--presenter", "binni", "--note", str(NOTE), "--replace",
                  "--file", staged([GBPAUD, dict(GBPJPY, verdict="watch", condition=None)])])
cs = {c["id"]: c for c in S.load_cases()}
ok(code == 0 and cs["2026-10-27-ahh-access-time-gbpaud-1"]["hindsight"] is not None, "hindsight kept (same)")
ok(cs["2026-10-27-ahh-access-time-gbpjpy-1"]["hindsight"] is None, "hindsight dropped (verdict changed)")
ok(not (TMP / "runs" / "cases_2026-10-27-ahh-access-time.rejects.json").exists(), "rejects file cleared")

# empty array -> done with 0
empty_note = ROOT / "wiki" / "AHH Session Notes" / "2026-10-28-taw-pro.md"
code, _, _ = run(["add", "--presenter", "binni", "--note", str(empty_note), "--file", staged([])])
ok(code == 0 and S.load_done()["2026-10-28-taw-pro"]["cases"] == 0, "empty array -> done, 0 cases")

# ---------------------------------------------------------------- opportunities sections
t1 = "# x\n## 📈 Trading Opportunities & Key Level Analysis\n1. **[[EURUSD]]** up\n2. **[[NASDAQ]]**\n## Rules\n3. no\n"
o = S.opportunities(t1)
ok(set(o) == {1, 2} and S.instrument_mentioned(o[2], "NDQ100"), "section variant + alias mention")
ok(S.opportunities("## Trading Instruments & Opportunities\n1. [[GBPUSD]]\n") == {1: "1. [[GBPUSD]]"}, "variant 2")
ok(S.opportunities("## Key claims\n1. x\n") is None, "no section")

# ---------------------------------------------------------------- pending regex
for stem, want in (("2026-10-24-3tt-week-of-26-oct", True), ("2026-03-07-weekly-review-binni", True),
                   ("2026-08-13-tar-session", True), ("2026-10-23-tat-v3-user-guide", False)):
    ok(bool(S.note_stem_info(stem + ".md")) is want, f"regex {stem}")
ok(S.note_stem_info("2026-03-07-weekly-review-binni.md")["session_type"] == "weekly-review", "binni type")

# ---------------------------------------------------------------- raw lookup
info = S.note_stem_info(NOTE)
ok(S.find_raw(NOTE, NOTE.read_text(), info).name == "2026-10-27-ahh-access-time.md", "raw AHH")
taw = ROOT / "wiki" / "AHH Session Notes" / "2026-10-21-taw-pro.md"
ok(S.find_raw(taw, taw.read_text(), S.note_stem_info(taw)).name == "2026-10-21-taw-pro.md", "raw TAW same date")
missing = "---\nraw: raw/does-not-exist.md\n---\n"
ok(S.find_raw(NOTE, missing, info).name == "2026-10-27-ahh-access-time.md", "missing raw: falls through")
arch = ROOT / "raw" / "archives"
if any(arch.rglob("2026-10-05-ahh-session*.md")):
    fake = ROOT / "wiki" / "AHH Session Notes" / "2026-10-05-ahh-session.md"
    r = S.find_raw(fake, "", S.note_stem_info(fake))
    ok(r is not None, "archive transcript found")

# ---------------------------------------------------------------- quote_in_raw
raw = S.words("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda")
ok(S.quote_in_raw("alpha beta gamma delta epsilon zeta eta theta iota QQQ", raw), "1 of 10 missing -> true")
ok(not S.quote_in_raw("alpha beta gamma delta epsilon zeta eta XX YY ZZ", raw), "3 of 10 missing -> false")
ok(not S.quote_in_raw("kappa iota theta eta zeta epsilon delta gamma beta alpha", raw), "reversed -> false")

# ---------------------------------------------------------------- yahoo dating
res = {"meta": {"exchangeTimezoneName": "Europe/London", "gmtoffset": 0},
       "timestamp": [int(dt.datetime(2026, 10, 20, 23, tzinfo=dt.timezone.utc).timestamp()),
                     int(dt.datetime(2026, 10, 27, 0, tzinfo=dt.timezone.utc).timestamp())],
       "indicators": {"quote": [{"open": [1, 1], "high": [1, 1], "low": [1, 1], "close": [1, 1]}]}}
bars, err = S.parse_yahoo(res)
ok([b["date"] for b in bars] == ["2026-10-21", "2026-10-27"], f"exchange-tz dating {bars}")

# ---------------------------------------------------------------- score
def mk_bars(start, n, path):
    """path(i) -> (open, high, low, close)"""
    out, d = [], dt.date.fromisoformat(start)
    for i in range(n):
        o, h, l, c = path(i)
        out.append({"date": (d + dt.timedelta(days=i)).isoformat(), "open": o, "high": h, "low": l, "close": c})
    return out

flat = lambda i: (100, 101, 99, 100)  # TR = 2 -> ATR 2
case = {"date": "2026-09-01", "direction": "long"}
pre = mk_bars("2026-08-10", 23, flat)  # through 2026-09-01
def with_after(fn):
    return pre + mk_bars("2026-09-02", 10, fn)
ok(S.score_case(case, with_after(lambda i: (100, 103 if i == 2 else 101, 99, 100)))["status"] == "favourable", "fav")
ok(S.score_case(case, with_after(lambda i: (100, 101, 97 if i == 2 else 99, 100)))["status"] == "adverse", "adv")
ok(S.score_case(case, with_after(flat))["status"] == "flat", "flat")
ok(S.score_case(case, with_after(lambda i: (100, 103, 97, 100) if i == 0 else flat(i)))["status"] == "adverse",
   "same bar both -> adverse")
h = S.score_case(case, with_after(lambda i: (100, 101 + i * 0.1, 99, 100)))
ok(h["mfe_atr"] == round(1.9 / 2, 2), f"mfe over all 10 bars ({h})")
ok(S.score_case(case, mk_bars("2026-08-19", 14, flat) + mk_bars("2026-09-02", 10, flat))["reason"] == "no_bars",
   "14 bars before -> no_bars")
ok(S.score_case(case, pre + mk_bars("2026-09-02", 8, flat)) is None, "8 bars after -> null")

reset_store()
old = {"id": "old-eurusd-1", "note": "n", "date": "2026-09-01", "instrument": "EURUSD", "direction": "long",
       "verdict": "take", "hindsight": None}
nt = {"id": "old-xyz-1", "note": "n", "date": "2026-09-01", "instrument": "XYZ", "direction": "long",
      "verdict": "take", "hindsight": None}
S.save_cases([old, nt])
calls = {"n": 0}
def fail_fetch(*a):
    calls["n"] += 1
    return [], "fetch_failed"
class A: all = False
with contextlib.redirect_stdout(io.StringIO()):
    S.cmd_score(A, fetch=fail_fetch)
cs = {c["id"]: c for c in S.load_cases()}
ok(cs["old-eurusd-1"]["hindsight"]["reason"] == "fetch_failed", "fetch_failed recorded")
ok(cs["old-xyz-1"]["hindsight"]["reason"] == "no_ticker", "no_ticker recorded")
with contextlib.redirect_stdout(io.StringIO()):
    S.cmd_score(A, fetch=fail_fetch)
ok(calls["n"] == 2, "fetch_failed retried, no_ticker not")
good = pre + mk_bars("2026-09-02", 10, lambda i: (100, 103, 99, 100))
with contextlib.redirect_stdout(io.StringIO()):
    S.cmd_score(A, fetch=lambda *a: (good, None))
ok(S.load_cases()[0]["hindsight"]["status"] == "favourable", "scored after retry")
class B: all = True
with contextlib.redirect_stdout(io.StringIO()):
    S.cmd_score(B, fetch=fail_fetch)
ok(S.load_cases()[0]["hindsight"]["status"] == "favourable", "--all failure keeps the real score")
# concurrent replace between fetch and write: result must not land on a changed case
def racing_fetch(*a):
    cs = S.load_cases()
    cs[0]["direction"] = "short"
    S.save_cases(cs)
    return good, None
S.save_cases([dict(old, hindsight=None)])
with contextlib.redirect_stdout(io.StringIO()):
    S.cmd_score(A, fetch=racing_fetch)
ok(S.load_cases()[0]["hindsight"] is None, "changed case not overwritten by a stale result")

# ---------------------------------------------------------------- find_precedents
T = dt.datetime(2026, 10, 30, 10, tzinfo=SGT)
base = {"note": "n", "asset_class": "fx", "tf": "4h", "direction": "long", "verdict": "take", "setup": [],
        "location": [], "structure": "unspecified", "htf": "unspecified", "risk_flags": []}
fx_cases = [
    dict(base, id="a", date="2026-10-20", instrument="GBPUSD"),                                  # recent
    dict(base, id="b", date="2026-10-08", instrument="GBPUSD"),                                  # 22 d -> not recent
    dict(base, id="c", date="2026-10-09", instrument="GBPUSD"),                                  # exactly 21 d -> recent
    dict(base, id="d", date="2026-10-30", instrument="GBPUSD"),                                  # same day -> excluded
    dict(base, id="e", date="2026-10-01", instrument="EURUSD", setup=["tflow"], htf="aligned"),
    dict(base, id="f", date="2026-10-02", instrument="EURUSD"),                                  # only tf/class/ccy
    dict(base, id="g", date="2026-10-03", instrument="AUDCAD", htf="aligned", tf="m"),
    dict(base, id="h", date="2026-10-04", instrument="USDJPY", direction="neutral", htf="aligned"),
]
sig = {"instrument": "GBPUSD", "direction": "long", "time": T,
       "tags": {"tf": "4h", "setup": ["tflow"], "location": [], "structure": "unspecified", "htf": "aligned",
                "risk_flags": []}}
pr = S.find_precedents(sig, fx_cases)
ok([c["id"] for c in pr["instrument_recent"]] == ["a", "c"], f"recent {[c['id'] for c in pr['instrument_recent']]}")
sim_ids = [c["id"] for c in pr["similar"]]
ok(sim_ids[0] == "e" and "f" not in sim_ids and "d" not in sim_ids, f"similar {sim_ids}")
ok("b" not in sim_ids, "b has no substantive match")
sims = {c["id"]: c for c in pr["similar"]}
ok("g" not in sims, "g below 0.45")  # htf only (1.5) + class 1 = 2.5/7.5
ok("h" in sims and sims["h"]["same_direction"] is False, "neutral -> same_direction false")
ok(pr["instrument_recent"][0]["same_direction"] is True, "same_direction true")
sig_us = dict(sig, instrument="NDQ100", tags=dict(sig["tags"], setup=[]))
pr2 = S.find_precedents(sig_us, [dict(base, id="u", date="2026-10-25", instrument="US100", asset_class="index")])
ok([c["id"] for c in pr2["instrument_recent"]] == ["u"], "US100 case recent for NDQ100")
# unspecified components excluded from the max: htf-only signal, htf-matching case
sig_h = dict(sig, tags={"tf": "4h", "setup": [], "location": [], "structure": "unspecified", "htf": "aligned",
                        "risk_flags": []})
s, subst = S.similarity(sig_h["tags"], "fx", ["GBP", "USD"], True,
                        dict(base, instrument="EURUSD", htf="aligned"))
ok(abs(s - 1.0) < 1e-9 and subst == ["htf"], f"max excludes unspecified ({s})")

# ---------------------------------------------------------------- tflow parse
p = S.parse_tflow_event("Tflow Bullish Signal @Zone (Support Zone x5 (M,W), Zone High: 1.95478, Zone Low: 1.94507): "
                        "D Level: 1.96230, LL: 1.95398. Filtered: None.")
ok(p["at_zone"] and p["zone"] == {"role": "Support", "count": 5, "tfs": "M,W", "high": 1.95478, "low": 1.94507}
   and p["d_level"] == 1.96230 and p["pivot_label"] == "LL" and p["pivot"] == 1.95398, f"EURNZD {p}")
p = S.parse_tflow_event("Tflow Bullish Signal @Zone (Support Zone x1 (W), Zone High: 0.46350, Zone Low: 0.46290): "
                        "D Level: 0.46873, LL: 0.46328. Filtered: None.")
ok(p["zone"]["count"] == 1 and p["zone"]["tfs"] == "W", "NZDCHF")
p = S.parse_tflow_event("Tflow Bullish Signal: D Level: 0.58238, LL: 0.57036. Filtered: None.")
ok(p["at_zone"] is False and p["zone"] is None and p["pivot"] == 0.57036, "AUDCHF")
p = S.parse_tflow_event("Tflow Bearish Signal: D Level: 64316.07, HH: 64576.07. Filtered: None.")
ok(p["direction"] == "Bearish" and p["pivot_label"] == "HH", "JPN225")
ok("parse_error" in S.parse_tflow_event("Tflow Bullish Signal broken text"), "malformed")

# ---------------------------------------------------------------- load_alerts
row = lambda sym, sig, t, d="2026-10-31", direc="Bearish", ev="": {
    "Date": d, "Time": t, "Symbol": sym, "Direction": direc, "Signal Type": sig, "Event": ev}
since = dt.datetime(2026, 10, 1, tzinfo=SGT)
al, sk = S.load_alerts({"4H": [row("EIGHTCAP:US30", "OptBear", "2:00:06"), row("EIGHTCAP:US30", "LBear", "2:00:04"),
                               row("EIGHTCAP:XAUUSD", "Tflow SBull", "02:01:03", direc="Bullish",
                                   ev="Tflow Bullish Signal: D Level: 1, LL: 0.9. Filtered: None."),
                               row("EIGHTCAP:XAUUSD", "SBull", "2:01:02", direc="Bullish"),
                               {"Date": "", "Time": "", "Symbol": "X", "Direction": "", "Signal Type": ""}]}, since)
by = {a["symbol"]: a for a in al}
ok(len(al) == 2 and by["US30"]["signal"] == "OptBear" and by["US30"]["also_fired"] == ["LBear"], f"US30 {al}")
ok(by["XAUUSD"]["signal"] == "Tflow SBull" and by["XAUUSD"]["tflow"]["pivot"] == 0.9, "XAUUSD Tflow kept")
ok(sk == 1, "blank row skipped")

# ---------------------------------------------------------------- coverage tags
bdir = TMP / "brief"
bdir.mkdir()
bp = bdir / "2026-10-29.json"
bp.write_text(json.dumps([{"symbol": "TVC:DXY", "bias": "bullish"}, {"symbol": "EIGHTCAP:GBPAUD", "bias": "bearish"}]))
os.utime(bp, (dt.datetime(2026, 10, 29, 5, 6, tzinfo=SGT).timestamp(),) * 2)
brief = S.brief_bias_lookup(bdir)
ok(brief("GBPAUD", dt.datetime(2026, 10, 29, 5, tzinfo=SGT)) is None, "brief D not usable at 05:00 D")
ok(brief("GBPAUD", dt.datetime(2026, 10, 29, 7, tzinfo=SGT)) == "bearish", "brief D usable at 07:00 D")
ok(brief("EIGHTCAP:USDX", dt.datetime(2026, 10, 29, 7, tzinfo=SGT)) == "bullish", "TVC:DXY matches USDX")
late = bdir / "2026-10-30.json"
late.write_text(json.dumps([{"symbol": "GBPAUD", "bias": "bullish"}]))
os.utime(late, (dt.datetime(2026, 10, 30, 8, 18, tzinfo=SGT).timestamp(),) * 2)
ok(brief.__call__ and S.brief_bias_lookup(bdir)("GBPAUD", dt.datetime(2026, 10, 30, 7, tzinfo=SGT)) == "bearish",
   "late file (08:18) not used at 07:00")

cal = ([(dt.datetime(2026, 11, 1, tzinfo=SGT), dt.datetime(2026, 11, 7, 23, 59, tzinfo=SGT))],
       [{"when": dt.datetime(2026, 11, 3, 11, 30, tzinfo=SGT), "ccy": "AUD", "event": "Cash Rate"}])

def mkal(sym, tf, d, close, sig="LBear"):
    return {"key": "k", "symbol": sym, "tv_symbol": sym, "class": S.instrument_class(sym), "tf": tf,
            "direction": d, "signal": sig, "also_fired": [], "event": "", "tflow": None,
            "nominal_close": close, "alert_time": close}

c0 = dt.datetime(2026, 11, 2, 18, tzinfo=SGT)
a_eur = mkal("EURAUD", "4H", "short", c0 - dt.timedelta(hours=8))
a_gbp = mkal("GBPAUD", "4H", "short", c0)
idx = lambda als: {"4H": {"alerts": als, "closes": sorted({a["nominal_close"] for a in als})},
                   "1H": {"alerts": [], "closes": []}}
tg = S.alert_tags(a_gbp, idx([a_eur, a_gbp]), None, cal)
ok("laggard" in tg["setup"], "laggard with EURAUD 2 closes earlier")
ok("news_pending" in tg["risk_flags"], "news_pending inside calendar week")
far = [mkal("EURAUD", "4H", "short", c0 - dt.timedelta(hours=4 * k)) for k in (4,)] + \
      [mkal("USDJPY", "4H", "long", c0 - dt.timedelta(hours=4 * k)) for k in (1, 2, 3)] + [a_gbp]
ok("laggard" not in S.alert_tags(a_gbp, idx(far), None, cal)["setup"], "EURAUD 4 closes earlier -> no laggard")
old_al = mkal("GBPAUD", "4H", "short", dt.datetime(2026, 10, 20, 10, tzinfo=SGT))
ok("news_pending" not in S.alert_tags(old_al, idx([old_al]), None, cal)["risk_flags"], "outside calendar weeks")
sat = mkal("GBPAUD", "4H", "short", dt.datetime(2026, 10, 31, 2, tzinfo=SGT))   # Fri 14:00 NY (EDT)
fri = mkal("GBPAUD", "4H", "short", dt.datetime(2026, 10, 30, 13, tzinfo=SGT))  # Fri 01:00 NY
thu = mkal("GBPAUD", "4H", "short", dt.datetime(2026, 10, 30, 12, tzinfo=SGT))  # Fri 00:00 NY
for a, want in ((sat, True), (fri, True), (thu, False)):
    ok(("friday" in S.alert_tags(a, idx([a]), None, ([], []))["risk_flags"]) is want, f"friday {a['nominal_close']}")

# ---------------------------------------------------------------- coverage end to end (gate)
now = dt.datetime(2026, 11, 2, 20, tzinfo=SGT)
rows = {"4H": [row("EIGHTCAP:GBPUSD", "Tflow LBull", "10:00:05", d="2026-11-01", direc="Bullish",
                   ev="Tflow Bullish Signal @Zone (Support Zone x2 (W,M), Zone High: 1.3, Zone Low: 1.29): "
                      "D Level: 1.31, LL: 1.295. Filtered: None."),
               row("EIGHTCAP:AUDCAD", "OptBear", "14:00:03", d="2026-11-01"),
               row("EIGHTCAP:NDQ100", "LBull", "18:00:02", d="2026-11-01", direc="Bullish")],
        "1H": [row("EIGHTCAP:EURUSD", "SBull", "9:00:11", d="2026-11-02", direc="Bullish")]}
store = [dict(base, id="r1", date="2026-10-28", instrument="GBPUSD"),
         dict(base, id="s1", date="2026-10-20", instrument="EURJPY", setup=["tflow"], location=["at_d_zone"]),
         dict(base, id="s2", date="2026-10-21", instrument="GBPCAD", setup=["tflow", "pullback_in_trend"]),
         dict(base, id="s3", date="2026-10-22", instrument="AUDNZD", direction="short", htf="aligned"),
         dict(base, id="s4", date="2026-10-23", instrument="EURCHF", direction="short", htf="aligned")]
fake_brief = lambda sym, when: {"AUDCAD": "bearish"}.get(sym)
rep = S.run_coverage(rows, {"1H": "ok", "4H": "ok"}, False, store, 14, now, fake_brief, ([], []))
ok(rep["alerts"]["total"] == 4, f"alerts {rep['alerts']}")
# GBPUSD: recent r1 + similar s1,s2 -> either; AUDCAD: similar s3,s4 on htf only -> similar_ge2, only-htf;
# NDQ100: nothing; EURUSD: nothing
ok(rep["rates"]["instrument_recent_ge1"] == 25.0, f"recent rate {rep['rates']}")
ok(rep["rates"]["similar_ge2"] == 50.0, f"similar rate {rep['rates']}")
ok(rep["rates"]["either"] == 50.0 and rep["gate"]["value"] == 50.0, "gate")
ok(rep["similar_only_htf"] == 1, f"only-htf {rep['similar_only_htf']}")
ok(rep["top_cases"][0]["id"] in ("s1", "s2", "s3", "s4", "r1"), "top cases")
ok(rep["rates_by_tab"]["1H"]["either"] == 0.0 and rep["rates_by_class"]["index"]["either"] == 0.0, "splits")
ok(rep["alerts_range"]["first"].startswith("2026-11-01T10:00"), "alerts_range from deduped alerts")

# ---------------------------------------------------------------- fetch failure
import scripts.fetch_google_sheet as FG  # noqa: E402
orig = FG.fetch_with_service_account
FG.fetch_with_service_account = lambda key: None if key == "H1" else [row("EIGHTCAP:GBPUSD", "LBull", "10:00", d="2026-11-02", direc="Bullish")]
rows2, st, _ = S.fetch_tabs()
ok(st == {"1H": "failed", "4H": "ok"}, f"None tab failed {st}")
FG.fetch_with_service_account = lambda key: None
code, _, _ = run(["coverage"])
ok(code == 3, "both failed -> 3")
FG.fetch_with_service_account = orig

print(f"OK — {passed} checks passed (temp dir {TMP})")
