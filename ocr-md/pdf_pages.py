#!/usr/bin/env python3
"""ocr-md preset helper: per-page PDF handling for ocr.ps1.

Usage: py pdf_pages.py <in.pdf> <out_dir> [dpi] [minchars]

For each page: if the embedded text layer passes the quality gate, write
page-NNN.txt (mode=textlayer); otherwise render page-NNN.png at dpi (mode=raster).
Writes manifest pdf_pages.json: [{"page":1,"mode":"...","file":"page-001.txt"}]

Text-layer gate: len(text) >= 600 (any content), or len(text) >= minchars
(default 150) AND the text contains at least one digit (blocks near-empty or
boilerplate-only layers from being trusted).

Requires pypdfium2:  py -m pip install --user pypdfium2
"""
import json
import os
import sys


def main(argv):
    if len(argv) < 3:
        print("usage: pdf_pages.py <in.pdf> <out_dir> [dpi] [minchars]", file=sys.stderr)
        return 2
    src, out = argv[1], argv[2]
    dpi = int(argv[3]) if len(argv) > 3 else 300
    minchars = int(argv[4]) if len(argv) > 4 else 150
    try:
        import pypdfium2 as pdfium
    except ImportError as e:
        print("pypdfium2 missing (install: py -m pip install --user pypdfium2): %s" % e, file=sys.stderr)
        return 3
    if not os.path.isfile(src):
        print("not a file: %s" % src, file=sys.stderr)
        return 2
    os.makedirs(out, exist_ok=True)
    doc = pdfium.PdfDocument(src)
    manifest = []
    for i in range(len(doc)):
        page = doc[i]
        text = ""
        try:
            tp = page.get_textpage()
            try:
                text = tp.get_text_range()
            except AttributeError:
                text = tp.extract_text()  # older pypdfium2 API
        except Exception:
            text = ""
        text = (text or "").strip()
        ok = (len(text) >= 600) or (len(text) >= minchars and any(c.isdigit() for c in text))
        if ok:
            fname = "page-%03d.txt" % (i + 1)
            with open(os.path.join(out, fname), "w", encoding="utf-8") as f:
                f.write(text)
            mode = "textlayer"
        else:
            fname = "page-%03d.png" % (i + 1)
            bmp = page.render(scale=dpi / 72.0)
            bmp.to_pil().save(os.path.join(out, fname))
            mode = "raster"
        manifest.append({"page": i + 1, "mode": mode, "file": fname})
    with open(os.path.join(out, "pdf_pages.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    nt = sum(1 for m in manifest if m["mode"] == "textlayer")
    print("pages=%d textlayer=%d raster=%d" % (len(manifest), nt, len(manifest) - nt))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
