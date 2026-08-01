
import os, re
wiki_root = '/Users/chriseah/obsidian/wiki-trades'
wiki_dir = os.path.join(wiki_root, 'wiki')

file_map = {}
for root, dirs, files in os.walk(wiki_dir):
    for f in files:
        if f.endswith('.md'):
            rel_path = os.path.relpath(os.path.join(root, f), wiki_dir)
            file_map[f] = rel_path
            file_map[f[:-3].lower()] = rel_path

def get_rel_path(source_file, target_file_rel):
    source_dir = os.path.dirname(os.path.relpath(source_file, wiki_dir))
    if source_dir == '.': return target_file_rel
    return '../' * len(source_dir.split('/')) + target_file_rel

def replace_wikilinks(match, file_path):
    text = match.group(1)
    key = text.lower()
    if key in file_map:
        return f'[{text}]({get_rel_path(file_path, file_map[key])})'
    return match.group(0)

wiki_link_pattern = re.compile(r'\[\[([^\]]+)\]\]')

for root, dirs, files in os.walk(wiki_dir):
    for f in files:
        if f.endswith('.md'):
            file_path = os.path.join(root, f)
            with open(file_path, 'r') as file:
                content = file.read()
            new_content = wiki_link_pattern.sub(lambda m: replace_wikilinks(m, file_path), content)
            if new_content != content:
                with open(file_path, 'w') as file:
                    file.write(new_content)
                print(f'Fixed links in {f}')

# Fix index.md
path = '/Users/chriseah/obsidian/wiki-trades/wiki/index.md'
with open(path, 'r') as f:
    content = f.read()
new_content = re.sub(r'\]\(\.\./', r'](', content)
with open(path, 'w') as f:
    f.write(new_content)
