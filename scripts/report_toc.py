"""Shared Table-of-Contents builder for wiki/reports/*.md files.

Obsidian's renderer follows CommonMark, not GitHub-Flavored Markdown: it does
NOT generate or resolve GFM-style slugified heading anchors. The only
reliable way to link to a heading within the same note is Obsidian's native
wikilink heading syntax, [[#Exact Heading Text]], using the heading's
literal text verbatim -- do not slugify, lowercase, or strip anything.

Caller contract: headings must not themselves contain [[wikilinks]] (e.g. a
[[TICKER]] mention baked into a "## " line) -- nested double-brackets break
wikilink parsing. Keep "## " lines plain-text only.
"""
import re

TOC_START = "<!-- TOC:START -->"
TOC_END = "<!-- TOC:END -->"

_H2_RE = re.compile(r"^##[ \t]+(?!#)(.+?)\s*$", re.MULTILINE)
_TOC_BLOCK_RE = re.compile(re.escape(TOC_START) + r".*?" + re.escape(TOC_END) + r"\n?", re.DOTALL)
_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def build_toc(markdown_text: str) -> str:
    """TOC_START/END-bracketed block linking to every H2 in markdown_text.
    Returns "" if there are no H2 headings."""
    headings = [m.group(1).strip() for m in _H2_RE.finditer(markdown_text)]
    if not headings:
        return ""
    lines = [TOC_START, "**📑 Table of Contents**", ""]
    lines += [f"- [[#{h}]]" for h in headings]
    lines.append(TOC_END)
    return "\n".join(lines) + "\n"


def upsert_toc(markdown_text: str) -> str:
    """Recompute the TOC from all current H2 headings, strip any existing
    TOC block, reinsert the fresh one right after the H1 title line. Use
    this for append-only reports where the TOC must stay in sync.

    Correctly skips a leading YAML frontmatter block (--- ... ---), if
    present, before looking for the H1 title -- inserting right after line 1
    unconditionally would land the TOC above the frontmatter entirely on any
    report that has one (caught via testing on market_sentiment.py's output,
    which always has frontmatter before its H1 title)."""
    toc = build_toc(markdown_text)
    body = _TOC_BLOCK_RE.sub("", markdown_text, count=1)
    if not toc:
        return body

    fm_match = _FRONTMATTER_RE.match(body)
    prefix = fm_match.group(0) if fm_match else ""
    rest_after_prefix = body[fm_match.end():] if fm_match else body
    stripped = rest_after_prefix.lstrip("\n")
    blank_lines_before_title = "\n" * (len(rest_after_prefix) - len(stripped))

    title_line, sep, rest = stripped.partition("\n")
    return f"{prefix}{blank_lines_before_title}{title_line}{sep}\n{toc}\n{rest.lstrip(chr(10))}"
