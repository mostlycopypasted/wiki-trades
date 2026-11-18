#!/usr/bin/env python3
"""
Central Bank Statement Due-Check — trigger for the Central Bank Tally Rule.

Reads the Red Folder rows of wiki/notes/economic-calendar.md (times are SGT),
finds each central bank's policy-statement event, and reports which ones are
DUE: release time + 10 minutes has passed, not yet ingested, still inside the
catch-up window, and not already being worked on. It is mechanical only — the
ingest itself (fetch, source page, quote check, tally update) is done by the
"Central Bank Statement Ingest" Orca automation, whose --precheck is this
script's default mode.

Modes:
  (default)            precheck: exit 0 and record a dispatch if anything is due,
                       exit 1 otherwise (Orca records a skipped run).
  --list-due           print the due items as JSON (no state change).
  --pending            print items dispatched in the last 60 min and not yet marked
                       done/failed (what the ingest agent should work on after precheck).
  --mark-done BANK [DATE]   mark an item ingested (DATE defaults to the due item's date).
  --mark-failed BANK [DATE] give up on an item (e.g. statement never published).
  --not-published BANK [DATE]  statement not on the official site yet: release the item so the
                       next slot (15 min later) retries it. Retries are capped by MAX_ATTEMPTS
                       (3 dispatches = the first try + 2 retries); after the last one the agent
                       should --mark-failed and log it.
  --status             print every tracked item and its state.
Flags: --now "YYYY-MM-DD HH:MM" (SGT, for testing), --dry-run (no state writes).

State: scripts/cb_statement_state.json  { "YYYY-MM-DD:BANK": {...} }
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

here = os.path.dirname(os.path.abspath(__file__))
wiki_root = os.path.abspath(os.path.join(here, ".."))
note_path = os.path.join(wiki_root, "wiki", "notes", "economic-calendar.md")
state_path = os.path.join(here, "cb_statement_state.json")

DELAY_MIN = 10            # run this long after the scheduled release
CATCHUP_HOURS = 6         # ignore events older than this (first-run / long outage guard)
REDISPATCH_MIN = 40       # don't re-dispatch an item sooner than this (agent may still be working)
MAX_ATTEMPTS = 3          # first try + 2 retries (15 min apart, via --not-published) without a --mark-done

# currency -> bank, and the Forex Factory event names that are the *statement* itself
BANK_BY_CCY = {"USD": "Fed", "EUR": "ECB", "GBP": "BoE", "JPY": "BoJ",
               "AUD": "RBA", "NZD": "RBNZ", "CHF": "SNB", "CAD": "BoC"}
STATEMENT_RE = re.compile(
    r"(FOMC Statement|Rate Statement|Monetary Policy Statement|Monetary Policy Summary|"
    r"Monetary Policy Assessment|Monetary Policy Meeting Statement|Policy Rate)", re.I)
EXCLUDE_RE = re.compile(r"(Minutes|Press Conference|Speaks|Speech|Meeting Minutes|Summary of Opinions)", re.I)

ROW_RE = re.compile(
    r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\d{2}:\d{2})\s*\|\s*([A-Z]+)\s*\|\s*(.*?)\s*\|")


def load_state():
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def statement_events():
    """Earliest statement event per (bank, date) from the calendar note."""
    found = {}
    try:
        lines = open(note_path, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        return found
    for ln in lines:
        m = ROW_RE.match(ln)
        if not m:
            continue
        date, time, ccy, name = m.groups()
        bank = BANK_BY_CCY.get(ccy)
        if not bank or EXCLUDE_RE.search(name) or not STATEMENT_RE.search(name):
            continue
        # "Policy Rate" rows (rate figure) are only a fallback when no statement row exists
        key = "%s:%s" % (date, bank)
        when = datetime.strptime("%s %s" % (date, time), "%Y-%m-%d %H:%M")
        weak = bool(re.search(r"Policy Rate", name, re.I)) and not re.search(r"Statement|Summary|Assessment", name, re.I)
        cur = found.get(key)
        if cur is None or (cur["weak"] and not weak) or (weak == cur["weak"] and when < cur["release"]):
            found[key] = {"bank": bank, "date": date, "event": name, "release": when, "weak": weak}
    return found


def due_items(state, now):
    out = []
    for key, ev in statement_events().items():
        trigger = ev["release"] + timedelta(minutes=DELAY_MIN)
        st = state.get(key, {})
        if st.get("done") or st.get("failed"):
            continue
        if now < trigger:
            continue
        if now > trigger + timedelta(hours=CATCHUP_HOURS):
            continue
        if st.get("attempts", 0) >= MAX_ATTEMPTS:
            continue
        last = st.get("last_dispatch")
        if last and now - datetime.strptime(last, "%Y-%m-%d %H:%M") < timedelta(minutes=REDISPATCH_MIN):
            continue
        out.append({"key": key, "bank": ev["bank"], "date": ev["date"], "event": ev["event"],
                    "release_sgt": ev["release"].strftime("%Y-%m-%d %H:%M"),
                    "attempts": st.get("attempts", 0)})
    return sorted(out, key=lambda x: x["release_sgt"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-due", action="store_true")
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--mark-done", nargs="+", metavar=("BANK", "DATE"))
    ap.add_argument("--mark-failed", nargs="+", metavar=("BANK", "DATE"))
    ap.add_argument("--not-published", nargs="+", metavar=("BANK", "DATE"))
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--now")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    now = datetime.strptime(a.now, "%Y-%m-%d %H:%M") if a.now else datetime.now()  # machine clock is SGT
    state = load_state()

    if a.status:
        evs = statement_events()
        for key in sorted(evs):
            ev = evs[key]
            print("%s  %s  release %s  %s" % (key, ev["event"], ev["release"].strftime("%H:%M"), json.dumps(state.get(key, {}))))
        return 0

    for flag, field in ((a.mark_done, "done"), (a.mark_failed, "failed"), (a.not_published, "waiting")):
        if flag:
            bank = flag[0]
            date = flag[1] if len(flag) > 1 else None
            keys = [k for k in statement_events() if k.endswith(":" + bank) and (date is None or k.startswith(date))]
            if date is None:   # default: most recent dispatched item for that bank
                keys = [k for k in keys if k in state] or keys
                keys = sorted(keys)[-1:]
            if not keys:
                print("no matching item for %s %s" % (bank, date or ""), file=sys.stderr)
                return 2
            for k in keys:
                if field == "waiting":   # release the cooldown so the next slot retries; attempts stay counted
                    state.setdefault(k, {}).pop("last_dispatch", None)
                    print("released %s for retry (attempts so far: %d of %d)" % (k, state[k].get("attempts", 0), MAX_ATTEMPTS))
                else:
                    state.setdefault(k, {})[field] = now.strftime("%Y-%m-%d %H:%M")
                    print("marked %s %s" % (k, field))
            if not a.dry_run:
                save_state(state)
            return 0

    if a.pending:
        out = []
        for key, ev in statement_events().items():
            st = state.get(key, {})
            last = st.get("last_dispatch")
            if st.get("done") or st.get("failed") or not last:
                continue
            if now - datetime.strptime(last, "%Y-%m-%d %H:%M") > timedelta(minutes=60):
                continue
            out.append({"key": key, "bank": ev["bank"], "date": ev["date"], "event": ev["event"],
                        "release_sgt": ev["release"].strftime("%Y-%m-%d %H:%M"), "attempts": st.get("attempts", 0)})
        print(json.dumps(sorted(out, key=lambda x: x["release_sgt"]), indent=2))
        return 0

    items = due_items(state, now)
    if a.list_due:
        print(json.dumps(items, indent=2))
        return 0

    # precheck mode
    if not items:
        print("no central bank statement due")
        return 1
    for it in items:
        s = state.setdefault(it["key"], {})
        s["attempts"] = s.get("attempts", 0) + 1
        s["last_dispatch"] = now.strftime("%Y-%m-%d %H:%M")
    if not a.dry_run:
        save_state(state)
    print("due: " + ", ".join("%s (%s SGT)" % (i["bank"], i["release_sgt"]) for i in items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
