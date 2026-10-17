"""Equity news for the Desk homepage, from moomoo's public news search (no OpenD needed).

One query per entry in scripts/equity_watchlist.json (its `news_keyword`), filtered down to headlines that are
actually about that company, merged newest-first. Read-only: nothing is written to wiki/ or raw/. The last good
result is kept in memory and in cache/news.json, so a stale copy is served instantly while a refresh runs in the
background, and the tab still loads when moomoo is unreachable.
"""
import datetime as dt
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import wiki_data as W

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "cache" / "news.json"
WATCHLIST = W.ROOT / "scripts" / "equity_watchlist.json"
ENDPOINT = "https://ai-news-search.moomoo.com/news_search"
UA = "moomoo-news-search/0.0.2 (Skill)"
TTL = 1800
PER_QUERY = 20
PER_SYMBOL = 6
MAX_AGE_DAYS = 30
SGT = dt.timezone(dt.timedelta(hours=8))

# market-wide feed: (label, moomoo keyword). Searched the same way as the watchlist, newest first.
MARKET_TOPICS = [
    ("US stocks", "Wall Street"), ("US stocks", "US stocks close"), ("Fed", "Federal Reserve"), ("Rates", "Treasury yields"),
    ("FX", "forex market"), ("FX", "dollar yen"), ("Gold", "gold price"), ("Oil", "crude oil prices"),
    ("Crypto", "Bitcoin price"), ("Asia", "Asian markets"), ("Asia", "Hang Seng Index"), ("SG", "Singapore stocks"),
    ("SG", "Straits Times Index"), ("Macro", "Market Talk"),
]
MARKET_MAX = 60
# earnings-calendar boilerplate, single-stock broker rating blurbs and preferred-share notices aren't market news
_MARKET_NOISE = re.compile(r"Preferred|will release its e|Ex-Dividend|Inducement|Listing|Compliance|Earnings Preview|Delisting|Price Target|Target Price|\bRating\b|Receives an? (?:Buy|Sell|Hold)|"
                           r"Gets an? (?:Buy|Sell|Hold)|Sticks to|Reaffirms|Earnings Summary|Starts? .{0,40} at (?:Buy|Hold|Sell)",
                           re.I)

# a headline whose subject is a broker/analyst naming the company only as the author of the call
# ("DBS Upgrades Mixue ..."), or credits it as research house ("... by DBS Group Research")
_BROKER_VERBS = r"(?:upgrades|downgrades|maintains|reaffirms|sticks|starts|initiates|keeps|raises|cuts|lowers|" \
                r"adjusts|resumes|reiterates|lifts|trims|boosts|hikes|rates|puts)"

_lock = threading.Lock()
_state = {"data": None, "at": 0.0, "loading": False, "error": None}


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _entries():
    try:
        return json.loads(WATCHLIST.read_text())
    except (OSError, ValueError):
        return []


def _relevant(entry, title):
    kw = entry.get("news_keyword") or entry.get("name") or ""
    if not kw or _norm(kw) not in _norm(title):
        return False
    ex = entry.get("news_exclude")
    if ex and re.search(ex, title, re.I):
        return False
    esc = re.escape(kw)
    if re.match(rf"\s*{esc}\s+{_BROKER_VERBS}\b", title, re.I):
        return False
    if re.search(rf"\bby\s+{esc}(?:\s+\w+)?\s+Research\b|\bby\s+{esc}\b", title, re.I):
        return False
    return True


def _fetch_one(entry):
    kw = entry.get("news_keyword") or entry.get("name")
    if not kw:
        return []
    q = urllib.parse.urlencode({"keyword": kw, "size": PER_QUERY, "news_type": 1, "lang": "en", "sort_type": 2})
    req = urllib.request.Request(f"{ENDPOINT}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.load(r)
    if j.get("code") != 0:
        raise RuntimeError(j.get("message") or "moomoo news error")
    out = []
    for it in j.get("data") or []:
        title = re.sub(r"</?em>", "", it.get("title") or "").strip()
        if not title or not _relevant(entry, title):
            continue
        t = int(it.get("publish_time") or 0)
        t = t / 1000 if t > 1e11 else t
        out.append({"id": str(it.get("news_id") or it.get("url")), "title": title, "url": it.get("url"),
                    "ts": int(t), "sym": entry["symbol"], "name": entry.get("name") or kw})
    return out


def _fetch_topic(label, kw):
    q = urllib.parse.urlencode({"keyword": kw, "size": PER_QUERY, "news_type": 1, "lang": "en", "sort_type": 2})
    req = urllib.request.Request(f"{ENDPOINT}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.load(r)
    if j.get("code") != 0:
        raise RuntimeError(j.get("message") or "moomoo news error")
    out = []
    for it in j.get("data") or []:
        title = re.sub(r"</?em>", "", it.get("title") or "").strip()
        if not title or _MARKET_NOISE.search(title):
            continue
        t = int(it.get("publish_time") or 0)
        t = t / 1000 if t > 1e11 else t
        out.append({"id": str(it.get("news_id") or it.get("url")), "title": title, "url": it.get("url"),
                    "ts": int(t), "topic": label})
    return out


def _build_market():
    merged, failed = {}, 0

    def run(t):
        for attempt in range(3):
            try:
                return _fetch_topic(*t)
            except Exception:
                time.sleep(1 + attempt)
        return None

    with ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(run, MARKET_TOPICS))
    for res in results:
        if res is None:
            failed += 1
            continue
        for it in res:
            m = merged.setdefault(it["id"], {**it, "topics": []})
            if it["topic"] not in m["topics"]:
                m["topics"].append(it["topic"])
    cutoff = time.time() - 7 * 86400
    items = sorted((m for m in merged.values() if m["ts"] >= cutoff), key=lambda x: -x["ts"])[:MARKET_MAX]
    for it in items:
        it.pop("topic", None)
        it["time"] = dt.datetime.fromtimestamp(it["ts"], SGT).strftime("%Y-%m-%d %H:%M")
        it["source"] = (urlparse(it["url"] or "").netloc or "").removeprefix("www.")
    if failed == len(MARKET_TOPICS):
        raise RuntimeError("moomoo news unreachable")
    return items


def _build():
    entries = _entries()
    failed = []

    def run(e):
        for attempt in range(3):
            try:
                return _fetch_one(e)
            except Exception:
                time.sleep(1 + attempt)  # moomoo throttles bursts
        failed.append(e["symbol"])
        return []

    with ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(run, entries))
    merged = {}
    for items in results:
        for it in items:
            m = merged.setdefault(it["id"], {**it, "syms": []})
            if it["sym"] not in m["syms"]:
                m["syms"].append(it["sym"])
    cutoff = time.time() - MAX_AGE_DAYS * 86400
    items = sorted((m for m in merged.values() if m["ts"] >= cutoff), key=lambda x: -x["ts"])
    seen, kept = {}, []  # one chatty name (SK Hynix) shouldn't crowd the rest out
    for it in items:
        if all(seen.get(s, 0) >= PER_SYMBOL for s in it["syms"]):
            continue
        for s in it["syms"]:
            seen[s] = seen.get(s, 0) + 1
        kept.append(it)
    items = kept
    for it in items:
        it.pop("sym", None)
        it["time"] = dt.datetime.fromtimestamp(it["ts"], SGT).strftime("%Y-%m-%d %H:%M")
        it["source"] = (urlparse(it["url"] or "").netloc or "").removeprefix("www.")
    if not items and failed and len(failed) == len(entries):
        raise RuntimeError("moomoo news unreachable")
    return {"fetchedAt": dt.datetime.now(SGT).isoformat(timespec="seconds"), "failed": failed, "market": _build_market(),
            "names": {e["symbol"]: e.get("name") or e["symbol"] for e in entries}, "items": items}


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
    except Exception as e:  # keep serving the last good copy
        with _lock:
            _state["error"] = str(e)
    finally:
        with _lock:
            _state["loading"] = False


def news(refresh=False):
    with _lock:
        if _state["data"] is None and SNAPSHOT.exists():
            try:
                _state["data"] = json.loads(SNAPSHOT.read_text())
                _state["at"] = SNAPSHOT.stat().st_mtime
            except (OSError, ValueError):
                pass
        stale = refresh or time.time() - _state["at"] > TTL
        start = stale and not _state["loading"]
        if start:
            _state["loading"] = True
        have = _state["data"] is not None
    if start:
        if have and not refresh:
            threading.Thread(target=_refresh, daemon=True).start()
        else:
            _refresh()  # first load, or a manual refresh: wait for it
    with _lock:
        d = _state["data"] or {"items": [], "names": {}, "failed": [], "fetchedAt": None}
        return {**d, "error": _state["error"], "loading": _state["loading"]}
