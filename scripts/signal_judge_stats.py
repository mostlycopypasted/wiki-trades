#!/usr/bin/env python3
"""Signal Judge scorecard — the one definition used by the report, `signal_judge.py stats` and the
dashboard's /api/judge (docs/design/signal-judge.md §8). Stdlib only: the dashboard imports it.

Groups: take / wait_retest / skip, each split by basis (precedent = followed a Binni/Pauline call,
own = the judge's own analysis), plus no_ruling, unjudged (cap + error) and filtered (RR_LT_1).
Only tracked entries count; pending entries and every untracked outcome are excluded.
"""

import datetime as dt

RESOLVED = {"TP1_HIT", "SL_HIT", "EXPIRED", "OPEN_RUN_EXPIRED"}
GROUPS = ["take (precedent)", "take (own)", "wait_retest (precedent)", "wait_retest (own)",
          "skip (precedent)", "skip (own)", "no_ruling", "unjudged", "filtered"]


def group_of(e):
    v = e.get("verdict")
    basis = ((e.get("judge") or {}).get("basis")) or "own_analysis"
    tag = "precedent" if basis == "precedent" else "own"
    if v in ("take", "wait_retest", "skip"):
        return f"{v} ({tag})"
    if v == "no_ruling":
        return "no_ruling"
    if v in ("unjudged_cap", "unjudged_error"):
        return "unjudged"
    if v is None and e.get("prefilter") == "RR_LT_1":
        return "filtered"
    return None


def _since(e, since):
    t = e.get("alert_time")
    if not t:
        return False
    return dt.datetime.fromisoformat(t) >= since


def scorecard(entries, since):
    """-> {"window_days", "rows": {group: {"n", "resolved", "tp1_pct", "avg_r", "avg_mfe_r", "no_fill"}}}"""
    now = dt.datetime.now(since.tzinfo)
    rows = {g: {"n": 0, "resolved": 0, "tp1_pct": None, "avg_r": None, "avg_mfe_r": None, "no_fill": 0} for g in GROUPS}
    acc = {g: {"r": [], "mfe": [], "tp": 0} for g in GROUPS}
    for e in entries:
        if not e.get("tracked") or not _since(e, since):
            continue
        g = group_of(e)
        if g is None:
            continue
        o = e.get("outcome") or {}
        st = o.get("status")
        rows[g]["n"] += 1
        if st == "NO_FILL":
            rows[g]["no_fill"] += 1
        if st in RESOLVED:
            rows[g]["resolved"] += 1
            acc[g]["tp"] += st == "TP1_HIT"
            if o.get("r") is not None:
                acc[g]["r"].append(o["r"])
            if o.get("mfe_r") is not None:
                acc[g]["mfe"].append(o["mfe_r"])
    for g, r in rows.items():
        if r["resolved"]:
            r["tp1_pct"] = round(100.0 * acc[g]["tp"] / r["resolved"])
            r["avg_r"] = round(sum(acc[g]["r"]) / len(acc[g]["r"]), 2) if acc[g]["r"] else None
            r["avg_mfe_r"] = round(sum(acc[g]["mfe"]) / len(acc[g]["mfe"]), 2) if acc[g]["mfe"] else None
    return {"window_days": max(0, (now - since).days), "rows": rows}


def precedent_hit_rate(entries, since):
    judged = [e for e in entries if e.get("verdict") in ("take", "wait_retest", "skip", "no_ruling") and _since(e, since)]
    n = len(judged)
    pct = lambda k: round(100.0 * k / n, 1) if n else None
    return {"judged": n, "with_precedents_pct": pct(sum(1 for e in judged if e.get("has_precedents"))),
            "followed_pct": pct(sum(1 for e in judged if (e.get("judge") or {}).get("basis") == "precedent"))}
