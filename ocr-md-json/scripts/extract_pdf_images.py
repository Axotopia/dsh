#!/usr/bin/env python3
"""extract_pdf_images.py — pull the page images out of a scanned/image PDF.

For PDFs that have NO embedded text layer (scans, image-only reports), extract
each page's image so a vision model can read it. Handles JPEG (DCTDecode)
images and raw FlateDecode images (RGB/gray).

Usage:
    py extract_pdf_images.py "scan.pdf" -out "pages"

Requires Pillow (py -m pip install --user pillow). stdlib otherwise.
"""

import re
import io
import os
import zlib
import argparse
from PIL import Image


def _dec(raw):
    for r in (raw, raw[1:]):
        try:
            return zlib.decompress(r)
        except Exception:
            continue
    return None


def _streams(data):
    """Yield (header, raw) for each stream in document order."""
    for m in re.finditer(rb'stream\r?\n(.*?)\r?\nendstream', data, re.DOTALL):
        raw = m.group(1)
        hdr = data[max(0, m.start() - 400):m.start()]
        dm = re.findall(rb'<<(.*?)>>', hdr, re.DOTALL)
        yield (dm[-1] if dm else b''), raw


def _save_jpeg(raw, path):
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
        img.save(path)
        return img.size
    except Exception:
        return None


def extract(pdf, outdir):
    os.makedirs(outdir, exist_ok=True)
    data = open(pdf, 'rb').read()
    count = 0
    for header, raw in _streams(data):
        if b'/Image' not in header:
            continue
        if b'/DCTDecode' in header:
            size = _save_jpeg(raw, os.path.join(outdir, 'page_%02d.jpg' % count))
            if size:
                count += 1
                continue
        if b'/FlateDecode' in header:
            bb = _dec(raw)
            if bb:
                w = re.search(rb'/Width\s+(\d+)', header)
                h = re.search(rb'/Height\s+(\d+)', header)
                if w and h:
                    W, H = int(w.group(1)), int(h.group(1))
                    for mode, ch in [('RGB', 3), ('L', 1)]:
                        if len(bb) >= W * H * ch:
                            try:
                                Image.frombytes(mode, (W, H), bb[:W * H * ch]).save(
                                    os.path.join(outdir, 'page_%02d.png' % count))
                                count += 1
                            except Exception:
                                pass
                            break
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf')
    ap.add_argument('-out', required=True)
    args = ap.parse_args()
    n = extract(args.pdf, args.out)
    print('extracted', n, 'image(s) ->', args.out)


if __name__ == '__main__':
    main()
