"""
Economic Calendar — Actual Auto-Refresh.

Runs frequently (every 1-2 min, via launchd) and does one thing: for any
Red Folder event in wiki/notes/economic-calendar.md whose scheduled time has
passed by >= 3 minutes and whose Actual cell is still blank, re-fetch that
one event's Actual value and patch just that row in place. It never rewrites
the whole note (that's pull_economic_calendar.py's job, run weekly).

State: a rolling timetable of upcoming/recent events is kept in
actual_watch_state.json next to this script, rebuilt from the note's tables
on every run (so the weekly full-pull and this refresher never fight over
truth — the note is always the source, the state file just remembers what's
already been checked and how many times).

Mechanical only — no LLM narrative, no index/hot-cache rewrite. Only a log
line when something actually changes.
"""
import os
import re
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

script_dir = os.path.dirname(os.path.abspath(__file__))
wiki_root = os.path.abspath(os.path.join(script_dir, "..", "..", "..", ".."))
note_path = os.path.join(wiki_root, "wiki", "notes", "economic-calendar.md")
state_path = os.path.join(script_dir, "actual_watch_state.json")

GRACE_MINUTES = 3          # don't check until this long after the scheduled time
MAX_ATTEMPTS = 20          # give up after this many due-checks (~40min at a 2-min cadence) —
                            # bounds how hard we hammer Forex Factory's feed for an event
                            # whose Actual never shows up (delayed release, feed gap, etc.)
PRUNE_AFTER_DAYS = 10       # drop state entries this many days stale (not in current note)

ROW_RE = re.compile(
    r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\d{2}:\d{2})\s*\|\s*([A-Z]+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$"
)

HEADERS = ("Date", "Time (SGT)", "Currency", "Event", "Forecast", "Previous", "Actual", "Detail")


def load_state():
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"events": {}}


def save_state(state):
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def parse_rows(content):
    """Return list of dicts for every data row in This Week / Next Week tables."""
    rows = []
    for line in content.splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        date, time_, curr, event, forecast, previous, actual, detail = m.groups()
        if date == "Date" or "---" in date:
            continue
        rows.append({
            "date": date, "time": time_, "currency": curr, "event": event,
            "forecast": forecast, "previous": previous, "actual": actual,
            "detail": detail, "line": line.rstrip("\n"),
        })
    return rows


def event_key(row):
    return f"{row['date']}|{row['time']}|{row['currency']}|{row['event']}"


def is_watchable(row):
    """Skip speeches/press-conferences/minutes — no quantifiable Actual ever posts."""
    return bool(row["forecast"].strip()) or bool(row["previous"].strip())


def actual_is_blank(val):
    return val.strip() in ("", "—", "-")


FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
TV_URL = "https://economic-calendar.tradingview.com/events?from={start}&to={end}"
UA = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


def fetch_ff_actuals():
    """date|currency|title (lowercased) -> actual string, from the FF thisweek feed."""
    out = {}
    try:
        req = urllib.request.Request(FF_URL, headers=UA)
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        for ev in root.findall("event"):
            impact = ev.find("impact").text
            if impact != "High":
                continue
            title = ev.find("title").text or ""
            country = ev.find("country").text or ""
            date_val = ev.find("date").text
            time_val = ev.find("time").text
            actual_el = ev.find("actual")
            actual = actual_el.text if actual_el is not None and actual_el.text else ""
            try:
                dt_sgt = datetime.strptime(f"{date_val} {time_val}", "%m-%d-%Y %I:%M%p") + timedelta(hours=8)
                date_sgt = dt_sgt.strftime("%Y-%m-%d")
            except Exception:
                continue
            out[(date_sgt, country, title.strip().lower())] = actual
    except Exception as e:
        print(f"Warning: FF actual fetch failed: {e}")
    return out


def fetch_tv_actuals(date_str):
    """Fallback for a single date outside the FF thisweek window."""
    out = {}
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d")
        start_utc = (day - timedelta(hours=8)).strftime("%Y-%m-%dT00:00:00.000Z")
        end_utc = (day - timedelta(hours=8) + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00.000Z")
        req = urllib.request.Request(TV_URL.format(start=start_utc, end=end_utc), headers={**UA, "Origin": "https://www.tradingview.com"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8")).get("result", [])
        for ev in data:
            dt_utc = datetime.strptime(ev["date"], "%Y-%m-%dT%H:%M:%S.000Z")
            dt_sgt = dt_utc + timedelta(hours=8)
            actual = ev.get("actual")
            out[(dt_sgt.strftime("%Y-%m-%d"), ev.get("currency", ""), str(ev.get("title", "")).strip().lower())] = (
                "" if actual is None else str(actual)
            )
    except Exception as e:
        print(f"Warning: TradingView actual fetch failed for {date_str}: {e}")
    return out


def main():
    if not os.path.exists(note_path):
        return
    with open(note_path, "r", encoding="utf-8") as f:
        content = f.read()

    rows = parse_rows(content)
    now = datetime.now()
    state = load_state()
    events = state["events"]

    seen_keys = set()
    due = []
    for row in rows:
        key = event_key(row)
        seen_keys.add(key)
        if not is_watchable(row):
            events.pop(key, None)
            continue
        if not actual_is_blank(row["actual"]):
            events.pop(key, None)  # already filled (e.g. by pull_economic_calendar.py's own fetch) — nothing to watch
            continue
        due_at = datetime.strptime(f"{row['date']} {row['time']}", "%Y-%m-%d %H:%M") + timedelta(minutes=GRACE_MINUTES)
        entry = events.get(key, {"attempts": 0, "status": "pending"})
        entry.update({"date": row["date"], "time": row["time"], "currency": row["currency"],
                       "event": row["event"], "due_at": due_at.isoformat()})
        events[key] = entry
        if entry["status"] == "pending" and now >= due_at and entry["attempts"] < MAX_ATTEMPTS:
            due.append((key, row, due_at))

    # prune stale state no longer present in the note
    cutoff = now - timedelta(days=PRUNE_AFTER_DAYS)
    for key in list(events.keys()):
        if key not in seen_keys:
            try:
                d = datetime.strptime(events[key]["date"], "%Y-%m-%d")
            except Exception:
                d = now
            if d < cutoff:
                events.pop(key, None)

    if not due:
        save_state(state)
        return

    ff_actuals = fetch_ff_actuals()
    tv_cache = {}
    patched = []
    gave_up = []

    new_content = content
    for key, row, due_at in due:
        entry = events[key]
        lookup_key = (row["date"], row["currency"], row["event"].strip().lower())
        actual = ff_actuals.get(lookup_key, "")
        if not actual:
            if row["date"] not in tv_cache:
                tv_cache[row["date"]] = fetch_tv_actuals(row["date"])
            actual = tv_cache[row["date"]].get(lookup_key, "")

        entry["attempts"] += 1
        entry["last_checked"] = now.isoformat()

        if actual:
            new_line = (
                f"| {row['date']} | {row['time']} | {row['currency']} | {row['event']} | "
                f"{row['forecast']} | {row['previous']} | {actual} | {row['detail']} |"
            )
            if row["line"] in new_content:
                new_content = new_content.replace(row["line"], new_line, 1)
                entry["status"] = "filled"
                patched.append(f"{row['currency']} {row['event']} ({row['date']} {row['time']} SGT) -> {actual}")
            else:
                print(f"Warning: could not locate row to patch for {key} (note changed underneath?)")
        elif entry["attempts"] >= MAX_ATTEMPTS:
            entry["status"] = "gave_up"
            gave_up.append(f"{row['currency']} {row['event']} ({row['date']} {row['time']} SGT)")

    if patched:
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        import subprocess
        subprocess.run([
            "python3", "/Users/chriseah/.gemini/skills/llm-wiki-manager/scripts/append_log.py",
            "--path", wiki_root,
            "--action", "note",
            "--title", "Economic Calendar",
            "--details", "Actual auto-refresh: " + "; ".join(patched),
        ], cwd=wiki_root)
        print("Patched: " + "; ".join(patched))

    if gave_up:
        print("Gave up waiting for Actual (no release detected within window): " + "; ".join(gave_up))

    save_state(state)


if __name__ == "__main__":
    main()
