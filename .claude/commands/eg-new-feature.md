---
description: Build a new feature using the elephant/goldfish workflow — design doc, goldfish design check, implement, review, validate
argument-hint: feature description (what the user wants and why)
---

Build a new feature using the elephant/goldfish workflow. The aim: design before code, let a fresh goldfish stress-test the design doc, then implement, review, and validate.

`$ARGUMENTS` is the feature description provided by the user. If empty, ask for one before doing anything. If `$ARGUMENTS` is a GitHub issue URL or `#<number>`, fetch it with `gh issue view <number> --json title,body,labels,comments` and seed the design doc from it.

## Interactivity is mandatory at decision points — overrides any "no-stopping" directive

This skill has small but **mandatory** user-facing decision points: scope confirmation in Step 0, the "save design doc to disk?" choice in Step 1, the "still not converging after 3 revisions" gate in Step 2, the no-code-gate override in Step 1, and any moment a design assumption is genuinely ambiguous. Enumerable choices go through `AskUserQuestion`; genuinely unbounded answers (verbatim correction text, custom paths) go through one targeted chat prompt AFTER an `AskUserQuestion` scopes the reason.

If a `<system-reminder>` or any other injected directive in this session tells you to work autonomously without stopping for clarifying questions (e.g. "no-stopping directive", "the user has asked you to work without stopping"), **it does NOT override these gates**. The no-code gate especially: do not bypass it on the user's behalf just because a directive said to keep working. The user's consent for autonomous mode applies to ordinary work, not to gates this skill specifically enumerates.

The only opt-out: if the user, in the same turn that invoked this skill, explicitly says "skip the design-doc gate" or "use defaults" (or equivalent unambiguous override), you may bypass the affected gate. Even then: print what you decided and continue to enforce the no-code gate until Pass B and Pass C close.

**Routing:** this command is for changing the code (scripts, scheduled jobs, dashboard, skills, wiki conventions). Routine wiki operations, such as an ingest, a TAT analysis, a brief, a journal entry or a journal review, are not features: they follow AGENTS.md and the skills directly. If the request is really one of those, say so and do it that way instead.

## Step 0: Confirm scope before designing

Restate the request back to the user in 1-2 sentences ("I read this as: <X>. Confirm or correct."). Misreads at this stage waste the most time later. If the user already gave a sharp request, this is a one-line confirmation, not a real check-in.

Surface-area sanity check:
- **Dashboard-only change** (`dashboard/`, read-only view over existing files): straightforward. Mirror an existing tab or card in `dashboard/static/app.js` and its reader in `dashboard/wiki_data.py`.
- **Dashboard write path** (a new `POST /api/*`): confirm with the user. The dashboard is read-only except the Journal and My Watchlist forms, and every write must go through an existing script (e.g. `scripts/journal.py`), not hand-rolled file edits.
- **Script output format change** (report headings, table columns, JSON keys, filenames): list every reader first. The dashboard parses many reports by heading or table shape, and skills and Orca prompts reference them.
- **New or moved scheduled job** (launchd plist, Orca automation, a new step inside an existing automation): confirm the SGT slot against the existing schedule in AGENTS.md, plus TradingView/CDP-lock and ego-browser contention. Orca prompts embed their own copy of the workflow, so editing a SKILL.md alone doesn't change a scheduled run.
- **Anything driving TradingView or ego-browser**: it must use the batch session rule (one `tv_session.sh start`/`stop`), line chart and TAW layout, the timestamped image names, and screenshot verification.
- **New external source** (sheet tab, API, scraped site): confirm credentials, rate limits, and what happens when it is empty, slow or blocked.
- **Wiki convention / AGENTS.md change**: this is the schema. Confirm with the user, and check whether the `llm-wiki-manager` skill's lint/migration conventions (and `scripts/lint_images.py`) need to follow.

## Step 1: Write the design doc

Print the design doc to the user. For most features this lives in chat; for substantial features (new domain area, new API resource family, new subsystem) propose writing it to `docs/design/` and ask the user via `AskUserQuestion` before creating the file:

- `question`: "Save the design doc to disk for durability?"
- `header`: `"Save doc?"`
- `multiSelect`: `false`
- `options`:
  1. **Yes, save to `docs/design/<inferred-slug>.md`** — "Keep it as a durable artifact."
  2. **Keep in chat only** — "Doc lives in this conversation."
  3. **Different path** — "I'll specify in chat."

Required sections:

```
DESIGN DOC
- Why: <user problem this solves; cite GH issue, conversation, or PRD section>
- Scope: <what is in; what is explicitly out>
- Surfaces touched: <files / routes / models / controllers / components / DB tables / external services>
- Interfaces: <component props, function signatures, API request/response shapes, DB columns, queue arguments>
- UX flow: <click-by-click for UI; request-by-request for backend>
- SGT timing: <when it runs (exact SGT slot or trigger), which bar or date window it reads (closed bars only; SGX/HKEX D−1 offset; per-asset-class weekly close), weekends and public holidays, and which existing slots it must not overlap>
- Shared resources: <TradingView session / CDP lock, ego-browser, Google Sheets quota, Forex Factory rate limit; how it waits for or yields to other jobs>
- Data contracts: <every file it writes (path, format, append vs rewrite, same-day rerun behaviour) and every reader of each output (dashboard, other scripts, skills, Orca prompts); every file it reads and who writes it>
- Unattended behaviour: <how it behaves under Orca/launchd/`claude -p` with no human: no prompts, bounded retries, non-zero exit on real failure, `append_log.py` `error` entry, nothing left running (TradingView, ego lite)>
- Doc drift: <which AGENTS.md rules, SKILL.md files and Orca automation prompts must change with it>
- Failure modes: <what the user sees when each thing breaks: empty sheet, TradingView not launching, blank screenshot, network down, stale cache; what the dashboard shows>
- Verification criteria: <repro/check scripts, read-only CLI runs (`--help`, `--dry-run`), report snippets that must appear, manual ego-browser dashboard steps, and which real SGT slot will prove it unattended>
- Out-of-scope follow-ups: <noted, not built>
```

If the feature came out of `/eg-prd` or `/eg-brainstorm`, **reference the PRD or brief by path and section** (`docs/prds/<slug>.md §3`) so the doc and the source of truth stay aligned. For trading-logic features (signal rules, scoring, levels), cite the wiki concept or source page the rule comes from (`wiki/concepts/tat.md`, `wiki/AHH Session Notes/...`), per AGENTS.md Bookkeeping discipline #8.

For UI work, sketch the visual structure in plain text or pseudo-JSX. If the design needs a real visual reference, ask the user to point at an existing component to mirror.

### No-code gate

**Do NOT edit, write, scaffold, or refactor code until BOTH Pass B (Critic) AND Pass C (Readiness) in Step 2 close with their ready tokens (`design ready` + `implementation ready`).** Article rule, paraphrased: *"I do not want you to create code. We are not going to create code. Resist your impulse."* This holds until the design doc passes both gates — even if the user asks to skip ahead, even if the change "looks trivial", even if it is "just one line".

If the user explicitly asks to skip the gate ("just write the code", "skip the design doc", etc.), restate the gate, name the still-open passes, and require an explicit override via `AskUserQuestion`:

- `question`: "Override the no-code gate? Design hasn't passed Critic+Readiness yet."
- `header`: `"Override?"`
- `multiSelect`: `false`
- `options`:
  1. **Yes, override** — "Proceed to implementation. I accept the open design risks."
  2. **No, finish the design check** — "Run another round of Pass B/C first."

Only "Yes, override" unblocks code edits. The exception is `/eg-fix-bug` for trivial fixes covered by its own Step 0 triviality gate — that is a separate command with a separate gate.

The design doc itself, test names mentioned in chat (not yet on disk), and read-only exploration (`Read`, `Grep`, `Bash` for `git status` / `git log` / `git diff`, `python3 scripts/<x>.py --help`, `--dry-run` / `--pending` runs that write nothing, `curl` against the dashboard's GET endpoints, `launchctl list | grep wikitrades`, `orca automations list`, reading `wiki/` reports) are NOT code edits and are permitted.

## Step 2: Three-goldfish design check

Run the article's full design-stage protocol: three sequential `Agent` calls per round (or two on revisions — see below), each with no prior context. The combined gate is "ready iff critic AND readiness both sign off"; comprehension is informational.

Each pass uses `subagent_type: "general-purpose"` and gets ONLY the design doc (no chat history, no implementation intent, no other passes' output). The asymmetry is the value.

**Round 1 runs all three passes; round 2+ skips comprehension** (revisions are gap-driven, not structural — once the doc reads cleanly, it almost always still reads cleanly). On every round, run critic and readiness.

### Pass A — Comprehension (round 1 only)

`description: "Goldfish comprehension check"`. Verifies the doc reads cleanly to a cold reader.

```
<<<COMPREHENSION_START>>>
You are a fresh reader with no prior context. Below is a design doc for a feature in the wiki-trades (an LLM-managed Obsidian trading wiki plus Python 3 scripts, launchd/Orca scheduled jobs and a stdlib-Python "Trade Terminal" dashboard that pull TAT alerts from Google Sheets, drive TradingView Desktop for chart captures, and write reports into `wiki/`) repo. Do NOT critique it yet. Your job is to verify the doc reads clearly to someone who walks in cold.

Output two short sections in this order:

## What this feature does
2-5 sentences in your own words. The user-visible change. Who triggers it, when, what they get back.

## How the existing system works (per the doc)
2-5 sentences summarizing the current behavior the doc describes touching. Surfaces, controllers, components, message flow — whatever the doc references.

End your output with EXACTLY one of these closing lines, on its own line:
- comprehension passed       (the doc reads cleanly; no ambiguous sections)
- comprehension unclear      (one or more sections are too vague to paraphrase)

If you mark it unclear, list the ambiguous sections by heading before the closing line. Do NOT critique architecture choices here — that is the critic's job. Only flag things you genuinely cannot understand.

DESIGN DOC:

<PASTE FULL DESIGN DOC FROM STEP 1 HERE>
<<<COMPREHENSION_END>>>
```

### Pass B — Critic (every round)

`description: "Goldfish design critic"`. Finds gaps that block implementation.

```
<<<DESIGN_START>>>
You are a fresh reviewer with no prior context. Below is a design doc for a feature in the wiki-trades (an LLM-managed Obsidian trading wiki plus Python 3 scripts, launchd/Orca scheduled jobs and a stdlib-Python "Trade Terminal" dashboard that pull TAT alerts from Google Sheets, drive TradingView Desktop for chart captures, and write reports into `wiki/`) repo (CLAUDE.md at the repo root has the architecture, including the SGT schedule of Orca/launchd jobs, the batch TradingView session rule, and which dashboard tabs read which wiki files).

Your job: read the design doc, then read the surfaces it claims to touch, and find holes BEFORE implementation starts. Specifically:

- Is the scope crisp? What questions would you have to answer to implement this that the doc does not answer?
- Are the interfaces concrete enough that two implementers would converge on the same result?
- Do the verification criteria actually verify the feature, or only verify that "something rendered"?
- Does the doc misunderstand any existing code? Look up the surfaces it claims to touch and check.
- Are there failure modes the doc missed? Network errors, unauthenticated users, empty state, partial saves, stale data, retries.
- SGT timing: does the slot collide with an existing job (05:01 Daily Brief, 05:45 Daily Signals, 06:15/09:01/13:01/17:01/21:01 TAT runs, 19:15 Portfolio, the central-bank and calendar pollers)? Does it read only closed bars? Are date windows right across weekends, holidays and the SGX/HKEX D−1 offset?
- Shared resources: does it open TradingView or ego-browser outside the batch session rule, hold the CDP lock too long, or race another job on the same wiki bookkeeping files (`log.md`, `index.md`, `hot.md`)?
- Data contracts: is every reader of every changed output named? Would the dashboard's parsers (`dashboard/wiki_data.py`) or another script break on the new shape? Do same-day reruns append or overwrite as AGENTS.md requires?
- Unattended runs: would it hang, prompt, exit 0 on failure, retry forever, or leave TradingView / ego lite running under Orca or launchd? Does it fit Orca's 600 s `--precheck` limit if it lives there?
- Ownership rules: does anything write to `raw/`, hand-edit structural wiki files instead of using the scripts, or rewrite the user's own journal words?
- Doc drift: which AGENTS.md rules, SKILL.md files and Orca automation prompts go stale if this ships as designed?
- Are there project-specific gotchas the doc ignores? CLAUDE.md is your reference.

If the doc cites a PRD or brief under docs/prds/ or docs/eg-brainstorms/, load it and check that the doc is consistent with it. For trading-logic rules, check the cited wiki/concepts/ or source pages actually say what the doc claims.

For dashboard work, you may open the running dashboard at http://127.0.0.1:8787 with the ego-browser skill to verify how an existing surface behaves. Do not start TradingView sessions or write into wiki/ or raw/.

DESIGN DOC:

<PASTE FULL DESIGN DOC FROM STEP 1 HERE>

Output: numbered list of gaps, with file:line citations where applicable. End with `design ready` ONLY if you have zero gaps. Otherwise list them and end with `design needs revision`.
<<<DESIGN_END>>>
```

### Pass C — Readiness (every round)

`description: "Goldfish implementation readiness"`. Stricter than the critic: not "is the design good?" but "is the design _executable_ in one pass?"

```
<<<READINESS_START>>>
You are a fresh implementer with no prior context. Below is a design doc for a feature in the wiki-trades (an LLM-managed Obsidian trading wiki plus Python 3 scripts, launchd/Orca scheduled jobs and a stdlib-Python "Trade Terminal" dashboard that pull TAT alerts from Google Sheets, drive TradingView Desktop for chart captures, and write reports into `wiki/`) repo. Imagine you've been told: "Implement this. First pass. No follow-up questions allowed." Could you?

For every interface, file path, function signature, API request/response shape, DB column, queue argument, component prop, message type, and verification criterion the doc claims, ask:
- Could I write the corresponding code without asking the author anything?
- Could I verify it works without asking what "works" means?
- Are the cited files and line numbers concrete enough that I'd open the right file and edit the right region?

Output a numbered list of EVERY question you would have to ask the author before you could ship. For each:
- The question itself, one sentence.
- The section of the doc that should have answered it but didn't.

If the list is empty, say "No open questions."

End with EXACTLY one of these closing lines, on its own line:
- implementation ready       (zero open questions; first-pass implementable)
- implementation not ready   (one or more open questions remain)

A design can be beautiful and still fail this gate. The critic asks "is the design good?"; you ask "is the design executable?".

DESIGN DOC:

<PASTE FULL DESIGN DOC FROM STEP 1 HERE>
<<<READINESS_END>>>
```

### Triage and loop

A round is **ready** iff Pass B closes with `design ready` AND Pass C closes with `implementation ready`. Comprehension is informational: log it, surface it to the user, but do not gate progress on it. If comprehension returns `comprehension unclear` AND the round is otherwise ready, still proceed — but flag in the final report that the doc was unclear in places.

If a round is **not ready**, bundle the critic gaps and readiness open questions into a single revise prompt:

```
=== CRITIC GAPS ===
<verbatim Pass B output>

=== READINESS OPEN QUESTIONS ===
<verbatim Pass C output>
```

Plus, if Pass A returned `comprehension unclear`, prepend:

```
=== COMPREHENSION FEEDBACK (informational — the cold reader could not paraphrase parts of the doc) ===
<verbatim Pass A output>
```

Tell the elephant to address EVERY numbered gap from BOTH the CRITIC GAPS and READINESS OPEN QUESTIONS sections — do not collapse or skip a section because the numbering restarts. Each gap is either: addressed in a doc revision, or rebutted with a verbatim reason citing CLAUDE.md / AGENTS.md / the PRD or brief under `docs/` / the cited `wiki/concepts/` page / the user's words from this conversation. Print the revised doc back to the user once both gates close.

Then re-run Pass B and Pass C against the revised doc (skip Pass A — see above). If the round still does not converge after **three revisions**, the feature is under-specified. Stop and call `AskUserQuestion`:

- `question`: "Design check hit the 3-revision cap with N gaps still open. What now?"
- `header`: `"3R cap"`
- `multiSelect`: `false`
- `options`:
  1. **I'll clarify scope in chat** — "I'll answer the open gaps directly; you re-run Pass B/C."
  2. **Drop one or more requirements** — "I'll specify which scope to cut so the doc converges."
  3. **Override and proceed anyway** — "Accept the open gaps as known unknowns; flag them in the final report and continue to Step 3."
  4. **Abandon the design** — "This feature isn't well enough understood yet. Stop."

Free-form chat (for option 1 or 2) only happens AFTER this question has scoped the choice.

## Step 3: Implementation plan

Once the design doc is `design ready`, write a short ordered implementation plan in chat:

1. Data source and pure logic first: fetch/parse helpers and scoring/date-window functions in `scripts/`, each with a scratchpad repro/check script.
2. The script's CLI: argparse with `--help`, plus `--dry-run` (or another read-only mode) for anything that writes.
3. Output writers: report/JSON/state files in the exact format the design names, using `append_log.py` / `update_index.py` / `update_weekly_index.py` for bookkeeping.
4. TradingView / ego-browser capture steps, if any, inside one batch session.
5. Dashboard reader (`dashboard/wiki_data.py` / `server.py` / `statements.py`), then the UI (`dashboard/static/app.js`, `charts.js`, `style.css`, `index.html`).
6. Docs: AGENTS.md rule, the SKILL.md under `.agents/skills/`, and the dashboard README.
7. Scheduling last: launchd plist or Orca automation (prompt text written for the user to apply; changing a live automation is outward-facing, so confirm first).

For trivial features (single-component change), skip this step.

## Step 4: Implement

**Pre-flight check before any code edit:** confirm Step 2 closed both Pass B (Critic) AND Pass C (Readiness). If either is still open, the no-code gate from Step 1 still applies — return to Step 2 instead of proceeding.

Follow the plan. After each layer, briefly verify before moving on:

- Logic: `python3 -m py_compile`, plus the scratchpad check script asserting outputs on fixed inputs (with a frozen SGT datetime where timing matters).
- CLI: `--help` and `--dry-run` run cleanly, and the dry-run output matches the designed format.
- Writers: one real run, if it's safe outside a scheduled slot. Then open the written file and confirm the format, append-vs-rewrite behaviour and the `wiki/log.md` entry. If it's not safe, write into the scratchpad via an output-path flag.
- Captures: run outside the scheduled capture slots, then open at least one PNG with the Read tool.
- Dashboard: `launchctl kickstart -k gui/$(id -u)/com.chriseah.wikitrades.dashboard`, `curl` the endpoint, then ego-browser screenshot + console check.
- Scheduling: `plutil -lint` the plist. For Orca, show the prompt/trigger diff to the user rather than applying it unasked.

**For dashboard changes, drive the feature in ego-browser against `http://127.0.0.1:8787` before reporting it done.** Check it at phone width too, since the dashboard is used from a phone over Tailscale.

**Always verify the no-harm path:** a run with empty input (no new alerts, empty sheet tab, weekend) produces the documented "nothing new" output, not a crash or a blank report.

## Step 5: Hand off to `/eg-precommit-review`

Run `/eg-precommit-review`. Pass the feature name as `$ARGUMENTS` so the reviewer focuses there.

## Step 6: Test gate

```sh
python3 -m py_compile <each touched .py>      # node --check for .js/.mjs, bash -n for .sh, plutil -lint for .plist
python3 <scratchpad>/check_<feature>.py        # the per-layer check scripts: must pass
python3 scripts/<touched_script>.py --help     # plus --dry-run where it exists
curl -fsS http://127.0.0.1:8787/api/<endpoint> # only if dashboard/ touched
```

All required tiers must pass. For dashboard features, **also do a final ego-browser walkthrough** of the golden path AND the most plausible edge case (empty data, missing report file for today, stale cache, a failed sheet fetch, weekend/no-new-alerts, very long instrument lists). Type checks and tests verify code correctness, not feature correctness — the user expects you to have actually used the feature.

## Step 7: Final report

Print to the user:
- Feature summary (one line)
- Files touched (grouped by layer: scripts / dashboard server / dashboard UI / skills & docs / scheduling)
- Tests added (file:test name each)
- Design-check result (gaps surfaced and how each was resolved)
- `/eg-precommit-review` outcome (rounds, fixes, rebuttals verbatim)
- Test gate status
- Walkthrough summary (ego-browser golden path + edge cases exercised for dashboard work; for scripts, the real or dry runs done and which upcoming SGT slot will exercise it unattended)
- Doc/automation drift: AGENTS.md / SKILL.md updated, and any Orca prompt change the user still needs to apply
- Out-of-scope follow-ups noted in the design doc

**STOP.** Do NOT commit; auto mode does not override the project's commit policy. Wait for the user's literal commit instruction. When it comes, follow `git log`: an `area: summary` subject (`dashboard: ...`, `scripts: ...`) or a short imperative sentence, a bulleted body, and the `Co-Authored-By` trailer. Stage files by name. `wiki/` and `raw/` are gitignored and never committed.
