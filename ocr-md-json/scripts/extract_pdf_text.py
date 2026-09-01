#!/usr/bin/env python3
"""extract_pdf_text.py — extract the EMBEDDED text layer from a native PDF.

Deterministic (no OCR): zlib-decompress each content stream and map the
`<hex> Tj` glyph codes through the font's ToUnicode CMap. This is the fast,
exact path for system-generated PDFs (hospital/financial reports) that carry a
real text layer.

Usage:
    py extract_pdf_text.py "in.pdf"            # print to stdout
    py extract_pdf_text.py "in.pdf" -o out.txt # write to file

Stdlib only (zlib, re). No pypdf/OCR libraries needed.
"""

import re
import zlib
import argparse
import sys


def _dec(raw):
    for r in (raw, raw[1:]):
        try:
            return zlib.decompress(r)
        except Exception:
            continue
    return None


def _get_obj(data, num):
    om = re.search((rb'(?<!\d)' + str(num).encode() + rb'\s+0\s+obj(.*?)endobj'),
                   data, re.DOTALL)
    return om.group(1) if om else None


def _parse_cmap(text):
    """glyph code (int) -> unicode string."""
    mapping = {}
    for m in re.finditer(rb'beginbfchar(.*?)endbfchar', text, re.DOTALL):
        for mm in re.finditer(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', m.group(1)):
            mapping[int(mm.group(1), 16)] = chr(int(mm.group(2), 16))
    for m in re.finditer(rb'beginbfrange(.*?)endbfrange', text, re.DOTALL):
        body = m.group(1)
        for mm in re.finditer(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', body):
            lo, hi, base = int(mm.group(1), 16), int(mm.group(2), 16), int(mm.group(3), 16)
            for i in range(lo, hi + 1):
                mapping[i] = chr(base + (i - lo))
        for mm in re.finditer(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]', body, re.DOTALL):
            lo = int(mm.group(1), 16)
            for i, s in enumerate(re.findall(rb'<([0-9A-Fa-f]+)>', mm.group(3))):
                mapping[lo + i] = chr(int(s, 16))
    return mapping


def _build_font_maps(data):
    maps = {}
    for m in re.finditer(rb'/(F\d+)\s+(\d+)\s+0\s+R', data):
        fname, fnum = m.group(1).decode(), int(m.group(2))
        body = _get_obj(data, fnum)
        if not body:
            continue
        tu = re.search(rb'/ToUnicode\s+(\d+)\s+0\s+R', body)
        if not tu:
            df = re.search(rb'/DescendantFonts\s*\[(\d+)\s+0\s+R\]', body)
            if df:
                dbody = _get_obj(data, int(df.group(1)))
                if dbody:
                    tu = re.search(rb'/ToUnicode\s+(\d+)\s+0\s+R', dbody)
        if not tu:
            continue
        tbody = _get_obj(data, int(tu.group(1)))
        if not tbody:
            continue
        sm = re.search(rb'<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream', tbody, re.DOTALL)
        if not sm:
            continue
        cm = _dec(sm.group(2))
        if cm is None:
            continue
        maps[fname] = _parse_cmap(cm)
    return maps


def extract_text(path):
    with open(path, 'rb') as fh:
        data = fh.read()
    fontmaps = _build_font_maps(data)
    patterns = re.compile(
        rb'/(F\d+)\s+[\d.]+\s+Tf|\[([^\]]*)\]\s*TJ|<([0-9A-Fa-f]+)>\s*Tj|\(((?:[^()\\]|\\.)*)\)\s*Tj',
        re.DOTALL)
    out = []
    for m in re.finditer(rb'/Contents\s+(\d+)\s+0\s+R', data):
        body = _get_obj(data, int(m.group(1)))
        if not body:
            continue
        sm = re.search(rb'<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream', body, re.DOTALL)
        if not sm:
            continue
        content = _dec(sm.group(2))
        if content is None:
            continue
        active = None
        for mm in patterns.finditer(content):
            if mm.group(1):
                active = fontmaps.get(mm.group(1).decode())
            elif mm.group(2) is not None:
                for ch in re.finditer(rb'<([0-9A-Fa-f]+)>', mm.group(2)):
                    c = int(ch.group(1), 16)
                    if active and c in active:
                        out.append(active[c])
            elif mm.group(3) is not None:
                c = int(mm.group(3), 16)
                if active and c in active:
                    out.append(active[c])
            elif mm.group(4) is not None:
                out.append(mm.group(4).decode('latin-1'))
    return ''.join(out) if out else ''


def collapse_hex(s):
    """Collapse double-encoded 00XX -> byte (fixes '00520061...' garbage)."""
    return re.sub(r'00([0-9A-Fa-f]{2})',
                  lambda m: chr(int(m.group(1), 16)) if int(m.group(1), 16) else '',
                  s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf')
    ap.add_argument('-o', '--out', default=None)
    args = ap.parse_args()
    txt = extract_text(args.pdf)
    txt = collapse_hex(txt)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as fh:
            fh.write(txt)
        print('extracted', len(txt), 'chars ->', args.out)
    else:
        sys.stdout.write(txt)
        sys.stdout.write('\n')


if __name__ == '__main__':
    main()
