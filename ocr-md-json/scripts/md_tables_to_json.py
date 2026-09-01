#!/usr/bin/env python3
"""md_tables_to_json.py — parse every Markdown table into a structured JSON file.

Output schema:
    {"title": <doc title>, "table_count": N, "tables": [
        {"name":"<slug>","title":"<nearest heading>","headers":[...],
         "rows":[{"col":value,...}]}
    ]}

Usage:
    py md_tables_to_json.py "record.md" -o "tables.json"
"""

import json
import re
import argparse


def _clean(cell):
    s = cell.strip()
    s = re.sub(r'\*\*(.*?)\*\*', r'\1', s)      # bold
    s = re.sub(r'\*(.*?)\*', r'\1', s)          # italic
    s = re.sub(r'`(.*?)`', r'\1', s)            # inline code
    s = re.sub(r'<[^>]+>', '', s)               # html
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def _parse_table(lines):
    rows = []
    for ln in lines:
        ln = ln.strip()
        if not ln.startswith('|'):
            continue
        cells = [c for c in ln.split('|')]
        cells = cells[1:-1] if len(cells) >= 2 else cells
        rows.append([_clean(c) for c in cells])
    if not rows:
        return None
    header = rows[0]
    sep = None
    for i, r in enumerate(rows):
        if all(re.fullmatch(r':?-{2,}:?', c or '') for c in r):
            sep = i
            break
    data_rows = rows[sep + 1:] if sep is not None else rows[1:]
    objs = []
    for r in data_rows:
        if len(r) < len(header):
            r = r + [''] * (len(header) - len(r))
        if all(not c for c in r):
            continue
        objs.append({header[i]: r[i] for i in range(len(header)) if header[i]})
    return {'headers': [h for h in header if h], 'rows': objs}


def run(md_path):
    with open(md_path, encoding='utf-8') as fh:
        lines = fh.read().splitlines()
    tables, last = [], None
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        m = re.match(r'^(#{1,6})\s+(.*)$', ln)
        if m:
            last = _clean(m.group(2))
            i += 1
            continue
        if ln.strip().startswith('|'):
            block = []
            while i < n and lines[i].strip().startswith('|'):
                block.append(lines[i])
                i += 1
            tbl = _parse_table(block)
            if tbl:
                name = re.sub(r'[^A-Za-z0-9]+', '_', last or 'table').strip('_').lower() or 'table'
                tbl['name'] = name
                tbl['title'] = last or ''
                if any(t['title'] == tbl['title'] for t in tables):
                    tbl['name'] = name + '_' + str(sum(1 for t in tables if t['title'] == tbl['title']) + 1)
                tables.append(tbl)
            continue
        i += 1
    return {'title': md_path, 'table_count': len(tables), 'tables': tables}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('md')
    ap.add_argument('-o', '--out', required=True)
    args = ap.parse_args()
    doc = run(args.md)
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    print('tables:', doc['table_count'], '->', args.out)


if __name__ == '__main__':
    main()
