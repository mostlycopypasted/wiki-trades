#!/usr/bin/env python3
"""Maintain wiki/index.md: the per-page catalog of Sources, AHH Session Notes,
Entities, Concepts, and Notes. Preserves the WEEKLY_INDEX block (owned by
update_weekly_index.py) and the Trade Journal lint exception (journal entries
are not indexed individually; see CLAUDE.md's Lint Exceptions section).

Usage:
    python3 scripts/update_index.py --rebuild
        Rescans every category directory and regenerates the full catalog.

    python3 scripts/update_index.py --category sources --title "TAR Session (2026-09-05)" \\
        --page-path "wiki/sources/2026-09-05-tar-session.md" --summary "..."
        Inserts or updates a single entry without rescanning everything else.
"""
import argparse
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_PATH = BASE_DIR / "wiki" / "index.md"

CATEGORIES = {
    "sources": {"heading": "## Sources", "dir": BASE_DIR / "wiki" / "sources"},
    "ahh-session-notes": {"heading": "## AHH Session Notes", "dir": BASE_DIR / "wiki" / "AHH Session Notes"},
    "entities": {"heading": "## Entities", "dir": BASE_DIR / "wiki" / "entities"},
    "concepts": {"heading": "## Concepts", "dir": BASE_DIR / "wiki" / "concepts"},
    "notes": {"heading": "## Notes", "dir": BASE_DIR / "wiki" / "notes"},
}

DEFAULT_TAG = {
    "sources": "transcript",
    "ahh-session-notes": "transcript",
    "entities": "trading-instrument",
    "concepts": "concept",
    "notes": "note",
}

MAX_SUMMARY_LEN = 220


def strip_md_links_keep_text(text):
    # Leave [[wikilinks]] as-is (allowed in prose); just collapse whitespace.
    return re.sub(r"\s+", " ", text).strip()


def first_tag(text):
    m = re.search(r"^tags:\s*\[([^\]]*)\]", text, re.MULTILINE)
    if not m:
        return None
    parts = [p.strip().strip('"').strip("'") for p in m.group(1).split(",")]
    return parts[0] if parts and parts[0] else None


def extract_title(text, fallback):
    m = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    if not m:
        return fallback
    title = m.group(1).strip()
    title = re.sub(r"^Session Summary:\s*", "", title)
    return title


def extract_metadata_block_summary(text):
    """Trade watch/trade log notes open with a bolded metadata block
    (Created Date / Instrument / Direction / Status / ...) instead of prose.
    Synthesize a summary from those fields rather than quoting the block.
    Only looks at the opening block (between the H1 and the first ## heading
    or --- separator) so it never matches a Direction/Status bullet buried
    deep in a session note's Trading Opportunities section."""
    h1 = re.search(r"^#\s+.+?\n", text, re.MULTILINE)
    if not h1:
        return None
    rest = text[h1.end():]
    boundary = re.search(r"\n##\s|\n---\s*\n", rest)
    opening_block = rest[:boundary.start()] if boundary else rest[:600]

    fields = {}
    for key in ("Direction", "Status", "Instrument", "Breakout Level", "Execution Condition"):
        m = re.search(rf"\*\*{re.escape(key)}\*\*:\s*(.+?)(?:\s{{2,}}|\n|$)", opening_block)
        if m:
            fields[key] = strip_md_links_keep_text(m.group(1)).rstrip("*").strip()
    if "Direction" not in fields and "Status" not in fields:
        return None
    bits = []
    if "Direction" in fields:
        bits.append(fields["Direction"])
    if "Status" in fields:
        bits.append(fields["Status"])
    if "Breakout Level" in fields:
        bits.append(f"breakout level {fields['Breakout Level']}")
    summary = "; ".join(bits)
    return clean_summary(summary) if summary else None


def extract_summary(text):
    meta_summary = extract_metadata_block_summary(text)
    if meta_summary:
        return meta_summary

    # 1. ## Executive Summary paragraph
    m = re.search(r"^##\s*(?:📈\s*)?Executive Summary\s*\n+(.+?)(?:\n\s*\n|\n##|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        m = re.search(r"^##\s*Executive Summary\s*\n+(.+?)(?:\n\s*\n|\n##|\Z)", text, re.MULTILINE | re.DOTALL)
    if m:
        return clean_summary(m.group(1))

    # 2. ## Definition paragraph (concepts)
    m = re.search(r"^##\s*Definition\s*\n+(.+?)(?:\n\s*\n|\n##|\Z)", text, re.MULTILINE | re.DOTALL)
    if m:
        return clean_summary(m.group(1))

    # 3. Blockquote directly under the H1 (entities)
    m = re.search(r"^#\s+.+?\n+^>\s*(.+?)\s*$", text, re.MULTILINE)
    if m:
        return clean_summary(m.group(1))

    # 4. First non-empty paragraph after the H1 that isn't a heading/frontmatter
    lines = text.split("\n")
    seen_h1 = False
    buf = []
    for line in lines:
        if not seen_h1:
            if line.startswith("# "):
                seen_h1 = True
            continue
        stripped = line.strip()
        if not stripped:
            if buf:
                break
            continue
        if stripped.startswith("#"):
            if buf:
                break
            continue
        buf.append(stripped)
    if buf:
        return clean_summary(" ".join(buf))
    return "(no summary available)"


def clean_summary(raw):
    text = strip_md_links_keep_text(raw)
    # Prefer the first sentence if that keeps things short.
    m = re.match(r"(.{20,%d}?[.!?])\s" % MAX_SUMMARY_LEN, text)
    if m:
        return m.group(1)
    if len(text) <= MAX_SUMMARY_LEN:
        return text
    cut = text[:MAX_SUMMARY_LEN].rsplit(" ", 1)[0]
    return cut + "…"


def is_hub(text):
    return bool(re.search(r"^##\s*Pages in this cluster", text, re.MULTILINE))


def rel_link(category, filepath):
    name = filepath.name
    dirpart = CATEGORIES[category]["dir"].name
    if " " in dirpart:
        return f"<{dirpart}/{name}>"
    return f"{dirpart}/{name}"


def build_entry(category, filepath):
    text = filepath.read_text(encoding="utf-8")
    title = extract_title(text, filepath.stem)
    summary = extract_summary(text)
    tag = first_tag(text) or DEFAULT_TAG[category]
    hub_mark = " ★" if is_hub(text) else ""
    link = rel_link(category, filepath)
    return title, f"- [{title}]({link}){hub_mark} — {summary} #{tag}"


def should_skip_note(filepath):
    if filepath.name.startswith("_"):
        return True
    return False


def gather_category(category):
    cfg = CATEGORIES[category]
    d = cfg["dir"]
    if not d.exists():
        return []
    entries = []
    for f in sorted(d.glob("*.md")):
        if category == "notes" and should_skip_note(f):
            continue
        title, line = build_entry(category, f)
        entries.append((title.lower(), line))
    entries.sort(key=lambda t: t[0])
    return [line for _, line in entries]


def read_weekly_block(current_text):
    m = re.search(r"<!-- WEEKLY_INDEX:START -->.*?<!-- WEEKLY_INDEX:END -->", current_text, re.DOTALL)
    return m.group(0) if m else None


def rebuild():
    current_text = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
    weekly_block = read_weekly_block(current_text) or ""

    header = (
        "# Index\n\n"
        "The catalog of pages in this wiki, organized by category. "
        "Updated by `scripts/update_index.py` on every ingest.\n\n"
        "> Read this first when answering queries — it's the navigation aid for the whole wiki.\n"
        "> One entry per page. `★` marks a cluster hub — read it before drilling into cluster pages.\n\n"
    )

    parts = [header]
    if weekly_block:
        parts.append(weekly_block + "\n\n")

    for category in ["sources", "ahh-session-notes", "entities", "concepts", "notes"]:
        heading = CATEGORIES[category]["heading"]
        entries = gather_category(category)
        parts.append(f"{heading}\n")
        if entries:
            parts.append("\n".join(entries) + "\n\n")
        else:
            parts.append("_No pages yet._\n\n")

    INDEX_PATH.write_text("".join(parts).rstrip() + "\n", encoding="utf-8")
    counts = {c: len(gather_category(c)) for c in CATEGORIES}
    print("Rebuilt wiki/index.md:")
    for c, n in counts.items():
        print(f"  {c}: {n}")


def upsert_single(category, title, page_path, summary, tag=None):
    if category not in CATEGORIES:
        raise SystemExit(f"Unknown category: {category}. Choose from {list(CATEGORIES)}")
    current_text = INDEX_PATH.read_text(encoding="utf-8")
    heading = CATEGORIES[category]["heading"]
    tag = tag or DEFAULT_TAG[category]
    link = page_path
    if " " in str(Path(page_path).parent):
        link = f"<{page_path}>"
    new_line = f"- [{title}]({link}) — {summary} #{tag}"

    heading_pat = re.compile(rf"^{re.escape(heading)}\s*\n", re.MULTILINE)
    m = heading_pat.search(current_text)
    if not m:
        raise SystemExit(f"Heading {heading} not found in wiki/index.md — run --rebuild first.")

    section_start = m.end()
    next_heading = re.search(r"^## ", current_text[section_start:], re.MULTILINE)
    section_end = section_start + next_heading.start() if next_heading else len(current_text)
    section = current_text[section_start:section_end]

    section_lines = [l for l in section.split("\n") if l.strip()]
    section_lines = [l for l in section_lines if f"]({page_path})" not in l and f"](<{page_path}>)" not in l]
    section_lines.append(new_line)
    section_lines.sort(key=lambda l: re.search(r"\[(.+?)\]", l).group(1).lower() if re.search(r"\[(.+?)\]", l) else l)

    new_section = "\n".join(section_lines) + "\n\n"
    current_text = current_text[:section_start] + new_section + current_text[section_end:]
    INDEX_PATH.write_text(current_text, encoding="utf-8")
    print(f"Updated {heading} with: {new_line}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="Rescan all category directories and regenerate the full catalog")
    parser.add_argument("--category", choices=list(CATEGORIES), help="Category for a single-entry upsert")
    parser.add_argument("--title", help="Page title for a single-entry upsert")
    parser.add_argument("--page-path", help="Path (relative to repo root) for a single-entry upsert")
    parser.add_argument("--summary", help="One-line summary for a single-entry upsert")
    parser.add_argument("--tag", help="Override tag for a single-entry upsert")
    args = parser.parse_args()

    if args.rebuild:
        rebuild()
    elif args.category and args.title and args.page_path and args.summary:
        upsert_single(args.category, args.title, args.page_path, args.summary, args.tag)
    else:
        parser.error("Either --rebuild, or all of --category/--title/--page-path/--summary are required.")


if __name__ == "__main__":
    main()
