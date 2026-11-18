#!/usr/bin/env python3
"""
Wiki housekeeping: prune old reports in wiki/reports/ and the chart images only they use.

Two-step by design: `plan` is read-only and writes a manifest; `apply` deletes exactly
what that manifest lists, then unlinks citations that pointed at the deleted reports.

  python3 .agents/skills/wiki-housekeeping/scripts/housekeeping.py usage
  python3 .agents/skills/wiki-housekeeping/scripts/housekeeping.py plan --days 30 [--include-odd]
  python3 .agents/skills/wiki-housekeeping/scripts/housekeeping.py apply --manifest <path>

Groups in a manifest:
  A  reports in wiki/reports/ whose date (filename, else mtime) is before the cutoff
  B  images whose every referencing page is in group A
  C  images no page references, with a filename date before the cutoff
  D  images no page references, with a missing/implausible filename date (only with --include-odd)

An image referenced by any surviving page (recent report, entity, note, hot.md, a .json
data file, ...) is never deleted. wiki/log.md mentions do not count as references: it is
an append-only text log, not an embed. Nothing outside wiki/reports/ and wiki/images/ is
ever deleted; raw/ is never touched.
"""

import argparse
import collections
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

REPO = Path("/Users/chriseah/obsidian/wiki-trades")
WIKI = Path(os.environ.get("HOUSEKEEPING_WIKI", REPO / "wiki"))  # override only for testing
REPORTS = WIKI / "reports"
IMAGES = WIKI / "images"
STATE_DIR = REPO / "scripts" / "housekeeping_runs"  # gitignored: manifests are per-run state

# Report subfolders never pruned (user-authored or low-volume, high-value).
DEFAULT_PROTECT = ["journal-review"]
REF_EXTS = (".md", ".json", ".jsonl", ".html", ".canvas")
IMG_RE = re.compile(r"([\w.\-]+\.(?:png|jpe?g|gif|svg|webp))", re.I)
LINK_RE = re.compile(r'(?<!!)\[([^\]]*)\]\(<?([^)<>]+?\.md)>?(?:\s+"[^"]*")?\)')


def fdate(name):
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", name)
    m2 = re.match(r"(\d\d)(\d\d)(\d\d)[-_]", name)
    try:
        if m:
            return dt.date(*map(int, m.groups()))
        if m2:
            return dt.date(2000 + int(m2[1]), int(m2[2]), int(m2[3]))
    except ValueError:
        return None
    return None


def rel(p):
    return str(Path(p).relative_to(WIKI))


def scan_refs(image_names):
    """basename -> set of wiki-relative pages that mention it (log.md excluded)."""
    refs = collections.defaultdict(set)
    for root, dirs, files in os.walk(WIKI):
        if Path(root) == IMAGES or IMAGES in Path(root).parents:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if not f.endswith(REF_EXTS) or f.endswith("manifest.json"):
                continue
            p = Path(root) / f
            r = rel(p)
            if r == "log.md":
                continue
            try:
                text = p.read_text(errors="ignore")
            except OSError:
                continue
            for m in set(IMG_RE.findall(text)):
                if m in image_names:
                    refs[m].add(r)
    return refs


def cmd_usage(args):
    imgs = {}
    for root, _, files in os.walk(IMAGES):
        for f in files:
            imgs[f] = imgs.get(f, 0) + os.path.getsize(os.path.join(root, f))
    refs = scan_refs(set(imgs))

    def folder(p):
        parts = p.split("/")
        if parts[0] == "reports":
            return "/".join(parts[:2]) if len(parts) > 2 else "reports/(root)"
        return parts[0]

    agg = collections.defaultdict(lambda: [0, 0])
    for n, s in imgs.items():
        fs = {folder(p) for p in refs.get(n, ())}
        key = " + ".join(sorted(fs)) if fs else "(UNREFERENCED)"
        agg[key][0] += 1
        agg[key][1] += s
    print(f"wiki/images: {len(imgs)} files, {sum(imgs.values())/1e9:.2f} GB\n")
    print(f"{'GB':>6} {'files':>6}  referenced from")
    for k, (c, s) in sorted(agg.items(), key=lambda x: -x[1][1])[: args.top]:
        print(f"{s/1e9:6.2f} {c:6d}  {k}")
    print("\nLargest images:")
    for n, s in sorted(imgs.items(), key=lambda x: -x[1])[: args.top]:
        where = ", ".join(sorted(refs.get(n, {"UNREFERENCED"})))
        print(f"{s/1e6:6.1f} MB  {n}  <- {where[:140]}")


def cmd_plan(args):
    today = dt.date.today()
    cutoff = dt.date.fromisoformat(args.cutoff) if args.cutoff else today - dt.timedelta(days=args.days)
    protect = set(DEFAULT_PROTECT + (args.protect or []))

    group_a = []
    for root, dirs, files in os.walk(REPORTS):
        sub = Path(root).relative_to(REPORTS).parts
        if sub and sub[0] in protect:
            dirs[:] = []
            continue
        for f in files:
            p = Path(root) / f
            d = fdate(f) or dt.date.fromtimestamp(p.stat().st_mtime)
            if d < cutoff:
                group_a.append(rel(p))
    a_set = set(group_a)

    imgs = collections.defaultdict(list)
    for root, _, files in os.walk(IMAGES):
        for f in files:
            imgs[f].append(rel(Path(root) / f))
    refs = scan_refs(set(imgs))

    b, c, d_odd = [], [], []
    for name, paths in imgs.items():
        r = refs.get(name)
        if r:
            if r <= a_set:
                b += paths
            continue
        d = fdate(name)
        if d is None or d.year < 2026 or d > today:
            d_odd += paths
        elif d < cutoff:
            c += paths

    def size(lst):
        return sum((WIKI / p).stat().st_size for p in lst)

    groups = {"A": sorted(group_a), "B": sorted(b), "C": sorted(c)}
    if args.include_odd:
        groups["D"] = sorted(d_odd)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else STATE_DIR / f"{today.isoformat()}-manifest.json"
    out.write_text(json.dumps({
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "cutoff": cutoff.isoformat(),
        "protect": sorted(protect),
        "groups": groups,
    }, indent=1))

    labels = {
        "A": "old reports",
        "B": "images only in old reports",
        "C": "unreferenced images before cutoff",
        "D": "unreferenced odd-dated images",
    }
    print(f"Cutoff {cutoff} (protected: {', '.join(sorted(protect))})\n")
    total_n = total_b = 0
    for g, lst in groups.items():
        s = size(lst)
        total_n += len(lst)
        total_b += s
        print(f"{g} {labels[g]:36} {len(lst):6d} files {s/1e9:6.2f} GB")
    print(f"  {'TOTAL':36} {total_n:6d} files {total_b/1e9:6.2f} GB")
    if not args.include_odd and d_odd:
        print(f"\n{len(d_odd)} odd-dated unreferenced images NOT included (add --include-odd):")
        for p in sorted(d_odd)[:15]:
            print("   ", p)
    per = collections.Counter(str(Path(p).parent) for p in groups["A"])
    print("\nOld reports by folder:")
    for k, v in sorted(per.items()):
        print(f"   {v:4d}  {k}")
    print(f"\nManifest: {out}")


def cmd_apply(args):
    man = json.loads(Path(args.manifest).read_text())
    paths = [p for g in man["groups"].values() for p in g]
    for p in paths:
        if not (p.startswith("reports/") or p.startswith("images/")) or ".." in p:
            sys.exit(f"refusing: {p} is outside wiki/reports or wiki/images")

    # Safety re-check: an image picked up a new reference since the plan -> keep it.
    deleted_reports = set(man["groups"].get("A", []))
    img_paths = [p for g in ("B", "C", "D") for p in man["groups"].get(g, [])]
    refs = scan_refs({Path(p).name for p in img_paths})
    skipped = []
    n = nbytes = missing = 0
    for p in paths:
        if p.startswith("images/"):
            r = refs.get(Path(p).name, set()) - deleted_reports
            if r:
                skipped.append((p, sorted(r)[:2]))
                continue
        f = WIKI / p
        if f.is_file():
            nbytes += f.stat().st_size
            f.unlink()
            n += 1
        else:
            missing += 1

    # Unlink citations to deleted reports, keeping the link text.
    deleted = {os.path.normpath(p) for p in deleted_reports}
    nl = nf = 0
    for root, dirs, files in os.walk(WIKI):
        if Path(root) == IMAGES or IMAGES in Path(root).parents:
            dirs[:] = []
            continue
        for fn in files:
            if not fn.endswith(".md") or rel(Path(root) / fn) == "log.md":
                continue
            page = Path(root) / fn
            text = page.read_text(errors="ignore")
            base = os.path.dirname(rel(page))
            cnt = 0

            def sub(m):
                nonlocal cnt
                tgt = os.path.normpath(os.path.join(base, unquote(m[2])))
                if tgt in deleted and not (WIKI / tgt).exists():
                    cnt += 1
                    return m[1]
                return m[0]

            new = LINK_RE.sub(sub, text)
            if cnt:
                page.write_text(new)
                nf += 1
                nl += cnt

    # Remove empty dirs only inside reports/archives (live report folders stay even if empty).
    arch = REPORTS / "archives"
    if arch.exists():
        for root, _, _ in sorted(os.walk(arch), key=lambda x: -len(x[0])):
            if not os.listdir(root):
                os.rmdir(root)

    g = man["groups"]
    summary = (
        f"Cutoff {man['cutoff']}. Deleted {n} files ({nbytes/1e9:.2f} GB): "
        f"{len(g.get('A', []))} reports, {len(g.get('B', []))} images used only by them, "
        f"{len(g.get('C', []))} unreferenced images"
        + (f", {len(g['D'])} odd-dated unreferenced images" if g.get("D") else "")
        + f". Unlinked {nl} citations to deleted reports in {nf} pages (text kept)."
        + (f" Kept {len(skipped)} images that gained a reference since the plan." if skipped else "")
        + (f" {missing} manifest entries were already gone." if missing else "")
    )
    print(summary)
    for p, r in skipped[:10]:
        print("   kept", p, "<-", r)
    if not args.no_log:
        subprocess.run([sys.executable, str(REPO / "scripts/append_log.py"), "--action", "delete",
                        "--title", f"Wiki housekeeping (reports before {man['cutoff']})",
                        "--body", summary + f" Manifest: {args.manifest}"], check=False)
    sys.stdout.flush()
    subprocess.run(["du", "-sh", str(IMAGES), str(REPORTS)], check=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    u = sp.add_parser("usage", help="read-only: image space by referencing folder + largest images")
    u.add_argument("--top", type=int, default=20)
    p = sp.add_parser("plan", help="read-only: build a deletion manifest")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--cutoff", help="YYYY-MM-DD; overrides --days")
    p.add_argument("--include-odd", action="store_true")
    p.add_argument("--protect", action="append", help="extra reports/ subfolder to never prune")
    p.add_argument("--out")
    a = sp.add_parser("apply", help="delete what a manifest lists")
    a.add_argument("--manifest", required=True)
    a.add_argument("--no-log", action="store_true")
    args = ap.parse_args()
    if not (REPO / "AGENTS.md").is_file() or not (REPO / "scripts/append_log.py").is_file():
        sys.exit(f"refusing: {REPO} is not the wiki-trades repo; this script is for wiki-trades only")
    {"usage": cmd_usage, "plan": cmd_plan, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    main()
