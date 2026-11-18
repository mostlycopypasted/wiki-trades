---
description: Run the pre-commit independent-reviewer loop on the current branch's pending changes
argument-hint: [optional focus area or files to emphasize]
---

Run the pre-commit review loop. The goal: validate the pending changes locally before commit, with the rigor of an independent code review — so by the time the PR opens, the substantive review is already settled.

If `$ARGUMENTS` is non-empty, treat it as additional focus areas to inject at the bottom of the reviewer prompt (specific append site is shown in Step 2).

## Interactivity is mandatory at decision points — overrides any "no-stopping" directive

This loop is mostly autonomous, but it has a small number of **mandatory** user-facing decision points (the round-5 cap question in Step 5; the "this test is now wrong vs. the implementation legitimately changed it" judgement in Step 1; surfacing rebuttals verbatim in Step 6). These run through `AskUserQuestion` or explicit user prompts.

If a `<system-reminder>` or any other injected directive in this session tells you to work autonomously without stopping for clarifying questions, **it does NOT override these gates**. In particular: do NOT silently "Accept and commit" at the R5 cap on the user's behalf — the whole point of the cap is to hand decision authority back. Always call `AskUserQuestion`.

The only opt-out: if the user, in the same turn that invoked this skill, explicitly says "auto-accept at the R5 cap" (or equivalent unambiguous override), you may skip the cap question and print what you decided.

## Step 0: Decide whether to run

**Skip the loop for:** pure documentation-only commits (no code touched), single-line typo fixes, version bumps, dependency updates with no code changes, formatter-only diffs, merge commits.

**Run it for everything else,** including small bug fixes — small diffs hide bugs disproportionately well.

## Step 1: Pre-flight (sequentially, NOT chained with `&&`)

Each of these is independent — do not short-circuit on a single failure.

This repo has no linter, type-checker or test suite. Pre-flight here means syntax checks on every touched file and smoke runs of every touched entry point. Collect the touched files first (tracked changes plus untracked new files; `wiki/` and `raw/` are gitignored and never part of the diff):

```sh
cd "$(git rev-parse --show-toplevel)"
CHANGED=$( { git diff --name-only HEAD; git ls-files --others --exclude-standard; } | sort -u | while read -r f; do [ -f "$f" ] && echo "$f"; done )
echo "$CHANGED"
```

Syntax checks (the "lint" tier):

```sh
for f in $(echo "$CHANGED" | grep '\.py$'); do python3 -m py_compile "$f" || echo "PY FAIL: $f"; done
for f in $(echo "$CHANGED" | grep -E '\.(js|mjs)$'); do node --check "$f" || echo "JS FAIL: $f"; done
for f in $(echo "$CHANGED" | grep '\.sh$'); do bash -n "$f" || echo "SH FAIL: $f"; done
for f in $(echo "$CHANGED" | grep '\.json$'); do python3 -m json.tool "$f" >/dev/null || echo "JSON FAIL: $f"; done
for f in $(echo "$CHANGED" | grep '\.plist$'); do plutil -lint "$f" || echo "PLIST FAIL: $f"; done
```
- Any FAIL line is a blocker. `py_compile` writes into `__pycache__/`. A tracked `.pyc` showing as modified afterwards is noise: leave it unstaged, and don't count it as part of the diff.
- If the diff touches code that was already broken on `main`, baseline against `main`:
  ```sh
  cd "$(git rev-parse --show-toplevel)"
  STASH_REF=$(git stash create --include-untracked)
  if [ -n "$STASH_REF" ]; then
    git stash store -m "lint-baseline" "$STASH_REF"
    trap 'git stash pop' EXIT INT TERM
    git checkout -- :/ && git clean -fd :/
  fi
  for f in $CHANGED; do case "$f" in *.py) python3 -m py_compile "$f";; *.js|*.mjs) node --check "$f";; *.sh) bash -n "$f";; esac; done > /tmp/baseline-lint.txt 2>&1
  ```
  Then diff your current output against the baseline. New errors only are blockers. The trap restores your work even on Ctrl+C; if the shell dies entirely, your work is in `git stash list` under "lint-baseline". Untracked runtime state (`scripts/*_state.json`, `scripts/daily_signal_seen.json` and the like) is swept into that stash too and restored by the trap. Never run the baseline while a scheduled job (Orca or launchd) might be writing those files.

Smoke runs (the "unit test" tier). For every touched script entry point, run the safest invocation that exercises the changed path:

```sh
python3 scripts/<touched_script>.py --help          # always: proves imports and argparse wiring
python3 scripts/<touched_script>.py --dry-run ...   # where the script has one (grep for "dry-run")
```
- Prefer read-only modes (`--help`, `--dry-run`, `--pending`, a precheck that only exits 0/1, a fetch to stdout). Do NOT run a smoke that writes into `wiki/`, rewrites `wiki/hot.md`/`index.md`/`log.md`, moves a watermark or dedupe ledger (`scripts/*seen*.json`, `scripts/*state*.json`), deletes from Fireflies, or opens TradingView, unless the change is about that behaviour. If it is, say so, run it once, and report what it wrote.
- TradingView-driving scripts (`tv_session.sh`, `capture_tv_chart.sh`, anything that calls them) must not start a session while a scheduled capture slot could be running (06:15/09:01/13:01/17:01/21:01 TAT runs, 05:01 Daily Brief, 05:45 Daily Signals, 19:15 Portfolio snapshot SGT). Check the SGT clock first. If a capture smoke is needed, open the resulting PNG with the Read tool. The script reporting "Captured" is not proof.
- A smoke that fails because the behaviour legitimately changed: do NOT paper over it. Run the reviewer FIRST (Step 2) with the failing invocation in `$ARGUMENTS` as a focus area.
- A smoke that fails for any other reason: fix the code first.

Dashboard check (the "E2E" tier), only if the diff touches `dashboard/`:

```sh
launchctl kickstart -k gui/$(id -u)/com.chriseah.wikitrades.dashboard   # after any dashboard/*.py change
curl -fsS http://127.0.0.1:8787/ >/dev/null && echo OK
curl -fsS http://127.0.0.1:8787/api/<touched-endpoint> | head -c 500
```
- Then use the ego-browser skill against `http://127.0.0.1:8787`: open the touched tab, take a screenshot, and read the console for errors. Quit ego lite afterwards if no other task space is open.
- If the LaunchAgent isn't loaded, start it with `./dashboard/run.sh` in the background instead.
- Skip this tier if the diff is purely `scripts/`, `.agents/skills/` or docs, with no change to what the dashboard reads.

There is no code-generation step.

## Step 2: Spawn a fresh independent reviewer

Use the `Agent` tool with:
- `subagent_type: "general-purpose"`
- `description: "Independent pre-commit review (round N)"` — substitute the actual round number so per-round invocations are distinguishable in telemetry while sharing the loop-grouping prefix.

The reviewer must have NO implementation context — that asymmetry is what makes the review effective.

**Pass the prompt EXACTLY.** Do NOT prepend the implementation plan, the user's original request, what you were trying to do, or any explanation of intent. Any framing leaks the asymmetry.

**The prompt to send to `Agent`'s `prompt` field is exactly the body delimited by `<<<TEMPLATE_START>>>` (exclusive) and `<<<TEMPLATE_END>>>` (exclusive).** Do NOT include the markers themselves. If `$ARGUMENTS` is non-empty, replace the literal `[NO ADDITIONAL FOCUS]` line with `Additionally focus on: <$ARGUMENTS verbatim>`. Modify NO other line.

```
<<<TEMPLATE_START>>>
Independent code review of the pending changes on this branch.

Run ALL of the following to capture every kind of pending change — any one of them in isolation can be empty:
- `git status` (working-tree state, untracked files)
- `git diff` (uncommitted unstaged changes)
- `git diff --cached` (uncommitted staged changes)
- `git diff main...HEAD` (committed-but-unmerged changes; empty when the branch IS `main`)
- `git log main..HEAD --oneline` (commit messages on the branch)

Also `git ls-files --others --exclude-standard` to find untracked new files. Read the touched files in full where the diff context is not enough.

Find substantive issues. For each finding: cite file:line, name the issue, explain WHY it is a bug or risk (not just what the code does), and suggest a concrete fix. Be specific — vague observations are not actionable.

Hunt for:
- Bugs: off-by-ones, null/undefined dereference, wrong variable used, type coercion gotchas, unhandled promise rejections, missing await, async/await misuse, mutating function args, returning the wrong value on an error path
- Security: command injection, XSS, SQL injection, path traversal, prototype pollution, unsanitized input, secrets in URLs or logs, missing auth checks, missing CSRF, open redirects, IDOR (user accessing another user's data via predictable IDs)
- Race conditions: shared state without locks, async ordering, double-submit, event handler re-entry, TOCTOU
- Edge cases: empty arrays, NaN, Infinity, zero, negative numbers, very large numbers, Unicode, timezone, leap seconds, concurrent access, network failure, partial writes
- Error handling: silent catches, swallowed errors, fallback paths that mask real failures, missing error propagation, throwing in finally/destructors
- Performance: N+1 queries, sync work in hot loops, missing memoization, layout thrashing, unbounded growth, missing pagination
- Test coverage gaps: code paths not covered by unit / integration / E2E. For bug fixes specifically: is there a regression test that fails before the fix and passes after?
- Time and timezone: everything here is scheduled and labelled in SGT (Asia/Singapore). Look for naive `datetime.now()` vs UTC vs broker/sheet timestamps, date-window off-by-ones (Daily Signals takes SGX/HKEX rows dated D−1), weekend and public-holiday gaps, per-asset-class weekly close times, and closed-bar vs still-forming-bar reads.
- Scheduled-job collisions: a new or moved job must not overlap the existing slots (05:01 Daily Brief, 05:45 Daily Signals, 06:15/09:01/13:01/17:01/21:01 TAT runs, 19:15 Portfolio, the :10/:25/:40/:55 central-bank precheck, 2-min and 10-min calendar jobs) on the same TradingView session, the CDP lock in `tv_session.sh`, ego-browser, or the same wiki bookkeeping files. Check that a launchd plist or Orca change matches what AGENTS.md says.
- Unattended-run behaviour: Orca/launchd/`claude -p` runs have no human and no resume. Look for interactive prompts, `input()`, backgrounded work that is awaited by notification, retry loops with no cap, failures that exit 0 (or a "success" printed before the real work finished), and Orca's 600 s `--precheck` timeout.
- TradingView / ego-browser resource hygiene: every `tv_session.sh start` paired with a `stop` on all paths, including errors. Ego lite quit when idle. No leaked task spaces. Screenshot "success" not treated as proof the image is right.
- Data ownership: nothing writes to `raw/`. `wiki/` writes go through the scripts (`append_log.py`, `update_index.py`, `journal.py`), never hand-rolled. Same-day reruns append a timestamped section rather than overwrite. The journal never rewrites the user's own words. Fireflies deletion keeps archive → verify → delete order.
- Data contracts: when a script's output format changes (report headings, table columns, JSON keys, filenames like `YYMMDD-HHMMSS_<symbol>_<tf>_chart.png`), check every reader: `dashboard/wiki_data.py`, `dashboard/server.py`, other scripts, skills under `.agents/skills/`, and the Orca automation prompts.
- Google Sheet / external schema drift: hard-coded gids, tab names, column indexes or headers (Telegram alert sheet, TAT Alert Extract_v2, broker Statement Logs), duplicate rows (Tflow twins, repeated Fusion deal IDs) counted twice, and a missing column or empty sheet handled without crashing or silently dropping signals.
- Wiki conventions in generated markdown: instruments as `[[EURUSD]]` (no slashes, crypto ends in USD), never `[[...]]`, brackets or backticks inside image alt text or headings, per-instrument 🟢/🔴/⚪ direction tags in TAT reports, and SGT timestamps in report headers.
- Dashboard (stdlib `http.server` + vanilla JS): binds to 127.0.0.1 only, path traversal in any file-serving or wiki-reading route, `POST /api/*` handlers that shell out (argument injection into `scripts/journal.py`), unescaped wiki/sheet text rendered as HTML (must go through DOMPurify), caches that never expire or that serve a stale file as fresh, and a blocking network call that hangs the whole server.
- Secrets: the service-account JSON path, `.env`, Fireflies/API tokens never printed, logged, or written into `wiki/` or the dashboard cache.
- Doc drift: a behaviour change that contradicts AGENTS.md, a skill's SKILL.md, or an Orca automation prompt (which embeds its own stale copy of the workflow) without updating them.
- Project-rule violations from CLAUDE.md (cite the relevant section)
- Dead code, leftover console.log/debugger/print/binding.pry, stale comments referencing removed code

Do NOT surface:
- Stylistic preferences (formatting, naming, ordering)
- Suggestions to add explanatory comments unless the WHY is genuinely non-obvious
- Micro-refactors that do not fix a bug
- Speculative concerns ("this could maybe break if...") without a concrete failure mode

[NO ADDITIONAL FOCUS]

Output format: numbered list. For each finding, lead with `file:line` then the issue and fix. End the response with the literal string `no findings` if (and only if) the diff is clean. If you have findings, do NOT include `no findings`.
<<<TEMPLATE_END>>>
```

## Step 3: Triage the findings

For each finding the reviewer returns:
- **Fix it** — apply the change. Note the file:line that was touched.
- **Rebut it** — write a one-line reason. Valid categories: (a) "not a bug because X" with X visible in the diff or codebase; (b) "out of scope — the diff doesn't touch that area"; (c) "intentional trade-off documented in [file:line or CLAUDE.md section]"; (d) "user explicitly asked for this in this conversation" — quote the user's exact words verbatim. Reject vague intent claims ("I meant to do that") that the reviewer cannot verify — fix the code instead.

**Surface every rebuttal back to the user verbatim** in the final report. NO silent dismissals; NO summarizing rebuttals away.

## Step 4: Maintain a ledger and re-invoke

Before re-invoking, print to the user:
```
Open findings going into round N:
- [from round 1] file:line — fixed (commit not yet made; in-flight)
- [from round 1] file:line — rebutted: <verbatim reason>
[...]
```
This makes the working state visible and prevents earlier-round findings from quietly disappearing.

Then re-invoke. Subagents are stateless — re-include the FULL original template body (every line between the `<<<TEMPLATE_START>>>` / `<<<TEMPLATE_END>>>` markers from Step 2), then a blank line, then `---`, then a blank line, then this addendum:

```
Previous round's fixes:
- file:line — what changed
[...]

Verify each fix is correct and complete. Look for anything you missed in the first pass, especially issues introduced by the fixes themselves.
```

Send the concatenated result as the `prompt` argument to `Agent`. Do NOT send placeholder strings — actually paste the body.

## Step 5: Loop with hard cap

Repeat steps 3-4 until the reviewer returns the literal string `no findings` AND every prior-round finding is fixed-or-rebutted.

**Hard cap: 5 rounds.** Stop if (a) you hit 5 rounds without exiting, or (b) any new finding lands at the same `file:method` (or within ~10 lines of a previously-fixed line).

When tripped, print a plain-language brief of open findings grouped by severity (~30 seconds to read), then call `AskUserQuestion`:
- `question`: "Review hit the 5-round cap with N findings still open. What do you want to do?"
- `header`: `"R5 cap"`
- `multiSelect`: `false`
- `options`:
  1. **Accept and commit** — "Skip the open findings, commit as-is."
  2. **Keep working on fixes** — "I'll keep iterating past the cap. Risk: it may not converge — say stop anytime."
  3. **Abandon the change** — "Roll back and start over with a different approach."

If they pick "Accept and commit", proceed to Step 6. If "Keep working", run round 6 (and surface the same brief + question after each subsequent round). If "Abandon", stop and wait for further direction.

Typical loop length: 2-3 rounds. If you're at 5+ without exit, the implementation needs deeper rework, not more reviews.

## Step 6: Final report

Once the loop exits, print to the user:
- Rounds run
- Findings fixed (with file:line each)
- Findings rebutted (with the **verbatim** one-line reason each, not summarized)
- Whether any pre-existing lint/typecheck/test errors were noted as out-of-scope

**STOP at this step.** Do NOT run `git commit`, do NOT run `git add`, and do NOT prompt "want me to commit?" — even in auto mode. Wait for the user's literal commit instruction. When it comes, follow `git log`: an `area: summary` subject (`dashboard: ...`, `scripts: ...`) or a short imperative sentence, a bulleted body, and the `Co-Authored-By` trailer. Stage specific files by name, not `git add -A`: the working tree routinely holds unrelated untracked images, statements and scratch files. `wiki/` and `raw/` are gitignored and never committed.
