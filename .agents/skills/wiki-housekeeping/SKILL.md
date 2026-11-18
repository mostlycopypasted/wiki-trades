---
name: wiki-housekeeping
description: wiki-trades vault only (/Users/chriseah/obsidian/wiki-trades) — not for other repos or vaults. Prune old auto-generated reports in wiki/reports/ and the chart screenshots in wiki/images/ that only those reports use, to keep the vault (and Obsidian Sync) small. Read-only usage/plan first, user confirmation, then delete + unlink citations + bookkeeping. Use when the user asks for housekeeping, cleanup, pruning old reports, freeing disk space, or "what's taking space in images".
license: MIT
metadata:
  author: AI Trading Team
  version: "1.0.0"
  tags:
    - maintenance
---

# Wiki Housekeeping (wiki-trades only)

Scoped to this vault: the skill lives in this repo (`.agents/skills/`, linked from `.claude/skills/`), so it loads only in sessions opened in wiki-trades, and the script's paths are fixed to `/Users/chriseah/obsidian/wiki-trades`. Its rules (report folders, the scheduled capture jobs, `append_log.py`, the weekly index) are this wiki's. Don't copy it to `~/.claude/skills` or use it in another vault.

Scheduled runs (Daily Brief, Daily Signals, TAT Combined, My Watchlist sweep, Equity News, Portfolio) add ~100 MB of chart PNGs a day to `wiki/images/`; the reports themselves are tiny. Space is freed by deleting **old reports together with the images only they embed**. First run: 2026-11-18 (30-day cutoff, 3.62 GB freed, images 7.3 → 3.5 GB).

Script: `.agents/skills/wiki-housekeeping/scripts/housekeeping.py` (`usage` / `plan` / `apply`).

## Rules

- **Deletion is permanent.** `wiki/` is not in git; Obsidian Sync propagates deletes to every device, and its version history is the only recovery. Never `apply` without the user confirming the `plan` numbers in this session (a standing "delete outright" decision covers the method, not each run).
- Only `wiki/reports/` and `wiki/images/` are ever touched. Never `raw/`, `wiki/notes/` (incl. the trade journal and signal-judge data), `sources/`, `entities/`, `concepts/`, `AHH Session Notes/`.
- An image is kept if **any** surviving page or data file (`.md/.json/.jsonl/.html/.canvas`, anywhere in `wiki/` except `log.md`) mentions its filename. `log.md` is an append-only text log, so its mentions don't keep an image.
- Unreferenced images newer than the cutoff are kept (a live run may not have filed its report yet).
- `reports/journal-review/` is always protected; add more with `--protect <subfolder>`.
- Never run `apply` while a scheduled capture run is in progress (check `wiki/log.md` tail / Orca): a fresh screenshot could be unreferenced for a few minutes. Safe windows: e.g. 11:00–13:30 or 15:00–17:00 SGT on a weekday, or Sunday.

## Workflow

1. **Survey (read-only):** `python3 .agents/skills/wiki-housekeeping/scripts/housekeeping.py usage` — image GB by referencing folder, unreferenced total, largest files. Show the user.
2. **Plan (read-only):** `... housekeeping.py plan --days 30` (or `--cutoff YYYY-MM-DD`; `--include-odd` adds unreferenced images with an implausible date in the name, e.g. a mistyped `280828-…`). Writes `scripts/housekeeping_runs/YYYY-MM-DD-manifest.json` (gitignored) and prints group counts/GB:
   - **A** reports dated before the cutoff (filename date, else mtime)
   - **B** images whose every reference is a group-A report
   - **C** unreferenced images dated before the cutoff
   - **D** odd-dated unreferenced images (only with `--include-odd`)
3. **Confirm** with `AskUserQuestion`: totals per group, the folders affected, and whether to include odd-dated images. Stop if they want to review the manifest.
4. **Apply:** `... housekeeping.py apply --manifest scripts/housekeeping_runs/<date>-manifest.json`. It re-checks each image's references first (keeps any that gained one since the plan), deletes, turns `[text](deleted-report.md)` citations into plain `text` across the wiki (entity pages cite equity-news/TAT reports heavily), removes empty folders under `reports/archives/` only, logs a `delete` entry via `scripts/append_log.py`, and prints `du` of images/reports.
5. **Bookkeeping:**
   - `python3 scripts/update_weekly_index.py` and check `wiki/index.md` has no links to deleted reports (`grep -n 'reports/' wiki/index.md`), editing out any that do.
   - Add a one-line housekeeping note to `wiki/hot.md` **Vault State** (replace the previous housekeeping line rather than stacking them).
   - If a whole report type was removed, update the AGENTS.md sentence that describes it.
6. **Verify:** re-run `usage`; confirm the dashboard (`http://127.0.0.1:8787`) still loads the Daily Brief / TAT / My Watchlist / Signals / Equity tabs for recent dates. Report what was deleted, GB freed, citations unlinked, anything kept by the safety re-check.

## Notes

- Image embeds that were already broken before a run (152 on 2026-11-18) are not this skill's doing; report them separately rather than "fixing" them by deleting the embed.
- `reports/my_watchlist/` is now the largest image consumer (16 instruments × 5 sweeps/day).
- Test against a throwaway tree with `HOUSEKEEPING_WIKI=/path/to/fake-wiki` (manifest outside that tree).
