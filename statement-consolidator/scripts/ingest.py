#!/usr/bin/env python3
"""ingest.py - read a bank/credit-card statement (CSV or XLSX) into a RAW
statement JSON.

Model-free. Detects the header row among the institution's title/branded rows,
captures summary lines (opening/closing balance, period) into the `statement`
block, and emits the per-transaction grid with every original cell preserved in
`raw`. NOTHING is dropped: summary lines that are lifted off the transaction
table are recorded verbatim in `skipped_meta_lines` + `statement.summary_lines`,
and rows that are neither a clean transaction nor a known summary line are still
emitted (and will later land in `extras`/`raw` with an unresolved flag).

Dependencies: standard library for CSV; `openpyxl` for XLSX (the one install).

Usage:
    python ingest.py <statement.csv|xlsx> -o out.raw.json
        [--header-row N] [--institution NAME] [--account-type checking|savings|credit|loan]
        [--currency USD] [--account-masked '****4821']

Output contract (see reference/CANONICAL-SCHEMA.md for the full statement
envelope): {source_file, account hints, header_row, columns_raw, statement{},
rows:[{raw:{...}}], row_count, skipped_meta_lines[], header_candidates{}}
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import common as C  # noqa: E402


# ---- reading ---------------------------------------------------------------

def read_grid(path):
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            return [list(row) for row in csv.reader(f)]
    if ext in (".xlsx", ".xlsm", ".xltx", ".xltm"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise SystemExit(
                "openpyxl is required to read .xlsx. Install it once with:\n"
                "    py -m pip install --user openpyxl\n"
                "(CSV input needs no third-party packages.)"
            )
        wb = load_workbook(path, data_only=True, read_only=True)
        ws = wb.active
        grid = [[("" if c is None else c) for c in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
        return grid
    raise SystemExit(f"Unsupported file type: {ext!r} (expected .csv / .xlsx)")


# ---- header detection ------------------------------------------------------

def find_header_row(grid, hint=None):
    """Return (header_index, candidates). A strong header row has a date-word
    AND an amount-word among its (normalized) cells; pick the highest-scoring
    strong row (tie -> earliest). Falls back to the highest-scoring row."""
    candidates = {}
    for i, row in enumerate(grid):
        cells = [("" if c is None else str(c)) for c in row]
        normed = [C.norm_header(c) for c in cells]
        hit = set()
        for n in normed:
            if not n:
                continue
            for canon, syns in C.SYNONYMS.items():
                if n in syns:
                    hit.add(canon)
                    break
        nonempty = sum(1 for c in cells if c.strip())
        has_date = "date" in hit
        has_amount = len(hit & {"amount", "amount_debit", "amount_credit"}) >= 1
        strong = has_date and has_amount
        hint_match = bool(hint) and C.norm_header(hint) in normed
        score = len(hit)
        candidates[i] = {"score": score, "hit": sorted(hit),
                         "strong": strong, "hint_match": hint_match, "nonempty": nonempty}
    best_i, best_score = None, -1
    for i in sorted(candidates):
        c = candidates[i]
        if c["strong"] and (c["score"] > best_score or
                            (c["score"] == best_score and c["hint_match"] and best_i is not None and not candidates[best_i]["hint_match"])):
            best_score, best_i = c["score"], i
    if best_i is None:
        for i in sorted(candidates):
            if candidates[i]["score"] > best_score:
                best_score, best_i = candidates[i]["score"], i
    if best_i is None:
        raise SystemExit("Could not detect a header row. Pass --header-row N (0-based) explicitly.")
    return best_i, candidates


# ---- statement meta --------------------------------------------------------

_OPEN_RE = r"\b(opening|starting|beginning|beg)\s*(balance|bal)\b\s*[:\-]?\s*"
_CLOSE_RE = r"\b(closing|ending|final|current)\s*(balance|bal)\b\s*[:\-]?\s*"
_PERIOD_RE = r"\b(statement\s*period|period|for\s*the\s*period)\b\s*[:\-]?\s*"
_SUMMARY_RE = r"\b(statement period|opening balance|starting balance|closing balance|ending balance|total|beginning balance|balance|period)\b"
_NUM_RE = re.compile(r"[-\s]?\(?\d[\d,]*(?:\.\d+)?\)?")
_DATE_TOK_RE = re.compile(r"\d{1,2}\s*[\/\-.]\s*\d{1,2}\s*[\/\-.]\s*\d{2,4}|\d{4}-\d{1,2}-\d{1,2}")


def _grab_money(text_after_pattern):
    m = _NUM_RE.search(text_after_pattern)
    if not m:
        return None
    try:
        d = C.parse_money(m.group(0))
        return None if d is None else float(d)
    except ValueError:
        return None


def extract_statement_meta(grid, date_fmt=None):
    """Scan every row for summary lines (opening/closing balance, period).
    Returns (statement_dict, meta_row_indices). Nothing is dropped: each lifted
    line is kept verbatim in statement.summary_lines."""
    statement = {"period_start": None, "period_end": None,
                 "opening_balance": None, "closing_balance": None,
                 "printed_total": None, "summary_lines": []}
    meta_rows = set()
    import re as _re
    for i, row in enumerate(grid):
        joined = " ".join(str(c) for c in row if c is not None)
        stripped = joined.strip()
        if not stripped:
            continue
        low = joined.lower()
        added = False
        m = _re.search(_OPEN_RE, joined, _re.I)
        if m and statement["opening_balance"] is None:
            v = _grab_money(joined[m.end():])
            if v is not None:
                statement["opening_balance"] = v
                statement["summary_lines"].append(stripped)
                added = True
        m = _re.search(_CLOSE_RE, joined, _re.I)
        if m and statement["closing_balance"] is None:
            v = _grab_money(joined[m.end():])
            if v is not None:
                statement["closing_balance"] = v
                statement["summary_lines"].append(stripped)
                added = True
        m = _re.search(_PERIOD_RE, joined, _re.I)
        if m:
            dates = [C.parse_date(t.strip(), date_fmt) for t in _DATE_TOK_RE.findall(joined[m.end():])]
            dates = [d for d in dates if d]
            if len(dates) >= 2:
                statement["period_start"] = dates[0]
                statement["period_end"] = dates[-1]
                statement["summary_lines"].append(stripped)
                added = True
            elif len(dates) == 1 and (statement["period_start"] is None or statement["period_end"] is None):
                if statement["period_start"] is None:
                    statement["period_start"] = dates[0]
                else:
                    statement["period_end"] = dates[0]
                statement["summary_lines"].append(stripped)
                added = True
        if added:
            meta_rows.add(i)
    return statement, meta_rows


def _is_meta_row(row, date_fmt=None):
    """A row is 'meta' if it has no parseable date AND it matches a summary
    keyword line (so we lift it off the transaction table and into the
    statement block)."""
    cells = [("" if c is None else str(c)) for c in row]
    nonempty = sum(1 for c in cells if c.strip())
    if nonempty < 1:
        return False
    if any(c and C.parse_date(c, date_fmt) is not None for c in cells):
        return False  # has a date -> it is a transaction row
    joined = " ".join(cells).lower()
    return bool(re.search(_SUMMARY_RE, joined))


# ---- main ------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Statement CSV/XLSX -> raw statement JSON")
    ap.add_argument("input")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--header-row", type=int, default=None, help="0-based header row override")
    ap.add_argument("--institution", default=None)
    ap.add_argument("--account-type", default=None)
    ap.add_argument("--currency", default=None)
    ap.add_argument("--account-masked", default=None)
    args = ap.parse_args(argv)

    grid = read_grid(args.input)
    # strip fully-empty leading/trailing rows
    while grid and all((c is None or str(c).strip() == "") for c in grid[0]):
        grid = grid[1:]
    while grid and all((c is None or str(c).strip() == "") for c in grid[-1]):
        grid = grid[:-1]
    if not grid:
        raise SystemExit(f"no data in {args.input}")

    header_i = args.header_row if args.header_row is not None else None
    if header_i is None:
        header_i, candidates = find_header_row(grid, hint=None)
    else:
        candidates = find_header_row(grid, hint=None)[1]
        if not (0 <= header_i < len(grid)):
            raise SystemExit(f"--header-row {header_i} is out of range (file has {len(grid)} rows)")

    statement, meta_rows = extract_statement_meta(grid)
    columns_raw = [("" if c is None else str(c)).strip() for c in grid[header_i]]
    ncol = len(columns_raw)

    rows = []
    skipped_meta = []
    for i in range(header_i + 1, len(grid)):
        row = grid[i]
        # pad / truncate to ncol
        padded = list(row[:ncol])
        while len(padded) < ncol:
            padded.append("")
        cells = [("" if c is None else str(c)).strip() for c in padded]
        if not any(cells):
            continue
        if i in meta_rows or _is_meta_row(row):
            line = " ".join(c for c in cells if c)
            if line:
                skipped_meta.append(line)
            continue
        raw = {}
        for h, v in zip(columns_raw, cells):
            raw[h] = v
        rows.append({"raw": raw})

    out = {
        "source_file": Path(args.input).name,
        "injected_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "institution": args.institution,
        "account_type": args.account_type,
        "currency": args.currency,
        "account_masked": args.account_masked,
        "header_row": header_i,
        "columns_raw": columns_raw,
        "statement": statement,
        "rows": rows,
        "row_count": len(rows),
        "skipped_meta_lines": skipped_meta,
        "header_candidates": {str(k): v for k, v in candidates.items()},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[ingest] {args.input}")
    print(f"[ingest]   header_row={header_i}  columns={columns_raw}")
    print(f"[ingest]   rows={len(rows)}  meta_lines={len(skipped_meta)}")
    st = statement
    print(f"[ingest]   statement: period={st.get('period_start')}..{st.get('period_end')} "
          f"open={st.get('opening_balance')} close={st.get('closing_balance')}")
    if not st.get("opening_balance") or not st.get("closing_balance"):
        print("[ingest]   note: opening/closing not auto-detected - pass via mapping/--flags or rely on row-level reconciliation")
    print(f"[ingest]   wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
