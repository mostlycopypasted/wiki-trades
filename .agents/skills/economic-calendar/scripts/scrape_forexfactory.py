#!/usr/bin/env python3
"""
Forex Factory calendar scrape via ego-browser (a real Chromium that passes Cloudflare).

The XML feed at nfs.faireconomy.media carries no Actual values and has no next-week file, while the
website has both. forexfactory.com blocks plain HTTP clients with a 403, so this loads the This / Next / Last
Week pages in ego-browser and reads the calendar table, impact folder colour included.

Writes dashboard/cache/ff_calendar.json (gitignored), which dashboard/wiki_data.py reads in preference to
the XML feed. Page times are already SGT because the browser runs in Asia/Singapore.

    python3 scripts/scrape_forexfactory.py            # this, next and last week
    python3 scripts/scrape_forexfactory.py this       # one week only
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "dashboard" / "cache" / "ff_calendar.json"
WEEKS = ["this", "next", "last"]
TIMEOUT = 240

JS = r"""
const weeks = __WEEKS__;
const task = await taskSpace("ff calendar scrape");
const page = task.page("p1");
const result = {};
for (const w of weeks) {
  await page.goto("https://www.forexfactory.com/calendar?week=" + w);
  const ok = await page.waitForFunction(() => document.querySelectorAll("tr.calendar__row").length > 3, undefined, { timeout: 30000 }).then(() => true).catch(() => false);
  if (!ok) { result[w] = { error: "calendar table did not load: " + await page.title() }; continue; }
  // event rows only get their data-event-id as they scroll into view, so walk down the page in steps
  await page.evaluate(async () => {
    const count = () => document.querySelectorAll("tr.calendar__row[data-event-id]").length;
    let stable = 0, last = -1;
    for (let i = 0; i < 60 && stable < 3; i++) {
      window.scrollBy(0, Math.floor(window.innerHeight * 0.8));
      await new Promise(r => setTimeout(r, 350));
      const atBottom = window.scrollY + window.innerHeight >= document.body.scrollHeight - 2;
      const n = count();
      stable = atBottom && n === last ? stable + 1 : 0;
      last = n;
    }
    window.scrollTo(0, 0);
  });
  result[w] = await page.evaluate(() => {
    const impactOf = el => {
      const c = (el.querySelector("td.calendar__impact span.icon") || {}).className || "";
      return c.includes("impact-red") ? "High" : c.includes("impact-ora") ? "Medium" : c.includes("impact-yel") ? "Low" : c.includes("impact-gra") ? "Holiday" : "";
    };
    const txt = (tr, k) => ((tr.querySelector("td.calendar__" + k) || {}).innerText || "").trim();
    let day = "", time = "";
    const events = [];
    for (const tr of document.querySelectorAll("tr.calendar__row")) {
      if (tr.classList.contains("calendar__row--day-breaker")) { day = tr.innerText.replace(/\s+/g, " ").trim(); time = ""; continue; }
      const id = tr.getAttribute("data-event-id");
      if (!id) continue;
      const t = txt(tr, "time");
      if (t) time = t;           // later events in the same slot leave the time cell blank
      events.push({ id, day, time, ccy: txt(tr, "currency"), impact: impactOf(tr), event: txt(tr, "event"),
                    actual: txt(tr, "actual"), forecast: txt(tr, "forecast"), previous: txt(tr, "previous") });
    }
    return { events };
  });
}
await task.finish({ keep: [] });
console.log("FFJSON:" + JSON.stringify(result));
"""

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def parse_day(label, today):
    """'Mon Oct 19' -> date, picking the year nearest today (weeks can straddle New Year)."""
    parts = label.split()
    if len(parts) < 3 or parts[1] not in MONTHS:
        return None
    best = None
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            d = dt.date(y, MONTHS[parts[1]], int(parts[2]))
        except ValueError:
            continue
        if best is None or abs((d - today).days) < abs((best - today).days):
            best = d
    return best


def parse_time(s):
    try:
        return dt.datetime.strptime(s.strip().lower(), "%I:%M%p").strftime("%H:%M")
    except ValueError:
        return None   # "All Day", "Tentative", "Day 2"


def scrape(weeks):
    p = subprocess.run(["ego-browser", "nodejs"], input=JS.replace("__WEEKS__", json.dumps(weeks)),
                       capture_output=True, text=True, timeout=TIMEOUT)
    # ego-browser's console.log lands on stderr, so look in both streams
    line = next((l for l in (p.stdout + "\n" + p.stderr).splitlines() if l.startswith("FFJSON:")), None)
    if not line:
        raise RuntimeError("no result from ego-browser: %s" % (p.stderr.strip() or p.stdout.strip())[-400:])
    return json.loads(line[len("FFJSON:"):])


def quit_if_idle():
    """Quit ego lite when no task space is open, so a scheduled run doesn't leave it idling in memory.

    Another session's spaces (equity-news-finder etc.) keep it running; an empty list means it is safe.
    """
    try:
        p = subprocess.run(["ego-browser", "nodejs", "-e", 'console.log("SPACES:" + JSON.stringify(await listTaskSpaces()))'],
                           capture_output=True, text=True, timeout=60)
        line = next((l for l in (p.stdout + "\n" + p.stderr).splitlines() if l.startswith("SPACES:")), None)
        if line is not None and json.loads(line[len("SPACES:"):]) == []:
            subprocess.run(["osascript", "-e", 'tell application "ego lite" to quit'], capture_output=True, timeout=30)
    except Exception as e:   # best effort only
        print("quit_if_idle skipped:", e, file=sys.stderr)


def main():
    weeks = [w for w in sys.argv[1:] if w in WEEKS] or WEEKS
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    try:
        raw = scrape(weeks)
    finally:
        quit_if_idle()
    # keep the previous copy of any week that failed or came back empty (next week is empty until published)
    try:
        old = json.loads(OUT.read_text(encoding="utf-8")).get("weeks", {})
    except (OSError, ValueError):
        old = {}
    out_weeks, problems = dict(old), []
    for w, data in raw.items():
        if data.get("error"):
            problems.append("%s: %s" % (w, data["error"]))
            continue
        events = []
        for e in data["events"]:
            d, t = parse_day(e["day"], today), parse_time(e["time"])
            if not d or not t or e["impact"] not in ("High", "Medium", "Low"):
                continue
            events.append({"id": e["id"], "date": str(d), "time": t, "ccy": e["ccy"], "impact": e["impact"],
                           "event": e["event"], "actual": e["actual"], "forecast": e["forecast"], "previous": e["previous"]})
        if events or w not in old:
            out_weeks[w] = events
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"fetchedAt": dt.datetime.now().timestamp(), "weeks": out_weeks}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT)
    print("ff_calendar.json:", {w: len(v) for w, v in out_weeks.items()})
    if problems:
        print("problems:", "; ".join(problems), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
