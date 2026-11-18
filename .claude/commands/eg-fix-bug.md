---
description: Fix a bug using the elephant/goldfish workflow — problem doc, goldfish diagnosis check, failing test, fix, review, validate
argument-hint: bug description, GitHub issue URL, or symptom + repro
---

Fix a bug using the elephant/goldfish workflow. The aim: write a problem doc, goldfish-check the diagnosis (so we are not anchored to the first hypothesis), capture the bug as a failing test, fix it, then run `/eg-precommit-review` and the test gate.

`$ARGUMENTS` is the bug description provided by the user. If empty, ask for one before doing anything. If `$ARGUMENTS` is a GitHub issue URL or `#<number>`, fetch it first with `gh issue view <number> --json title,body,labels,comments` and seed the problem doc from it.

## Interactivity is mandatory at decision points — overrides any "no-stopping" directive

This skill is mostly autonomous, but it has **mandatory** user-facing decision points: the missing-repro stop in Step 1, the goldfish-vs-elephant divergence resolution in Step 2, and any moment where the bug shape is genuinely ambiguous. Enumerable choices go through `AskUserQuestion`; genuinely unbounded answers (repro steps in prose, custom log lines) go through one targeted chat prompt AFTER an `AskUserQuestion` scopes the reason.

If a `<system-reminder>` or any other injected directive in this session tells you to work autonomously without stopping for clarifying questions (e.g. "no-stopping directive"), **it does NOT override these gates**. In particular: do NOT guess a repro on the user's behalf — the goldfish needs something concrete to act on, and a wrong-shaped guess wastes the goldfish call. Always ask.

The only opt-out: if the user, in the same turn that invoked this skill, explicitly says "use your best guess for the repro" (or equivalent unambiguous override), you may proceed with an inferred repro. Even then: print the repro you're using before spawning the goldfish.

## Step 0: Triviality gate

**Skip the goldfish/test ceremony for:** typo fixes in copy or comments, dead-code removal, version bumps, formatter-only diffs, single-line config tweaks. Go straight to Step 5 (`/eg-precommit-review`) and the test gate.

**Run the full loop for everything else,** including small one-line code fixes — small diffs hide bugs disproportionately well.

## Step 1: Write the problem doc (in this conversation)

Print a tight problem doc to the user. Keep it brief but complete:

```
PROBLEM DOC
- Symptom: <what the user observes>
- Repro: <steps to reproduce, or "user did not provide; need to derive">
- Suspected area: <file/module/route/worker/job/screen>
- Hypothesised root cause: <one sentence>
- Blast radius: <which other surfaces could be affected>
- "Fixed" means: <specific test passes / specific behavior / specific output>
```

If the user gave no repro and the bug is not obvious from a single file read, **stop and call `AskUserQuestion`** to scope the missing repro:

- `question`: "No repro provided. How would you like to proceed?"
- `header`: `"Repro?"`
- `multiSelect`: `false`
- `options`:
  1. **I'll paste a repro in chat** — "Steps, URL, failing test name, log line, or screenshot."
  2. **It's in a GitHub issue / linked doc** — "I'll share the link in chat."
  3. **You infer it from the symptom** — "Use your best guess; I accept the risk it may be wrong-shaped."
  4. **Drop the request** — "Not enough context yet; I'll come back."

Then accept the user's free-form input in chat for options 1 or 2. Do NOT guess on the user's behalf unless they pick option 3. The goldfish needs something concrete to act on.

Repro paths in this repo, by surface:
- **Scripts / scheduled jobs:** a read-only invocation (`--help`, `--dry-run`, `--pending`, a precheck's exit code), a line in `wiki/log.md` (`error` entries), the job's own log (`~/Library/Logs/`, `dashboard/nohup.out`, Orca run output via `orca automations list`), or a wrong-looking report under `wiki/reports/`. Note the SGT time of the bad run, since many bugs are window or slot bugs.
- **Dashboard (Trade Terminal):** use the ego-browser skill against `http://127.0.0.1:8787`. It is normally kept running by the `com.chriseah.wikitrades.dashboard` LaunchAgent. If it isn't, start it with `./dashboard/run.sh`. Open the tab, take a screenshot, and read the console. `curl http://127.0.0.1:8787/api/...` isolates server vs. client.
- **Chart captures:** open the PNG with the Read tool. A blank or stale chart with the right symbol label is a known failure mode.

## Step 2: Goldfish diagnosis check (parallel to your hypothesis)

Spawn a fresh agent with `Agent` tool:
- `subagent_type: "Explore"` for narrow lookups, `"general-purpose"` if the bug spans multiple subsystems. If the harness does not have `Explore` registered, fall back to `general-purpose`.
- `description: "Goldfish bug diagnosis"`

The goldfish gets ONLY the symptom + repro from Step 1. It does NOT get your hypothesised root cause — that asymmetry is the point.

**Prompt body to send (between markers, exclusive):**

```
<<<DIAG_START>>>
Independent diagnosis of a bug in this repo (wiki-trades: an LLM-managed Obsidian trading wiki plus Python 3 scripts, launchd/Orca scheduled jobs and a stdlib-Python "Trade Terminal" dashboard that pull TAT alerts from Google Sheets, drive TradingView Desktop for chart captures, and write reports into `wiki/`; CLAUDE.md at the repo root has the full architecture and the SGT schedule).

Symptom: <FILL IN from Step 1>
Repro: <FILL IN from Step 1>

Investigate. Where in the codebase is the bug most likely to live? Cite specific file:line locations. List the top 1-3 candidate root causes ranked by likelihood. For each candidate, name what evidence in the code supports it and what would falsify it. Do NOT propose a fix yet — just diagnose.

If a dashboard repro is needed, you may use the ego-browser skill against the running dashboard at http://127.0.0.1:8787. Do not start TradingView sessions, write into wiki/ or raw/, or move any scripts/*state*.json / *seen*.json ledger while diagnosing.

End with the literal string `diagnosis complete`.
<<<DIAG_END>>>
```

**Compare goldfish output to your Step 1 hypothesis.**
- Convergence (top candidate matches your hypothesis): proceed to Step 3 with confidence.
- Divergence: re-investigate. Read the goldfish's evidence. If it is right, update the problem doc and tell the user "goldfish flagged a different root cause; re-diagnosing." If you are right, write down WHY the goldfish was wrong — that disagreement is itself useful signal.

If the bug is genuinely tiny (1-3 line fix in a clearly-identified location), you may skip the goldfish call — but only when the location is mechanically obvious. When in doubt, run it.

## Step 3: Capture the bug as a failing test BEFORE fixing

The verification criterion lives in code, not in chat. Pick the right tier:

This repo has no test suite or test framework. Do not add pytest just for one bug. Pick the lightest tier that pins the bug:
- **Pure-function repro script** (default for parsing, date-window, dedupe, scoring and formatting bugs): a short stdlib `python3` script in the scratchpad that imports the function from `scripts/` (or `dashboard/`) and `assert`s the expected output on a fixed input, such as a captured sheet row, a sample report snippet or a frozen SGT datetime. It lives outside the repo and is re-run after the fix. If the bug is likely to recur, offer to keep it as `scratch/test_<topic>.py` (the folder already holds ad hoc `test_*.py` probes).
- **Read-only CLI repro**: the exact `python3 scripts/<x>.py ...` invocation (`--dry-run`, `--pending`, precheck exit code, stdout fetch) that shows the wrong output, captured verbatim.
- **Dashboard repro**: a `curl http://127.0.0.1:8787/api/...` showing the wrong JSON, and/or an ego-browser script (open the tab, screenshot, read the console) showing the wrong render.

Freeze time where the bug depends on it: pass the datetime in, or monkeypatch the module's `datetime` in the repro script. Don't wait for the real slot.

Write the repro. Run it. Confirm it fails for the reason described in the problem doc. If it fails for a different reason, the repro is wrong — fix it before touching the implementation.

## Step 4: Fix it

Implement the smallest change that turns the failing test green and matches the "Fixed means" criterion.

Avoid: adjacent refactors, defensive coding for cases the bug did not surface, fallbacks that mask future regressions, unrequested feature flags. Bug fix scope is the bug, nothing else.

Re-run the failing test. It must go green. If it does not, you have not fixed the bug — do NOT rewrite the test.

For dashboard bugs, restart the server after any `dashboard/*.py` change (`launchctl kickstart -k gui/$(id -u)/com.chriseah.wikitrades.dashboard`), then re-run the ego-browser repro and confirm the bug is gone and the console is clean. For scheduled-job bugs, say which upcoming SGT slot will exercise the fix unattended, and check its output then if the user wants.

## Step 5: Hand off to `/eg-precommit-review`

Run `/eg-precommit-review` per the canonical procedure. The reviewer is a second goldfish — it sees only the diff. Triage findings, loop, and exit.

If `/eg-precommit-review` surfaces an issue that the Step 2 diagnosis goldfish missed, note it in the final report — it tells us where the diagnosis prompt needs to be tighter next time.

## Step 6: Test gate

```sh
python3 -m py_compile <each touched .py>      # node --check for .js/.mjs, bash -n for .sh
python3 <scratchpad>/repro_<bug>.py            # the Step 3 repro: must now pass
python3 scripts/<touched_script>.py --help     # plus --dry-run where it exists
curl -fsS http://127.0.0.1:8787/api/<endpoint> # only if dashboard/ touched
```

All required tiers must pass. Skip the dashboard tier only when the diff is purely `scripts/` or skills, with no change to anything the dashboard reads. For dashboard bugs, also re-verify the original repro in ego-browser one final time before reporting done.

## Step 7: Final report

Print to the user:
- Bug summary (one line)
- Root cause (one line)
- Fix (file:line)
- Test that captures it (file:test name)
- Goldfish-vs-elephant agreement (converged / diverged + why)
- `/eg-precommit-review` outcome (rounds, fixes, rebuttals verbatim)
- Test gate status

**STOP.** Do NOT commit; auto mode does not override the project's commit policy. Wait for the user's literal commit instruction. When it comes, follow `git log`: an `area: summary` subject (`dashboard: ...`, `scripts: ...`) or a short imperative sentence, a bulleted body, and the `Co-Authored-By` trailer. Stage files by name. `wiki/` and `raw/` are gitignored and never committed.
