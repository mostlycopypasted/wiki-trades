#!/usr/bin/env python3
"""
Lint and auto-fix image embeds in wiki markdown reports.

Obsidian and CommonMark parsers fail when image alt text contains nested brackets
such as `![SK Hynix ([[000660.KS]]) Chart](path)`. This script detects and can
automatically strip nested brackets and backticks inside `![ ... ]`.

Usage:
    python3 scripts/lint_images.py              # Check all reports in wiki/reports/
    python3 scripts/lint_images.py --fix        # Automatically fix broken alt texts
    python3 scripts/lint_images.py <filepath>   # Check a specific file
"""

import re
import sys
from pathlib import Path


def check_and_fix_content(text: str, auto_fix: bool = False):
    issues = []
    lines = text.splitlines(keepends=True)
    new_lines = []

    for idx, line in enumerate(lines, 1):
        modified_line = line
        if "![" in line:
            # Pattern matching !\[ ... \](url)
            # Use regex to find image markdown embeds
            def fix_img(m):
                full_match = m.group(0)
                url_match = re.search(r"\(([^)]+)\)$", full_match)
                if not url_match:
                    return full_match
                url = url_match.group(1)
                alt_part = full_match[2 : -(len(url) + 3)]
                cleaned_alt = re.sub(r"[\[\]`]", "", alt_part).strip()
                if cleaned_alt != alt_part:
                    issues.append((idx, alt_part, cleaned_alt, url))
                return f"![{cleaned_alt}]({url})"

            # Greedy match to outer ](url) to handle nested brackets properly
            modified_line = re.sub(r"!\[.*?\]\([^\s)]+\)", fix_img, line)

        new_lines.append(modified_line if auto_fix else line)

    return issues, "".join(new_lines)


def process_file(filepath: Path, auto_fix: bool = False) -> bool:
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
        return False

    issues, fixed_content = check_and_fix_content(content, auto_fix=auto_fix)
    if issues:
        rel = filepath.relative_to(Path.cwd() if Path.cwd() in filepath.parents else filepath.parent)
        print(f"❌ {rel}:")
        for line_no, old_alt, new_alt, url in issues:
            print(f"   Line {line_no}: ![{old_alt}]({url})")
            if auto_fix:
                print(f"   --> Fixed to: ![{new_alt}]({url})")
        if auto_fix:
            filepath.write_text(fixed_content, encoding="utf-8")
        return False
    return True


def main():
    auto_fix = "--fix" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--fix"]

    if args:
        target_paths = [Path(a) for a in args]
    else:
        root = Path(__file__).resolve().parent.parent / "wiki" / "reports"
        target_paths = list(root.rglob("*.md"))

    total_files = 0
    clean_files = 0
    for path in sorted(target_paths):
        if path.is_file() and path.suffix == ".md":
            total_files += 1
            if process_file(path, auto_fix=auto_fix):
                clean_files += 1

    if clean_files == total_files:
        print(f"✅ All {total_files} markdown reports have clean, valid image embeds.")
        sys.exit(0)
    else:
        status = "Fixed issues in" if auto_fix else "Found issues in"
        print(f"\n⚠️  {status} {total_files - clean_files} of {total_files} files.")
        sys.exit(0 if auto_fix else 1)


if __name__ == "__main__":
    main()
