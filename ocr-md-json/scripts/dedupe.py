#!/usr/bin/env python3
"""dedupe.py — find identical files in a folder by content hash.

Photo exports often contain the same page saved under several names (or the
same bytes re-exported). Group them so you only transcribe each unique image
once.

Usage:
    py dedupe.py "folder"
"""

import os
import glob
import hashlib
import argparse


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder')
    ap.add_argument('-e', '--ext', default=None,
                    help='restrict to one extension, e.g. jpg')
    args = ap.parse_args()
    pattern = os.path.join(args.folder, '*')
    groups = {}
    for f in glob.glob(pattern):
        if not os.path.isfile(f):
            continue
        if args.ext and not f.lower().endswith('.' + args.ext.lower()):
            continue
        groups.setdefault(md5(f), []).append(os.path.basename(f))
    uniq = sum(1 for v in groups.values())
    print('unique:', uniq, '| files:', sum(len(v) for v in groups.values()))
    for names in groups.values():
        if len(names) > 1:
            print('  [' + str(len(names)) + 'x]', names)


if __name__ == '__main__':
    main()
