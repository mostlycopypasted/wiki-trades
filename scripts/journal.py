#!/usr/bin/env python3
"""
Trade journal — one markdown file per trade in wiki/notes/journal/.

Frontmatter holds the countable fields (prices, R, emotion, FOMO score, mistakes);
the body holds your reasoning, feelings and a running comment log. The dashboard's
Journal tab reads the same files through load_all() below.

Usage:
  python3 scripts/journal.py new GBPAUD long --entry 1.9070 --stop 1.8999 --target 1.9212 \\
      --tf 1H --setup "TAT OptBull retest" --source tat-report --planned yes --fomo 1 --emotion calm
  python3 scripts/journal.py comment GBPAUD "moved stop to BE, felt relieved"
  python3 scripts/journal.py close GBPAUD --exit 1.9150 --mistakes early-exit
  python3 scripts/journal.py list [--open]
  python3 scripts/journal.py stats [--days 30]
  python3 scripts/journal.py sync      # rewrite the Trade Journal tab in the Fusion tracker sheet (also runs after new/comment/close)

On a terminal, `new` prompts for anything not passed as a flag (Enter skips).
Use --no-prompt (and --why/--feel) when scripting or logging on someone's behalf.
Backfill an older trade with --opened "YYYY-MM-DD HH:MM" (and close --closed ...).
"""

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
JOURNAL_DIR = WIKI / "notes" / "journal"
TAT_DIR = WIKI / "reports" / "tat_analysis"
DSIG_DIR = WIKI / "reports" / "daily-signals"
BRIEF_DIR = WIKI / "reports" / "daily_brief"

SGT = dt.timezone(dt.timedelta(hours=8))
TIME_FMT = "%Y-%m-%d %H:%M"

CRYPTO = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "NEAR", "LTC", "BNB", "AVAX", "DOT", "LINK", "TRX", "SHIB"}
EMOTIONS = ["calm", "confident", "excited", "anxious", "bored", "frustrated", "impatient", "revenge"]
SOURCES = ["daily-brief", "tat-report", "daily-signals", "ahh", "own", "social", "none"]
MISTAKES = ["chased-entry", "no-stop", "moved-stop", "oversized", "early-exit", "late-exit", "revenge",
            "overtrading", "against-htf-bias", "news-gamble", "anticipated-signal"]
CHECKLIST = [
    "It was in my plan before this session",
    "The signal bar had CLOSED (I wasn't anticipating it)",
    "I'm entering at a level, not chasing a move that already ran",
    "Stop and target were set before I clicked",
    "It's been more than 1h since my last loss",
    "I'd take this even if I hadn't just watched a move I missed",
    "On the higher timeframe I marked the last swing high/low, and I'm entering at the 38.2-50% pullback, not near the extreme",
]
FIELDS = ["type", "symbol", "direction", "status", "opened", "closed", "timeframe", "setup", "idea_source",
          "planned", "entry", "stop", "target", "size", "risk_pct", "exit", "result_r", "pnl",
          "emotion_before", "confidence", "fomo", "rules_followed", "mistakes"]
LIST_FIELDS = {"emotion_before", "mistakes"}
NUM_FIELDS = {"entry", "stop", "target", "size", "risk_pct", "exit", "result_r", "pnl", "confidence", "fomo"}

REVENGE_MIN = 60      # a trade opened within this many minutes of a loss closing is flagged
OVERTRADE_N = 4       # the Nth trade of a day (and beyond) is flagged
HIGH_FOMO = 3


# ---------------------------------------------------------------- frontmatter

FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def _parse_value(key, raw):
    v = re.sub(r"\s+#.*$", "", raw).strip().strip('"').strip("'")
    if key in LIST_FIELDS or (v.startswith("[") and v.endswith("]")):
        return [x.strip().strip('"').strip("'") for x in v.strip("[]").split(",") if x.strip()]
    if not v:
        return None
    if key in NUM_FIELDS:
        try:
            return float(v)
        except ValueError:
            return None
    return v


def parse_frontmatter(md):
    """Flat YAML only: `key: value` and `key: [a, b]`. Comment and continuation lines are skipped."""
    m = FM_RE.match(md)
    if not m:
        return {}, md
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#") or line[:1].isspace():
            continue
        k, sep, v = line.partition(":")
        if sep:
            fm[k.strip()] = _parse_value(k.strip(), v)
    return fm, md[m.end():]


def _fmt_value(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(v) + "]"
    if isinstance(v, float):
        return ("%.5f" % v).rstrip("0").rstrip(".")
    return str(v)


def set_fields(md, updates):
    """Rewrite only the given frontmatter keys, leaving every other line untouched."""
    m = FM_RE.match(md)
    if not m:
        raise ValueError("entry has no frontmatter")
    lines = m.group(1).splitlines()
    for key, val in updates.items():
        new = "%s: %s" % (key, _fmt_value(val))
        for i, line in enumerate(lines):
            if re.match(r"%s\s*:" % re.escape(key), line):
                lines[i] = new.rstrip()
                break
        else:
            lines.append(new.rstrip())
    return "---\n" + "\n".join(lines) + "\n---\n" + md[m.end():]


# ---------------------------------------------------------------- helpers

def now_sgt():
    return dt.datetime.now(SGT).replace(tzinfo=None)


def parse_time(s):
    try:
        return dt.datetime.strptime(str(s).strip()[:16], TIME_FMT)
    except (TypeError, ValueError):
        return None


def norm_symbol(sym):
    s = re.sub(r"[^A-Z0-9.]", "", sym.upper())
    if s.endswith("USDT"):
        s = s[:-1]
    if s in CRYPTO:
        s += "USD"
    return s


def compute_r(fm):
    try:
        entry, stop, ex = float(fm["entry"]), float(fm["stop"]), float(fm["exit"])
    except (KeyError, TypeError, ValueError):
        return None
    risk = abs(entry - stop)
    if not risk:
        return None
    sign = -1 if str(fm.get("direction", "")).lower() == "short" else 1
    return round(sign * (ex - entry) / risk, 2)


def entry_files():
    if not JOURNAL_DIR.is_dir():
        return []
    return sorted(p for p in JOURNAL_DIR.glob("*.md") if not p.name.startswith("_"))


def sections(body):
    out, cur = {}, None
    for line in body.splitlines():
        m = re.match(r"^## (.+?)\s*$", line)
        if m:
            cur = m.group(1).strip()
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def _section(secs, *needles):
    for k, v in secs.items():
        if any(n in k.lower() for n in needles):
            return v
    return ""


COMMENT_RE = re.compile(r"^-\s+\*\*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\*\*\s*[—–-]\s*(.*)$")


def load_entry(path):
    md = path.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(md)
    if fm.get("type") != "trade-journal":
        return None
    secs = sections(body)
    comments = [{"at": m.group(1), "text": m.group(2).strip()}
                for m in map(COMMENT_RE.match, _section(secs, "comment").splitlines()) if m]
    checks = re.findall(r"^- \[( |x|X)\] (.+)$", _section(secs, "fomo check"), re.M)
    e = {k: fm.get(k) for k in FIELDS}
    e["symbol"] = norm_symbol(e.get("symbol") or "")
    e["direction"] = (e.get("direction") or "").lower()
    e["status"] = (e.get("status") or "open").lower()
    e["emotion_before"] = e.get("emotion_before") or []
    e["mistakes"] = e.get("mistakes") or []
    if e.get("result_r") is None and e["status"] == "closed":
        e["result_r"] = compute_r(e)
    e.update(
        id=path.stem,
        path=str(path.relative_to(WIKI)),
        why=_section(secs, "why"),
        feel=_section(secs, "how i feel", "feel"),
        during=_section(secs, "during"),
        outcome=_section(secs, "exit", "outcome"),
        lessons=_section(secs, "lesson"),
        comments=comments,
        checklist={"done": sum(c[0].lower() == "x" for c in checks), "total": len(checks)},
    )
    return e


# ---------------------------------------------------------------- plan evidence from the wiki

def _mentions(text, sym):
    return re.search(r"\[\[%s\]\]|\b%s\b" % (re.escape(sym), re.escape(sym)), text) is not None


def _read(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def wiki_plan_evidence(sym, opened):
    """Where the symbol showed up in the wiki on the trade's date, before the trade was opened."""
    if not sym or not opened:
        return []
    date, hhmm = opened.strftime("%Y-%m-%d"), opened.strftime("%H:%M")
    found = []
    # TAT report: only runs whose SGT timestamp is at or before the trade
    tat = _read(TAT_DIR / ("%s-tat-alert-report.md" % date))
    run, hits = None, set()
    for line in tat.splitlines():
        m = re.match(r"^#{1,2} .*?(\d{1,2}:\d{2}) SGT", line)
        if m:
            run = m.group(1).zfill(5)
        if run and run <= hhmm and _mentions(line, sym):
            hits.add(run)
    if hits:
        found.append("TAT " + ", ".join(sorted(hits)))
    # Daily Signals: written ~05:45, so it counts for any trade after that
    if hhmm >= "05:45" and _mentions(_read(DSIG_DIR / ("%s_Daily_Signals.md" % date)), sym):
        found.append("Daily Signals")
    # Daily Brief: everything above the per-instrument chart gallery (which lists the whole watchlist)
    brief = _read(BRIEF_DIR / ("%s.md" % date)).split("Daily Watchlist Charts")[0]
    if hhmm >= "05:30" and _mentions(brief, sym):
        found.append("Daily Brief")
    return found


# ---------------------------------------------------------------- load + behaviour flags

def load_all():
    entries = [e for e in map(load_entry, entry_files()) if e]
    entries.sort(key=lambda e: e.get("opened") or "")
    losses = []  # close times of losing trades seen so far
    per_day = {}
    for e in entries:
        opened = parse_time(e.get("opened"))
        day = opened.strftime("%Y-%m-%d") if opened else ""
        per_day[day] = per_day.get(day, 0) + (1 if e["status"] != "cancelled" else 0)
        e["nth_today"] = per_day[day]
        prior = [t for t in losses if opened and t <= opened]
        e["after_loss_min"] = int((opened - max(prior)).total_seconds() // 60) if prior else None
        e["plan_evidence"] = wiki_plan_evidence(e["symbol"], opened)
        fomo = e.get("fomo")
        planned = str(e.get("planned") or "").lower()
        e["flags"] = [f for f, on in [
            ("high-fomo", fomo is not None and fomo >= HIGH_FOMO),
            ("unplanned", planned == "no"),
            ("no-wiki-plan", not e["plan_evidence"]),
            ("revenge", e["after_loss_min"] is not None and e["after_loss_min"] < REVENGE_MIN),
            ("overtrading", e["nth_today"] >= OVERTRADE_N),
            ("no-stop", e["status"] != "cancelled" and (e.get("stop") in (None, "") or "no-stop" in e["mistakes"])),
            ("rules-broken", str(e.get("rules_followed") or "").lower() == "no"),
        ] if on]
        closed = parse_time(e.get("closed"))
        if e["status"] == "closed" and (e.get("result_r") or 0) < 0 and closed:
            losses.append(closed)
    return entries


# ---------------------------------------------------------------- commands

def _ask(label, default=None, choices=None):
    hint = " [%s]" % "/".join(choices) if choices else ""
    try:
        v = input("%s%s%s: " % (label, hint, " (%s)" % default if default not in (None, "") else "")).strip()
    except EOFError:
        v = ""
    return v or default


def _log(action, title, body):
    try:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "append_log.py"), "--action", action,
                        "--title", title, "--body", body], check=False, capture_output=True)
    except OSError:
        pass


# ---------------------------------------------------------------- Google Sheet mirror

SHEET_ID = "1mX_2qAY6vYTXm63XvGawFrrmVU4DnNj3HZVehQv3fOs"
SHEET_TAB = "Trade Journal"
SA_FILE = Path("/Users/chriseah/tradingview-mcp/service_account.json")
SHEET_COLS = ["Opened (SGT)", "Closed (SGT)", "Symbol", "Direction", "Status", "Timeframe", "Setup", "Entry", "Stop",
              "Target", "Exit", "Size", "Result (R)", "P&L (SGD)", "FOMO (0-5)", "Confidence (1-5)", "Emotion before",
              "Planned", "Idea source", "Wiki plan evidence", "Flags", "Mistakes", "Rules followed", "Why I took it",
              "How I felt", "Lessons", "Comments", "Entry file"]


def sheet_rows(entries):
    def cell(v):
        return "" if v is None else v
    rows = []
    for e in sorted(entries, key=lambda e: e.get("opened") or "", reverse=True):
        rows.append([
            cell(e.get("opened")), cell(e.get("closed")), e["symbol"], e["direction"], e["status"],
            cell(e.get("timeframe")), cell(e.get("setup")), cell(e.get("entry")), cell(e.get("stop")),
            cell(e.get("target")), cell(e.get("exit")), cell(e.get("size")), cell(e.get("result_r")),
            cell(e.get("pnl")), cell(e.get("fomo")), cell(e.get("confidence")), ", ".join(e["emotion_before"]),
            cell(e.get("planned")), cell(e.get("idea_source")), ", ".join(e["plan_evidence"]),
            ", ".join(e["flags"]), ", ".join(e["mistakes"]), cell(e.get("rules_followed")), e["why"], e["feel"],
            e["lessons"], "\n".join("%s — %s" % (c["at"], c["text"]) for c in e["comments"]), e["path"],
        ])
    return rows


def sync_sheet(quiet=False):
    """Rewrite the Trade Journal tab from the journal files. Never raises: a sheet problem must not block logging."""
    try:
        import gspread
        ws = gspread.service_account(filename=str(SA_FILE)).open_by_key(SHEET_ID).worksheet(SHEET_TAB)
        data = [SHEET_COLS] + sheet_rows(load_all())
        ws.clear()
        ws.update(values=data, range_name="A1", value_input_option="RAW")
        ws.freeze(rows=1)
        ws.format("A1:AB1", {"textFormat": {"bold": True}})
        ws.format("A2:AB%d" % max(len(data), 2), {"verticalAlignment": "TOP"})
        ws.format("X2:AA%d" % max(len(data), 2), {"wrapStrategy": "WRAP"})
        if not quiet:
            print("📄 Synced %d trades to the %s tab" % (len(data) - 1, SHEET_TAB))
    except Exception as ex:  # noqa: BLE001
        print("⚠️ Google Sheet sync skipped (%s: %s)" % (type(ex).__name__, ex), file=sys.stderr)


def cmd_sync(a):
    sync_sheet()


def find_entry(ref):
    files = entry_files()
    exact = [p for p in files if p.stem == ref or p.name == ref]
    if exact:
        return exact[0]
    sym = norm_symbol(ref)
    cands = [e for e in map(load_entry, files) if e and e["symbol"] == sym]
    if not cands:
        sys.exit("❌ No journal entry for %s" % ref)
    open_ = [e for e in cands if e["status"] == "open"]
    pick = max(open_ or cands, key=lambda e: e.get("opened") or "")
    return JOURNAL_DIR / (pick["id"] + ".md")


def cmd_new(a):
    interactive = sys.stdin.isatty() and not a.no_prompt
    sym = norm_symbol(a.symbol)
    direction = a.direction.lower()
    opened = parse_time(a.opened) if a.opened else now_sgt()
    if not opened:
        sys.exit("❌ --opened must be 'YYYY-MM-DD HH:MM'")
    v = {"entry": a.entry, "stop": a.stop, "target": a.target, "size": a.size, "risk_pct": a.risk,
         "timeframe": a.tf, "setup": a.setup, "idea_source": a.source, "planned": a.planned,
         "fomo": a.fomo, "confidence": a.confidence, "rules_followed": a.rules,
         "emotion_before": a.emotion.split(",") if a.emotion else None}
    why, feel = a.why or "", a.feel or ""
    checks = {int(x) for x in (a.checks or "").split(",") if x.strip().isdigit()}
    if interactive:
        print("📝 %s %s — Enter skips a field" % (sym, direction))
        for k, label, ch in [("entry", "Entry price", None), ("stop", "Stop loss", None), ("target", "Target", None),
                             ("size", "Size (lots/units)", None), ("risk_pct", "Risk % of account", None),
                             ("timeframe", "Timeframe", None), ("setup", "Setup (signal/level)", None),
                             ("idea_source", "Idea came from", SOURCES), ("planned", "In your plan before the session?", ["yes", "no"])]:
            if v[k] is None:
                v[k] = _ask(label, choices=ch)
        if v["emotion_before"] is None:
            em = _ask("Feeling right now (comma list: %s)" % ", ".join(EMOTIONS))
            v["emotion_before"] = [x.strip() for x in em.split(",")] if em else None
        if v["confidence"] is None:
            v["confidence"] = _ask("Confidence 1-5")
        if v["fomo"] is None:
            v["fomo"] = _ask("FOMO 0-5 (0 none, 5 had to get in)")
        why = why or _ask("Why are you taking this trade?", "")
        feel = feel or _ask("How do you feel (in your own words)?", "")
        print("FOMO check — answer honestly (y/n):")
        for i, c in enumerate(CHECKLIST):
            if (_ask("  " + c, "n") or "n").lower().startswith("y"):
                checks.add(i)
    fm = {"type": "trade-journal", "symbol": sym, "direction": direction, "status": "open",
          "opened": opened.strftime(TIME_FMT), "closed": None}
    for k in FIELDS:
        if k not in fm:
            fm[k] = v.get(k)
    fm["emotion_before"] = [x for x in (fm["emotion_before"] or []) if x]
    fm["mistakes"] = []
    fm["rules_followed"] = fm["rules_followed"] or None
    fm_lines = "\n".join(("%s: %s" % (k, _fmt_value(fm.get(k)))).rstrip() for k in FIELDS)
    title = "%s %s — %s SGT" % (sym, direction.capitalize(), opened.strftime(TIME_FMT))
    body = "\n".join([
        "# " + title, "",
        "**Instrument:** [[%s]] · **Direction:** %s" % (sym, "Long 🟢" if direction == "long" else "Short 🔴"), "",
        "## Why I took this trade", why or "", "",
        "## FOMO check (before entry)",
        *["- [%s] %s" % ("x" if i in checks else " ", c) for i, c in enumerate(CHECKLIST)], "",
        "## How I feel (before)", feel or "", "",
        "## During the trade", "", "",
        "## Exit & outcome", "", "",
        "## Lessons", "", "",
        "## Comments", "", "",
        "## Screenshots", "",
    ])
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    stem = "%s-%s-%s" % (opened.strftime("%Y-%m-%d-%H%M"), sym.lower(), direction)
    path, n = JOURNAL_DIR / (stem + ".md"), 2
    while path.exists():
        path, n = JOURNAL_DIR / ("%s-%d.md" % (stem, n)), n + 1
    path.write_text("---\n%s\n---\n%s" % (fm_lines, body), encoding="utf-8")
    _log("journal", "Trade opened — %s" % title, "New journal entry %s (FOMO %s, planned %s)."
         % (path.relative_to(ROOT), _fmt_value(fm.get("fomo")) or "?", fm.get("planned") or "?"))
    print("✅ %s" % path.relative_to(ROOT))
    sync_sheet(quiet=True)


def cmd_comment(a):
    path = find_entry(a.ref)
    md = path.read_text(encoding="utf-8")
    stamp = parse_time(a.at) if a.at else now_sgt()
    line = "- **%s** — %s" % (stamp.strftime(TIME_FMT), " ".join(a.text).strip())
    m = re.search(r"^## Comments[^\n]*\n", md, re.M)
    if m:
        nxt = re.search(r"^## ", md[m.end():], re.M)
        end = m.end() + (nxt.start() if nxt else len(md) - m.end())
        block = md[m.end():end].rstrip("\n")
        block = (block + "\n" if block.strip() else "") + line + "\n\n"
        md = md[:m.end()] + block + md[end:]
    else:
        md = md.rstrip("\n") + "\n\n## Comments\n" + line + "\n"
    path.write_text(md, encoding="utf-8")
    print("💬 %s → %s" % (line, path.relative_to(ROOT)))
    sync_sheet(quiet=True)


def cmd_close(a):
    path = find_entry(a.ref)
    md = path.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(md)
    closed = parse_time(a.closed) if a.closed else now_sgt()
    upd = {"status": "cancelled" if a.cancel else "closed", "closed": closed.strftime(TIME_FMT)}
    if a.exit is not None:
        upd["exit"] = a.exit
    if a.pnl is not None:
        upd["pnl"] = a.pnl
    if a.rules:
        upd["rules_followed"] = a.rules
    if a.mistakes:
        upd["mistakes"] = sorted(set((fm.get("mistakes") or []) + a.mistakes.split(",")))
    r = a.r if a.r is not None else compute_r(dict(fm, **upd)) if not a.cancel else None
    if r is not None:
        upd["result_r"] = r
    md = set_fields(md, upd)
    if a.note:
        m = re.search(r"^## Exit & outcome[^\n]*\n", md, re.M)
        if m:
            md = md[:m.end()] + a.note.strip() + "\n" + md[m.end():]
    path.write_text(md, encoding="utf-8")
    res = "%+.2fR" % r if r is not None else upd["status"]
    _log("journal", "Trade %s — %s %s" % (upd["status"], fm.get("symbol"), fm.get("direction")),
         "Journal entry %s → %s." % (path.relative_to(ROOT), res))
    print("✅ %s %s" % (res, path.relative_to(ROOT)))
    sync_sheet(quiet=True)


def _fmt_r(r):
    return "%+.2fR" % r if r is not None else "—"


def cmd_list(a):
    for e in load_all():
        if a.open and e["status"] != "open":
            continue
        print("%-16s %-9s %-5s %-9s %7s  fomo %-3s %s" % (
            e.get("opened") or "?", e["symbol"], e["direction"], e["status"], _fmt_r(e.get("result_r")),
            _fmt_value(e.get("fomo")) or "-", " ".join(e["flags"])))


def _group(trades, keyf):
    out = {}
    for t in trades:
        for k in keyf(t):
            out.setdefault(k, []).append(t["result_r"])
    return out


def cmd_stats(a):
    entries = load_all()
    if a.days:
        cutoff = (now_sgt() - dt.timedelta(days=a.days)).strftime(TIME_FMT)
        entries = [e for e in entries if (e.get("opened") or "") >= cutoff]
    done = [e for e in entries if e["status"] == "closed" and e.get("result_r") is not None]
    print("Trades: %d logged · %d closed · %d open" % (len(entries), len(done),
                                                        sum(e["status"] == "open" for e in entries)))
    if not done:
        return
    rs = [e["result_r"] for e in done]
    wins = sum(r > 0 for r in rs)
    print("Win rate %.0f%% · total %+.2fR · expectancy %+.2fR/trade" % (100 * wins / len(rs), sum(rs), sum(rs) / len(rs)))

    def show(title, groups):
        print("\n" + title)
        for k, v in sorted(groups.items(), key=lambda kv: sum(kv[1])):
            print("  %-22s n=%-3d total %+6.2fR  avg %+.2fR  win %3.0f%%" % (
                k, len(v), sum(v), sum(v) / len(v), 100 * sum(r > 0 for r in v) / len(v)))

    def fomo_bucket(e):
        f = e.get("fomo")
        return ["unrated"] if f is None else ["0-1 low"] if f <= 1 else ["2 some"] if f < HIGH_FOMO else ["3+ high"]

    show("By FOMO", _group(done, fomo_bucket))
    show("By planned (self-reported)", _group(done, lambda e: [str(e.get("planned") or "unrated")]))
    show("By wiki plan evidence", _group(done, lambda e: ["in wiki plan" if e["plan_evidence"] else "not in wiki"]))
    show("By emotion before", _group(done, lambda e: e["emotion_before"] or ["unrated"]))
    show("Behaviour flags", _group(done, lambda e: e["flags"] or ["clean"]))
    show("Mistakes", _group([e for e in done if e["mistakes"]], lambda e: e["mistakes"]))


def main():
    ap = argparse.ArgumentParser(description="Trade journal (wiki/notes/journal/)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="log a new trade")
    n.add_argument("symbol")
    n.add_argument("direction", choices=["long", "short"])
    n.add_argument("--entry", type=float)
    n.add_argument("--stop", type=float)
    n.add_argument("--target", type=float)
    n.add_argument("--size", type=float)
    n.add_argument("--risk", type=float, help="risk %% of account")
    n.add_argument("--tf")
    n.add_argument("--setup")
    n.add_argument("--source", choices=SOURCES)
    n.add_argument("--planned", choices=["yes", "no"])
    n.add_argument("--fomo", type=int, choices=range(0, 6))
    n.add_argument("--confidence", type=int, choices=range(1, 6))
    n.add_argument("--emotion", help="comma list: " + ", ".join(EMOTIONS))
    n.add_argument("--rules", choices=["yes", "partial", "no"])
    n.add_argument("--why")
    n.add_argument("--feel")
    n.add_argument("--checks", help="FOMO checklist items ticked, as 0-based indices: '0,1,3'")
    n.add_argument("--opened", help="'YYYY-MM-DD HH:MM' SGT, for backfilling (default: now)")
    n.add_argument("--no-prompt", action="store_true")
    n.set_defaults(fn=cmd_new)

    c = sub.add_parser("comment", help="add a timestamped comment to a trade")
    c.add_argument("ref", help="entry id/filename, or a symbol (latest open trade)")
    c.add_argument("text", nargs="+")
    c.add_argument("--at", help="'YYYY-MM-DD HH:MM' (default: now)")
    c.set_defaults(fn=cmd_comment)

    x = sub.add_parser("close", help="close (or cancel) a trade")
    x.add_argument("ref")
    x.add_argument("--exit", type=float)
    x.add_argument("--r", type=float, help="override result in R (e.g. after partials)")
    x.add_argument("--pnl", type=float)
    x.add_argument("--mistakes", help="comma list: " + ", ".join(MISTAKES))
    x.add_argument("--rules", choices=["yes", "partial", "no"])
    x.add_argument("--note", help="text for the Exit & outcome section")
    x.add_argument("--closed", help="'YYYY-MM-DD HH:MM' SGT (default: now)")
    x.add_argument("--cancel", action="store_true", help="planned trade that was never taken")
    x.set_defaults(fn=cmd_close)

    sy = sub.add_parser("sync", help="rewrite the Google Sheet Trade Journal tab from the journal files")
    sy.set_defaults(fn=cmd_sync)

    ls = sub.add_parser("list", help="list journal entries")
    ls.add_argument("--open", action="store_true")
    ls.set_defaults(fn=cmd_list)

    st = sub.add_parser("stats", help="win rate / R by FOMO, plan, emotion, flags")
    st.add_argument("--days", type=int)
    st.set_defaults(fn=cmd_stats)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
