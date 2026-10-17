"""Fed funds rate odds for the Calendar view, from moomoo's FedWatch endpoint (needs OpenD running).

Runs the moomoo skill's `get_fed_watch_target_rate.py` and reshapes its per-meeting target-range
probabilities into hike / hold / cut odds against the *current* target range. The endpoint doesn't say what
the current range is, so it is read from the Fed row of wiki/notes/central-bank-tally.md ("... to 3.75–4.00%");
if that can't be parsed, the first meeting's most likely range stands in. Read-only: nothing is written to
wiki/ or raw/. The last good result is kept in memory and cache/fedwatch.json so the card still renders when
OpenD is closed.
"""
import datetime as dt
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import wiki_data as W

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "cache" / "fedwatch.json"
SCRIPT = Path.home() / ".claude" / "skills" / "moomooapi" / "scripts" / "quote" / "get_fed_watch_target_rate.py"
TTL = 900
SGT = dt.timezone(dt.timedelta(hours=8))

_lock = threading.Lock()
_state = {"data": None, "at": 0.0, "loading": False, "error": None}


def _low(rng):
    return float(rng.split("-")[0])


def _current_range():
    try:
        for s in W.parse_cb_tally()["stances"]:
            if s["bank"].strip().lower() == "fed":
                m = re.search(r"(\d\.\d{2})\s*[–-]\s*(\d\.\d{2})%", s["trigger"])
                if m:
                    return f"{m.group(1)}-{m.group(2)}%"
    except Exception:
        pass
    return None


def _build():
    p = subprocess.run([sys.executable, str(SCRIPT), "--json"], capture_output=True, text=True, timeout=90,
                       stdin=subprocess.DEVNULL)
    out = p.stdout
    i = out.find("{")  # the SDK logs a connect line to stdout before the JSON
    if p.returncode or i < 0:
        raise RuntimeError((p.stderr.strip().splitlines() or ["FedWatch fetch failed"])[-1][:200])
    records = json.JSONDecoder().raw_decode(out[i:])[0].get("records") or []
    if not records:
        raise RuntimeError("FedWatch returned no records")
    by = {}
    for r in records:
        by.setdefault(r["meeting_date"], []).append({"range": r["target_range"], "p": float(r["probability"])})
    dates = sorted(by)
    base = _current_range()
    inferred = base is None
    if inferred:
        base = max(by[dates[0]], key=lambda x: x["p"])["range"]
    b = _low(base)
    meetings = []
    for d in dates:
        rs = sorted(by[d], key=lambda x: _low(x["range"]))
        tot = sum(x["p"] for x in rs) or 1.0
        hike = sum(x["p"] for x in rs if _low(x["range"]) > b + 1e-9) / tot * 100
        cut = sum(x["p"] for x in rs if _low(x["range"]) < b - 1e-9) / tot * 100
        move = sum((_low(x["range"]) - b) * 100 * x["p"] for x in rs) / tot
        top = max(rs, key=lambda x: x["p"])
        meetings.append({"date": d, "hike": round(hike, 1), "hold": round(100 - hike - cut, 1), "cut": round(cut, 1),
                         "move_bp": round(move), "top": top["range"], "top_p": top["p"], "ranges": rs})
    return {"fetchedAt": dt.datetime.now(SGT).isoformat(timespec="seconds"), "base": base,
            "baseInferred": inferred, "meetings": meetings}


def _refresh():
    try:
        data = _build()
        with _lock:
            _state.update(data=data, at=time.time(), error=None)
        try:
            SNAPSHOT.parent.mkdir(exist_ok=True)
            SNAPSHOT.write_text(json.dumps(data))
        except OSError:
            pass
    except Exception as e:
        with _lock:
            _state["error"] = str(e)
    finally:
        with _lock:
            _state["loading"] = False


def fedwatch(refresh=False):
    with _lock:
        if _state["data"] is None and SNAPSHOT.exists():
            try:
                _state["data"] = json.loads(SNAPSHOT.read_text())
                _state["at"] = SNAPSHOT.stat().st_mtime
            except (OSError, ValueError):
                pass
        start = (refresh or time.time() - _state["at"] > TTL) and not _state["loading"]
        if start:
            _state["loading"] = True
        have = _state["data"] is not None
    if start:
        if have and not refresh:
            threading.Thread(target=_refresh, daemon=True).start()
        else:
            _refresh()
    with _lock:
        d = _state["data"] or {"meetings": [], "base": None, "fetchedAt": None}
        return {**d, "error": _state["error"]}
