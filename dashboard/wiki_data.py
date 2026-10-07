"""Data layer for the Trading Desk dashboard.

Reads the LLM-maintained wiki (daily briefs, TAT alert reports, Daily Signals,
AHH Session Notes, economic calendar, central bank tally, market sentiment) and
the live TAT alert Google Sheet, and turns them into plain JSON-able dicts.

Every parser is read-only and tolerant: a section that is missing or formatted
differently yields an empty value rather than an exception, because the wiki's
report formats have drifted over time.
"""
import os
import re
import sys
import threading
import time
import datetime as dt
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
IMAGES = WIKI / "images"
BRIEF_DIR = WIKI / "reports" / "daily_brief"
TAT_DIR = WIKI / "reports" / "tat_analysis"
DSIG_DIR = WIKI / "reports" / "daily-signals"
SENT_DIR = WIKI / "reports" / "market-sentiment"
AHH_DIR = WIKI / "AHH Session Notes"
SOURCES_DIR = WIKI / "sources"
CAL_FILE = WIKI / "notes" / "economic-calendar.md"
CB_FILE = WIKI / "notes" / "central-bank-tally.md"
CS_FILE = WIKI / "notes" / "currency-strength.md"

SGT = dt.timezone(dt.timedelta(hours=8))

MAJORS = ["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"]
FX_CCY = set(MAJORS + ["SGD", "CNH", "HKD", "NOK", "SEK", "MXN", "ZAR", "TRY", "PLN", "CNY"])
METALS = {"XAU", "XAG", "XPT", "XPD", "XCU"}
ENERGY = {"USOUSD", "UKOUSD", "NATGAS", "XNGUSD", "WTI", "BRENT"}
CRYPTO = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "NEAR", "LTC", "BNB", "AVAX", "DOT", "LINK", "TRX", "SHIB"}
INDICES = {"DXY", "NDQ100", "SPX500", "US30", "US2000", "GER40", "UK100", "FRA40", "EU50", "JPN225", "JP225",
           "ASX200", "HK50", "HSI", "HSTECH", "CN50", "STI", "SGP", "SPX", "NASDAQ", "NAS100", "ESP35", "AUS200"}


def now_sgt():
    return dt.datetime.now(SGT)


def read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------- helpers

def asset_class(sym):
    s = sym.upper()
    if s in INDICES:
        return "Index"
    if s in ENERGY:
        return "Energy"
    if s[:3] in METALS:
        return "Metal"
    if s.endswith("USD") and s[:-3] in CRYPTO:
        return "Crypto"
    if len(s) == 6 and s[:3] in FX_CCY and s[3:] in FX_CCY:
        return "Forex"
    return "Stock"


def pair_currencies(sym):
    s = sym.upper()
    if asset_class(s) == "Forex":
        return [s[:3], s[3:]]
    if asset_class(s) == "Metal":
        return [s[3:]] if len(s) == 6 else []
    if s == "DXY":
        return ["USD"]
    return []


def direction_of(text):
    """Classify free text as bull / bear / neutral by the first directional keyword."""
    t = (text or "").lower()
    m = re.search(r"\b(long|bull\w*|buy\w*|uptrend|short|bear\w*|sell\w*|downtrend)", t)
    if not m:
        return "neutral"
    w = m.group(1)
    if w.startswith(("long", "bull", "buy", "up")):
        return "bull"
    return "bear"


def signal_direction(sig):
    s = (sig or "").lower()
    if "bull" in s:
        return "bull"
    if "bear" in s:
        return "bear"
    return "neutral"


# Spoken / legacy names used in session notes -> the symbol the alert sheet and watchlist use.
ALIASES = {"JP225": "JPN225", "NIKKEI": "JPN225", "NASDAQ": "NDQ100", "NAS100": "NDQ100", "US100": "NDQ100",
           "SPX": "SPX500", "US500": "SPX500", "SP500": "SPX500", "USOIL": "USOUSD", "WTI": "USOUSD",
           "UKOIL": "UKOUSD", "BRENT": "UKOUSD", "GOLD": "XAUUSD", "SILVER": "XAGUSD", "DOW": "US30",
           "DJI": "US30", "DAX": "GER40", "GER30": "GER40", "USDX": "DXY", "SGP": "STI"}


def canon_symbol(sym):
    s = sym.strip().upper()
    if s.endswith(".SI"):
        s = s[:-3]
    elif s.endswith(".HK"):
        s = s[:-3].lstrip("0") or "0"
    return ALIASES.get(s, s)


def wikilinks(text):
    """Instrument symbols referenced as [[SYM]] or [SYM](../entities/sym.md)."""
    seen, out = set(), []
    pat = r"\[\[([^\]#|]+?)(?:\|[^\]]*)?\]\]|\[([^\]]+)\]\([^)]*entities/[^)]*\)"
    for m in re.finditer(pat, text or ""):
        s = canon_symbol(m.group(1) or m.group(2))
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def clean_inline(text):
    """Strip markdown emphasis / wikilink brackets for plain-text display."""
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text or "")
    t = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), t)
    t = t.replace("**", "").replace("`", "")
    t = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"\1", t)
    return t.strip()


def split_sections(md, level=2):
    """Return [(heading, body)] for headings of exactly `level` hashes."""
    pat = re.compile(r"^%s (.+)$" % ("#" * level), re.M)
    marks = list(pat.finditer(md))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(md)
        out.append((m.group(1).strip(), md[m.end():end]))
    return out


def find_section(md, needle, level=2):
    for h, body in split_sections(md, level):
        if needle.lower() in h.lower():
            return body
    return ""


def parse_tables(md):
    """Parse every GFM pipe table in md -> list of (header, rows[dict])."""
    tables, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|\s*:?-{3}", lines[i + 1].strip()):
            header = [c.strip() for c in ln.strip("|").split("|")]
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                if len(cells) > len(header):  # a stray pipe inside the last cell
                    cells = cells[:len(header) - 1] + [" | ".join(cells[len(header) - 1:])]
                cells += [""] * (len(header) - len(cells))
                rows.append(dict(zip(header, cells)))
                j += 1
            tables.append((header, rows))
            i = j
        else:
            i += 1
    return tables


def table_with(md, first_col):
    for header, rows in parse_tables(md):
        if header and header[0].lower().startswith(first_col.lower()):
            return rows
    return []


def strip_toc(md):
    return re.sub(r"<!-- TOC:START -->.*?<!-- TOC:END -->", "", md, flags=re.S)


def strip_frontmatter(md):
    return re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)


# ---------------------------------------------------------------- image index

_img_cache = {"mtime": None, "by_sym": {}}
IMG_RE = re.compile(r"^(\d{6})-(\d{6})_(.+?)_(1h|4h|d|w|15m|m15)_chart\.png$", re.I)


def image_index():
    try:
        mtime = IMAGES.stat().st_mtime
    except OSError:
        return {}
    if _img_cache["mtime"] == mtime:
        return _img_cache["by_sym"]
    by_sym = {}
    for name in os.listdir(IMAGES):
        m = IMG_RE.match(name)
        if not m:
            continue
        ymd, hms, sym, tf = m.groups()
        stamp = "20%s-%s-%s %s:%s" % (ymd[:2], ymd[2:4], ymd[4:], hms[:2], hms[2:4])
        by_sym.setdefault(sym.upper(), []).append({"file": name, "tf": tf.upper(), "at": stamp})
    for v in by_sym.values():
        v.sort(key=lambda x: x["at"], reverse=True)
    _img_cache.update(mtime=mtime, by_sym=by_sym)
    return by_sym


# ---------------------------------------------------------------- daily brief

def list_briefs():
    return sorted((p.stem for p in BRIEF_DIR.glob("20??-??-??.md")), reverse=True)


def _brief_scores(md):
    rows = table_with(find_section(md, "Currency Strength"), "Currency")
    out = []
    for r in rows:
        ccy = clean_inline(r.get("Currency", ""))
        try:
            score = int(r.get("Score", "").replace("+", ""))
        except ValueError:
            continue
        out.append({"ccy": ccy, "score": score, "bias": r.get("Trend Bias", "")})
    return out


def _suggested_pairs(md):
    body = find_section(md, "Suggested Pairs")
    out = []
    for line in body.splitlines():
        kind = "bull" if "Buys" in line else "bear" if "Sells" in line else None
        if not kind:
            continue
        for m in re.finditer(r"\[\[(\w+)\]\]\s*\(Score Diff:\s*([+-]?\d+)\)", line):
            out.append({"sym": m.group(1).upper(), "dir": kind, "diff": int(m.group(2))})
    return out


def _drhr(md):
    body = find_section(md, "D-R-H-R")
    out, cur, side = [], None, None
    for line in body.splitlines():
        if "LONG SETUPS" in line:
            side = "bull"
        elif "SHORT SETUPS" in line:
            side = "bear"
        m = re.match(r"\s*•\s*\[\[(\w+)\]\]\s*\|\s*(.+)", line)
        if m and side:
            cur = {"sym": m.group(1).upper(), "dir": side, "label": m.group(2).strip(), "detail": []}
            out.append(cur)
        elif cur and line.strip().startswith("- "):
            cur["detail"].append(clean_inline(line.strip()[2:]))
    return out


def _watchlist(md):
    body = find_section(md, "Watchlist Charts")
    out = []
    for h, sec in split_sections(body, 3):
        m = re.search(r"\[\[(\w+)\]\]\s*\((.*?)\)\s*·\s*Signal\s*`?([^`·]*)`?\s*·\s*Structure\s*(\w+)\s*·\s*TAT Bias\s*(\w+)\s*·\s*Price\s*`?([^`\s]*)`?", sec)
        if not m:
            continue
        img = re.search(r"!\[[^\]]*\]\(([^)]+)\)", sec)
        out.append({
            "sym": m.group(1).upper(), "dir": direction_of(m.group(2)) if "neutral" not in m.group(2).lower() else "neutral",
            "signal": m.group(3).strip().strip("—").strip(), "structure": m.group(4), "bias": m.group(5),
            "price": m.group(6), "img": os.path.basename(img.group(1)) if img else None,
            "cls": asset_class(m.group(1)),
        })
    return out


def _brief_overview(md):
    body = find_section(md, "Executive Overview")
    items = []
    for line in body.splitlines():
        m = re.match(r"-\s*\*\*(.+?)\*\*:\s*(.+)", line.strip())
        if m:
            items.append({"k": m.group(1), "v": m.group(2)})
    return items


def _synthesis(md):
    body = find_section(md, "TAT Alert Synthesis")
    return parse_setup_bullets(body)


def parse_brief(date):
    path = BRIEF_DIR / ("%s.md" % date)
    md = read(path)
    if not md:
        return None
    title = (re.search(r"^# (.+)$", md, re.M) or [None, date])[1]
    events = table_with(find_section(md, "Economic Events"), "Time")
    evs = [{"date": date, "time": r.get("Time (SGT)", "").strip(), "ccy": r.get("Currency", "").strip(),
            "event": r.get("Event", "").strip(), "actual": "" if r.get("Actual", "").strip() in ("—", "-") else r.get("Actual", "").strip()}
           for r in events]
    fill_actuals(evs)
    for r, e in zip(events, evs):
        r["Actual"] = e["actual"] or "—"
        if e.get("actualSrc"):
            r["actualSrc"] = e["actualSrc"]
    cos = table_with(find_section(md, "Change of Structure"), "Pair")
    sentiment = table_with(find_section(md, "Market Sentiment"), "Instrument")
    return {
        "date": date, "title": title, "path": str(path.relative_to(WIKI)),
        "overview": _brief_overview(md),
        "events": events,
        "scores": _brief_scores(md),
        "pairs": _suggested_pairs(md),
        "cos": [{"sym": clean_inline(r.get("Pair", "")), "prev": r.get("Previous Structure", ""), "cur": r.get("Current Structure", "")} for r in cos],
        "sentiment": [_sent_row(r) for r in sentiment],
        "synthesis": _synthesis(md),
        "drhr": _drhr(md),
        "watchlist": _watchlist(md),
    }


def strength_history():
    hist = []
    for date in sorted(list_briefs()):
        scores = _brief_scores(read(BRIEF_DIR / ("%s.md" % date)))
        if scores:
            hist.append({"date": date, "scores": {s["ccy"]: s["score"] for s in scores}})
    return hist


# ---------------------------------------------------------------- sentiment

def _pct(v):
    try:
        return float(str(v).replace("%", ""))
    except ValueError:
        return 0.0


def _sent_row(r):
    inst = r.get("Instrument", "")
    syms = wikilinks(inst)
    try:
        n = int(r.get("Articles", "0"))
    except ValueError:
        n = 0
    return {"name": clean_inline(re.sub(r"\s*\(\[\[.*?\]\]\)", "", inst)), "sym": syms[0] if syms else "",
            "n": n, "pos": _pct(r.get("Positive")), "neg": _pct(r.get("Negative")), "neu": _pct(r.get("Neutral")),
            "summary": r.get("Summary", "").strip() if r.get("Summary", "").strip() != "_pending_" else ""}


def latest_sentiment(date=None):
    files = sorted(SENT_DIR.glob("20??-??-??-market-sentiment.md"), reverse=True)
    if date:
        files = [f for f in files if f.name.startswith(date)] or files
    for f in files:
        md = read(f)
        runs = split_sections(md, 2)
        runs = [(h, b) for h, b in runs if h.startswith("🕒 Run")]
        # merge runs: later runs override earlier rows for the same instrument
        merged = {}
        for h, b in runs:
            for r in table_with(b, "Instrument"):
                row = _sent_row(r)
                key = row["sym"] or row["name"]
                if row["summary"] or key not in merged:
                    merged[key] = row
        if merged:
            return {"date": f.name[:10], "rows": list(merged.values()), "path": str(f.relative_to(WIKI))}
    return {"date": None, "rows": [], "path": None}


# ---------------------------------------------------------------- setups (TAT + brief)

ITEM_RE = re.compile(r"^(🟢|🔴|⚪)?\s*\*{0,2}`?\[\[(\w+)\]\]`?\s*(?:&\s*`?\[\[(\w+)\]\]`?)?\**\s*(?:\(([^)]*)\))?\s*[:*—–-]*\s*(.*)$")
BUCKETS = (("retest", ("retest", "pullback")), ("dual", ("highest probability", "dual")),
           ("standalone", ("standalone",)), ("other", ("thematic", "conflict", "inconsistency")))


def _bucket_of(text):
    t = text.lower()
    for name, keys in BUCKETS:
        if any(k in t for k in keys):
            return name
    return None


def parse_setup_bullets(body):
    """Extract dual-alignment / retest setups from a confluence section.

    Handles both layouts the TAT reports have used: heading-per-bucket with
    '- 🟢 **`[[SYM]]` (Bullish — thesis)**:' items, and the older single-list
    form where a bold bullet label ('**🔥 Dual Alignment — 1:**') opens the bucket.
    """
    out, cur, bucket = [], None, "dual"
    for line in body.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped.startswith("#"):
            bucket, cur = _bucket_of(stripped) or "other", None
            continue
        if not stripped.startswith("- "):
            continue
        content = stripped[2:].strip()
        if indent == 0:
            lab = re.match(r"\*\*([^*]+?)\*\*:?\s*(.*)$", content)
            if lab and "[[" not in lab.group(1) and _bucket_of(lab.group(1)):
                bucket, cur = _bucket_of(lab.group(1)), None
                content = lab.group(2).strip()
                if not content:
                    continue
        if bucket not in ("dual", "retest"):
            cur = None
            continue
        m = ITEM_RE.match(content)
        if m and (indent == 0 or m.group(1)):
            emoji, s1, s2, paren, rest = m.groups()
            d = "bull" if emoji == "🟢" else "bear" if emoji == "🔴" else direction_of(paren or rest)
            cur = {"syms": [x for x in (s1, s2) if x], "dir": d, "bucket": bucket,
                   "title": clean_inline(paren or ""), "text": clean_inline(rest).lstrip(".,;: "), "detail": []}
            out.append(cur)
        elif cur and indent > 0:
            cur["detail"].append(clean_inline(content))
    return out


# ---------------------------------------------------------------- TAT reports

def list_tat_dates():
    return sorted((p.name[:10] for p in TAT_DIR.glob("20??-??-??-tat-alert-report.md")), reverse=True)


RUN_HDR = re.compile(r"^(#{2,3}) .*?Intraday Update Run.*?\[?(\d{1,2}:\d{2}) SGT", re.M)
H1_HDR = re.compile(r"^(#{2,3}) 🕐 1H TAT Alert Analysis.*?(\d{1,2}:\d{2}) SGT", re.M)


def parse_tat_report(date):
    path = TAT_DIR / ("%s-tat-alert-report.md" % date)
    md = strip_toc(read(path))
    if not md:
        return None
    cands = sorted([(m.start(), m.group(2)) for m in RUN_HDR.finditer(md)] +
                   [(m.start(), m.group(2)) for m in H1_HDR.finditer(md)])
    starts = []  # (pos, time); an H1 heading opens a run only when no run header for that time precedes it
    for pos, t in cands:
        if not starts or starts[-1][1] != t:
            starts.append((pos, t))
    runs = []
    for i, (pos, t) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(md)
        body = md[pos:end].strip().rstrip("-").strip()
        conf = ""
        cm = re.search(r"^#{2,4} .*Confluence.*$", body, re.M)
        if cm:
            nxt = re.search(r"^#{2,3} (📸|📊)", body[cm.end():], re.M)
            conf = body[cm.end(): cm.end() + nxt.start()] if nxt else body[cm.end():]
        diff = find_section(body, "Differences", 3) or find_section(body, "Differences", 2)
        runs.append({"time": t.zfill(5), "md": body, "setups": parse_setup_bullets(conf),
                     "diff": table_with(diff, "Metric")})
    title = (re.search(r"^# (.+)$", md, re.M) or [None, date])[1]
    return {"date": date, "title": title, "path": str(path.relative_to(WIKI)), "runs": runs}


WATCHLIST_HDR_RE = re.compile(r"^## .*My-Watchlist 4H Chart Screenshots.*$", re.M)


def my_watchlist_gallery():
    """Latest 'My-Watchlist 4H Chart Screenshots' section across TAT reports.

    scripts/capture_watchlist_charts.py emits one such section per scheduled 4H
    run (see AGENTS.md's My-Watchlist 4H Screenshot Rule); a report file can
    carry several same-day sections (intraday reruns append, never overwrite),
    so this takes the *last* occurrence in the newest report file that has one.
    """
    for date in list_tat_dates():
        path = TAT_DIR / ("%s-tat-alert-report.md" % date)
        md = strip_toc(read(path))
        if not md:
            continue
        marks = list(WATCHLIST_HDR_RE.finditer(md))
        if not marks:
            continue
        last = marks[-1]
        nxt = re.search(r"^## ", md[last.end():], re.M)
        body = md[last.end(): last.end() + nxt.start()] if nxt else md[last.end():]
        times = re.findall(r"\[(\d{1,2}:\d{2}) SGT\]", md[:last.start()])
        entries = [{"sym": m.group(1).upper(), "img": os.path.basename(m.group(2))}
                   for m in re.finditer(r"!\[(\w+)[^\]]*\]\(([^)]+)\)", body)]
        return {"date": date, "time": times[-1] if times else None,
                "path": str(path.relative_to(WIKI)), "entries": entries}
    return {"date": None, "time": None, "path": None, "entries": []}


# ---------------------------------------------------------------- Daily Signals reports

def list_dsig_dates():
    return sorted((p.name[:10] for p in DSIG_DIR.glob("20??-??-??_Daily_Signals.md")), reverse=True)


def parse_daily_signals_report(date):
    path = DSIG_DIR / ("%s_Daily_Signals.md" % date)
    md = strip_toc(read(path))
    if not md:
        return None
    summary = ""
    for h, b in split_sections(md, 2):
        if "Executive Summary" in h:
            summary = b.strip().rstrip("-").strip()
            break
    return {"date": date, "path": str(path.relative_to(WIKI)), "summary": summary}


# ---------------------------------------------------------------- AHH session notes

SESSION_TYPES = [("ahh-access-time", "AHH Access Time"), ("ahh-session", "AHH Session"),
                 ("taw-pro", "TAW Pro"), ("tat-pro", "TAT Pro"), ("weekly-review", "Weekly Review"),
                 ("tar-session", "TAR Session")]
# Section headings that hold per-instrument trade ideas, across every layout the notes have used
IDEA_SECTIONS = ("opportunit", "instrument", "claims", "forex pairs", "commodities", "indices", "stocks")


def _session_type(stem):
    for key, label in SESSION_TYPES:
        if key in stem:
            return label
    return "Session"


def parse_ahh_note(path):
    md = strip_frontmatter(read(path))
    stem = path.stem
    date = stem[:10]
    ideas, rules = [], []
    summary = find_section(md, "Executive Summary")
    for h, body in split_sections(md, 2):
        hl = h.lower()
        if any(k in hl for k in IDEA_SECTIONS):
            ideas.extend(_ahh_ideas(body))
        elif "rule" in hl:
            for m in re.finditer(r"^\s*-\s*\*\*(.+?)\*\*:?\s*(.*)$", body, re.M):
                rules.append({"name": clean_inline(m.group(1)).rstrip(":"), "text": clean_inline(m.group(2))})
            if not rules:
                for m in re.finditer(r"^\s*-\s+(.+)$", body, re.M):
                    rules.append({"name": "", "text": clean_inline(m.group(1))})
    for i, idea in enumerate(ideas):
        idea.update(date=date, session=_session_type(stem), note=str(path.relative_to(WIKI)), id="%s#%d" % (stem, i))
    for r in rules:
        r.update(date=date, session=_session_type(stem), note=str(path.relative_to(WIKI)))
    return {"date": date, "session": _session_type(stem), "path": str(path.relative_to(WIKI)),
            "summary": summary.strip().rstrip("-").strip(), "ideas": ideas, "rules": rules}


SYM_REF = r"(?:\[\[[^\]]+\]\]|\[[^\]]+\]\([^)]*entities/[^)]*\))"
IDEA_HEADS = [
    re.compile(r"^\d+\.\s+\*\*(.+?)\*\*\s*(.*)$"),                          # 1. **[[SYM]]** ...
    re.compile(r"^\d+\.\s+(%s[^:\n]*?)\s+[-–—]\s+(.*)$" % SYM_REF),              # 1. [[SYM]] - text
    re.compile(r"^-\s+\*\*(.*?%s.*?)\*\*:?\s*(.*)$" % SYM_REF),                  # - **[[SYM]] (Name)**: text
]
TIMESTAMP = re.compile(r"\s*\[\d{1,2}:\d{2}(?::\d{2})?\]")


def _idea_rest(cur, rest):
    """Fold the text after an idea's heading into its fields."""
    rest = rest.strip()
    paren = re.match(r"^(\([^)]*\))\s*(.*)$", rest)
    if paren:
        cur["title"] += " " + clean_inline(paren.group(1))
        rest = paren.group(2)
    rest = re.sub(r"^[-–—:]+\s*", "", rest)
    field = re.match(r"^\*\*([A-Z][\w &/]{1,30}?)\*\*:?\s*(.*)$", rest)
    if field:
        cur["fields"][field.group(1).rstrip(":")] = clean_inline(field.group(2))
    elif rest:
        cur["fields"]["Setup"] = clean_inline(rest)


def _ahh_ideas(body):
    """Parse per-instrument ideas from a session note section.

    Handles numbered items with bold or plain symbol heads, and bold-symbol bullets,
    each optionally followed by '- **Key**: value' or '- Key: value' sub-bullets.
    """
    ideas, cur = [], None
    for line in body.splitlines():
        head = next((m for m in (rx.match(line) for rx in IDEA_HEADS) if m), None)
        if head and wikilinks(head.group(1)):
            cur = {"title": clean_inline(head.group(1)).rstrip(":").strip(), "syms": wikilinks(head.group(1)), "fields": {}}
            _idea_rest(cur, head.group(2))
            ideas.append(cur)
            continue
        if not cur or not re.match(r"^\s+-\s+", line):
            continue
        sub = re.match(r"^\s+-\s+\*\*(.+?)\*\*:?\s*(.*)$", line) or re.match(r"^\s+-\s+([A-Z][\w &/]{1,25}):\s+(.*)$", line)
        if sub and "[[" not in sub.group(1):
            cur["fields"][sub.group(1).rstrip(":")] = clean_inline(sub.group(2))
        else:
            cur["fields"]["Notes"] = (cur["fields"].get("Notes", "") + " " + clean_inline(line.strip()[2:])).strip()
    for idea in ideas:
        f = {k: TIMESTAMP.sub("", v).strip() for k, v in idea["fields"].items()}
        dtext = f.get("Direction") or idea["title"] + " " + f.get("Setup", "")
        low = dtext.lower()
        idea["dir"] = "neutral" if re.match(r"\s*(neutral|watch|wait|range|stuck)", low) else direction_of(dtext)
        idea["direction"] = f.get("Direction", "")
        idea["levels"] = f.get("Key Levels") or f.get("Key levels", "")
        setup = f.get("Timeframe & Setup") or f.get("Setup") or ""
        idea["setup"] = " ".join(x for x in (setup, f.get("Status", ""), f.get("Notes", "")) if x)
        idea["fields"] = f
    return ideas


def all_ahh():
    """AHH Access Time / AHH Session / TAW Pro notes plus Weekly Review and TAR Session summaries, newest first."""
    paths = list(AHH_DIR.glob("20??-??-??-*.md"))
    for pattern in ("20??-??-??-weekly-review*.md", "20??-??-??-tar-session*.md"):
        paths += SOURCES_DIR.glob(pattern)
    return sorted((parse_ahh_note(p) for p in paths), key=lambda n: n["date"], reverse=True)


# ---------------------------------------------------------------- calendar & central banks

def parse_calendar():
    md = read(CAL_FILE)
    events, this_start = [], None
    for h, body in split_sections(md, 2):
        if "Events" not in h and "Results" not in h:
            continue
        week = "this" if "This Week" in h else "last" if "Last Week" in h else "next"
        if week == "this":
            m = re.search(r"\((\d{4}-\d{2}-\d{2}) to", h)
            this_start = m.group(1) if m else None
        default_lvl = "High" if "High" in h else "Medium" if "Medium" in h else "Low"
        for r in table_with(body, "Date"):
            impact = r.get("Impact", "")
            lvl = ("High" if "High" in impact else "Medium" if "Medium" in impact else "Low") if impact else default_lvl
            link = re.search(r"\((https?://[^)]+)\)", r.get("Detail", ""))
            actual = r.get("Actual", "").strip()
            events.append({"date": r.get("Date", ""), "time": r.get("Time (SGT)", ""), "impact": lvl,
                           "ccy": r.get("Currency", "").strip(), "event": r.get("Event", "").strip(),
                           "forecast": r.get("Forecast", "").strip(), "previous": r.get("Previous", "").strip(),
                           "actual": "" if actual in ("—", "-") else actual,
                           "url": link.group(1) if link else "", "week": week})
    fill_actuals(events)
    # pull_economic_calendar.py now writes a Last Week Results section; older notes lack it, so fall back
    # to fetching last week straight from TradingView.
    if this_start and not any(e["week"] == "last" for e in events):
        start = dt.date.fromisoformat(this_start)
        for ev in last_week_events(str(start - dt.timedelta(days=7)), str(start - dt.timedelta(days=1))):
            events.append(dict(ev, week="last"))
    updated = re.search(r"^updated:\s*(\S+)", md, re.M)
    return {"updated": updated.group(1) if updated else None, "events": events}


# ---------------------------------------------------------------- TradingView actuals backfill
#
# wiki/notes/economic-calendar.md is a snapshot from its last pull, and each Daily Brief's event table is
# captured at 05:01 SGT — before most releases — so released events often still show no Actual. These
# helpers fetch the same TradingView calendar feed pull_economic_calendar.py uses and fill the gaps.

TV_CAL_URL = "https://economic-calendar.tradingview.com/events?from=%s&to=%s"
TV_CCYS = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "CNY"}
_tv_cache = {}


def _tv_value(v, unit, scale):
    if v is None:
        return ""
    num = ("%.4f" % v).rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
    return num + (scale or "") + ("%" if unit == "%" else "")


def _tv_impact(ev):
    """Same folder mapping as pull_economic_calendar.classify_folder_event."""
    if ev.get("currency") not in TV_CCYS:
        return None
    if ev.get("currency") == "EUR" and ev.get("country") not in ("EU", "DE"):
        return None
    return {1: "High", 0: "Medium", -1: "Low"}.get(ev.get("importance"))


def tv_events(start, end):
    """TradingView calendar events between two SGT dates (inclusive), cached; [] if the feed is unreachable."""
    key = (start, end)
    hit = _tv_cache.get(key)
    ttl = 900 if end >= str(now_sgt().date() - dt.timedelta(days=1)) else 6 * 3600
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    f = dt.datetime.fromisoformat(start + "T00:00:00+08:00").astimezone(dt.timezone.utc)
    t = dt.datetime.fromisoformat(end + "T23:59:59+08:00").astimezone(dt.timezone.utc)
    url = TV_CAL_URL % (f.strftime("%Y-%m-%dT%H:%M:%S.000Z"), t.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Origin": "https://www.tradingview.com"})
    out = []
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8")).get("result", [])
        for ev in data:
            impact = _tv_impact(ev)
            if not impact:
                continue
            when = dt.datetime.strptime(ev["date"], "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=dt.timezone.utc).astimezone(SGT)
            unit, scale = ev.get("unit"), ev.get("scale")
            out.append({"date": when.strftime("%Y-%m-%d"), "time": when.strftime("%H:%M"), "impact": impact,
                        "ccy": ev.get("currency", ""), "event": ev.get("title", ""),
                        "forecast": _tv_value(ev.get("forecast"), unit, scale),
                        "previous": _tv_value(ev.get("previous"), unit, scale),
                        "actual": _tv_value(ev.get("actual"), unit, scale),
                        "url": "https://www.tradingview.com/economic-calendar/", "actualSrc": "TradingView"})
        out.sort(key=lambda e: (e["date"], e["time"], e["ccy"]))
        _tv_cache[key] = (time.time(), out)
    except Exception:
        _tv_cache[key] = (time.time() - ttl + 300, hit[1] if hit else [])  # back off 5 min, keep any old copy
        return hit[1] if hit else []
    return out


def _title_tokens(title):
    t = title.lower().replace("m/m", " mom").replace("y/y", " yoy").replace("q/q", " qoq")
    toks = {("change" if w == "chg" else w) for w in re.findall(r"[a-z0-9]+", t)}
    # Forex Factory says "Cash Rate" / "Policy Rate" / "Official Bank Rate"; TradingView says "Interest Rate Decision"
    if re.search(r"\b(cash|policy|bank|overnight|refinancing|funds|interest)\s+rate\b", t):
        toks |= {"interest", "rate", "decision"}
    return toks - {"the", "of", "and", "s"}


def _when(e):
    try:
        return dt.datetime.fromisoformat("%sT%s:00+08:00" % (e["date"], e["time"].strip().zfill(5)))
    except (ValueError, KeyError, AttributeError):
        return None


def match_events(mine, theirs):
    """One-to-one pairs (my_event, tv_event), best title match first.

    Same currency, and either released within 10 minutes of each other, or the same day with a strong title
    match (central banks often release later than Forex Factory's tentative time, e.g. BoJ 10:30 vs 11:00).
    """
    pairs = []
    for i, e in enumerate(mine):
        we, te = _when(e), _title_tokens(e.get("event", ""))
        if not we:
            continue
        for j, c in enumerate(theirs):
            wc = _when(c)
            if c["ccy"] != e.get("ccy") or not wc:
                continue
            tc = _title_tokens(c["event"])
            score = len(te & tc) / float(len(te | tc) or 1)
            gap = abs((wc - we).total_seconds())
            if (gap <= 600 and score >= 0.34) or (c["date"] == e["date"] and gap <= 3 * 3600 and score >= 0.5):
                pairs.append((score, -gap, i, j))
    pairs.sort(reverse=True)
    used_i, used_j, out = set(), set(), []
    for score, _, i, j in pairs:
        if i not in used_i and j not in used_j:
            used_i.add(i)
            used_j.add(j)
            out.append((mine[i], theirs[j]))
    return out


def fill_actuals(events):
    """Fill `actual` in place on released events that lack one. Returns how many were filled."""
    now = now_sgt()
    todo = [e for e in events if not e.get("actual") and _when(e) and _when(e) < now]
    if not todo:
        return 0
    tv = [c for c in tv_events(min(e["date"] for e in todo), max(e["date"] for e in todo)) if c["actual"]]
    pairs = match_events(todo, tv)
    for e, c in pairs:
        e["actual"], e["actualSrc"] = c["actual"], "TradingView"
    return len(pairs)


def last_week_events(start, end):
    """Past week from TradingView, with each Daily Brief's red-folder events kept High-impact.

    TradingView's own importance flags fewer events as high than Forex Factory's red folder, so events the
    briefs listed are promoted to High (and briefs' events TradingView lacks, like press conferences, are kept).
    """
    tv = [dict(e) for e in tv_events(start, end)]
    brief_events = []
    for date in list_briefs():
        if start <= date <= end:
            for r in table_with(find_section(read(BRIEF_DIR / ("%s.md" % date)), "Economic Events"), "Time"):
                brief_events.append({"date": date, "time": r.get("Time (SGT)", "").strip(), "impact": "High",
                                     "ccy": r.get("Currency", "").strip(), "event": r.get("Event", "").strip(),
                                     "forecast": r.get("Forecast", "").strip(), "previous": r.get("Previous", "").strip(),
                                     "actual": "", "url": (re.search(r"\((https?://[^)]+)\)", r.get("Detail", "")) or [None, ""])[1]})
    matched = set()
    for b, c in match_events(brief_events, tv):
        c["impact"] = "High"
        matched.add(id(b))
    tv += [b for b in brief_events if id(b) not in matched]
    return sorted(tv, key=lambda e: (e["date"], e["time"], e["ccy"]))


def parse_cb_tally():
    md = read(CB_FILE)
    stances = []
    for r in table_with(find_section(md, "Current Stances"), "Bank"):
        st = r.get("Stance", "")
        lean = "hawk" if "Hawk" in st else "dove" if "Dov" in st else "neutral"
        stances.append({"bank": r.get("Bank", ""), "stance": st, "lean": lean,
                        "changed": r.get("Last Changed", ""), "trigger": clean_inline(re.sub(r"\(see \[.*?\]\(.*?\)\)", "", r.get("Trigger Event", "")))})
    nxt = {r.get("Bank", ""): {"when": r.get("Next Scheduled Update", ""), "type": r.get("Event Type", "")}
           for r in table_with(find_section(md, "Next Scheduled"), "Bank")}
    for s in stances:
        s["next"] = nxt.get(s["bank"], {})
    updated = re.search(r"^updated:\s*(\S+)", md, re.M)
    return {"updated": updated.group(1) if updated else None, "stances": stances}


# ---------------------------------------------------------------- live alert sheet

SHEET_TABS = [  # (key in fetch_google_sheet.GIDS, dashboard source id, label)
    ("H1", "1H", "1H"), ("4H", "4H", "4H"), ("DAILY", "D", "Daily FX"),
    ("BATS", "BATS", "TV Stocks (bats)"), ("BULL", "YBULL", "Yahoo Bull D"), ("BEAR", "YBEAR", "Yahoo Bear D"),
]
SHEET_TTL = 300


def _norm_date(s):
    s = str(s or "").strip().split(" ")[0]
    if "/" in s:
        p = s.split("/")
        if len(p) == 3:
            return "%s-%s-%s" % (p[2], p[1].zfill(2), p[0].zfill(2))
    return s


def _norm_time(s):
    s = str(s or "").strip()
    if not s:
        return ""
    parts = s.split(":")
    return ":".join(x.zfill(2) for x in parts)


def _norm_sym(raw, source):
    s = str(raw or "").strip().upper()
    exch = ""
    if ":" in s:
        exch, s = s.split(":", 1)
    if s.endswith(".SI"):
        exch, s = "SGX", s[:-3]
    elif s.endswith(".HK"):
        exch, s = "HKEX", s[:-3].lstrip("0") or "0"
    elif source in ("YBULL", "YBEAR") and not exch:
        exch = "US"
    return s, exch


class SheetCache:
    def __init__(self):
        self.lock = threading.Lock()
        self.rows = []
        self.fetched_at = None
        self.error = None
        self.loading = False
        self.tab_counts = {}

    def get(self, force=False):
        stale = self.fetched_at is None or (time.time() - self.fetched_at) > SHEET_TTL
        if (force or stale) and not self.loading:
            if self.fetched_at is None or force:
                self._refresh()
            else:
                threading.Thread(target=self._refresh, daemon=True).start()
        return self.rows

    def _refresh(self):
        with self.lock:
            if self.loading:
                return
            self.loading = True
        try:
            sys.path.insert(0, str(ROOT))
            from scripts.fetch_google_sheet import fetch_with_service_account  # noqa
            import contextlib
            import io

            def pull(tab):
                key, src, label = tab
                with contextlib.redirect_stdout(io.StringIO()):
                    recs = fetch_with_service_account(key) or []
                return src, label, recs

            rows, counts = [], {}
            with ThreadPoolExecutor(max_workers=6) as ex:
                for src, label, recs in ex.map(pull, SHEET_TABS):
                    counts[src] = len(recs)
                    for r in recs:
                        rows.append(self._row(src, label, r))
            rows = [r for r in rows if r["sym"] and r["date"]]
            rows.sort(key=lambda r: (r["date"], r["time"]), reverse=True)
            self.rows, self.tab_counts, self.error = rows, counts, None
            self.fetched_at = time.time()
        except Exception as e:  # keep serving the last good copy
            self.error = "%s: %s" % (type(e).__name__, e)
            if self.fetched_at is None:
                self.fetched_at = time.time() - SHEET_TTL + 60  # retry in a minute, not on every request
        finally:
            self.loading = False

    @staticmethod
    def _row(src, label, r):
        if src in ("YBULL", "YBEAR"):
            sym, exch = _norm_sym(r.get("Yahoo Symbol"), src)
            sig = str(r.get("Signal", ""))
            return {"src": src, "srcLabel": label, "date": _norm_date(r.get("Date & Time")), "time": "",
                    "sym": sym, "exch": exch, "name": r.get("Stock Name", ""), "signal": sig,
                    "dir": signal_direction(sig), "price": r.get("Signal Price", ""),
                    "event": "", "sector": " / ".join(x for x in (r.get("Sector", ""), r.get("Sub-Sector", "")) if x),
                    "cls": "Stock"}
        sym, exch = _norm_sym(r.get("Symbol"), src)
        sig = str(r.get("Signal Type", ""))
        d = signal_direction(sig) if sig else signal_direction(r.get("Direction"))
        event = re.sub(r"\.?\s*Filtered:.*$", "", str(r.get("Event", ""))).strip()
        return {"src": src, "srcLabel": label, "date": _norm_date(r.get("Date")), "time": _norm_time(r.get("Time")),
                "sym": sym, "exch": exch, "name": r.get("Name", ""), "signal": sig, "dir": d,
                "price": r.get("Signal Price", ""), "event": event, "sector": "",
                "cls": "Stock" if src == "BATS" else asset_class(sym)}


SHEET = SheetCache()


# ---------------------------------------------------------------- trade journal

def all_journal():
    """Every wiki/notes/journal/ entry with its behaviour flags (parsing lives in scripts/journal.py)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts import journal  # noqa
    return journal.load_all()
