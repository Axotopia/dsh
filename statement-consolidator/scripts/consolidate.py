#!/usr/bin/env python3
"""consolidate.py - merge many canonical statement JSON files into ONE big file
with the same format, run the model-free reconciliation gate, and emit the
deliverable (JSON + CSV, and XLSX when openpyxl is installed).

Deterministic. No network, no PHI beyond what the user already put in the input
files (account numbers arrive pre-masked from ingest).

Checks (see reference/RECONCILIATION.md):
  1. close-check          opening + sum(amount) == closing      (per statement)
  2. continuity           prev.closing == next.opening          (per account)
  3. duplicates           same row content in >1 distinct file  (re-reads + double-import)
  4. coverage             months present per account vs. the year(s) in scope
  5. exceptions           accumulated anomalies (unparsed, unmapped, dup flags)

Usage:
    python consolidate.py -o out.xlsx [inputs ...] [--year 2025] [--work-dir work]

Inputs may be: explicit .json files, a directory (all *.canonical.json inside),
or a shell-glob pattern.
"""
from __future__ import annotations

import argparse
import csv
import glob as _glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import common as C  # noqa: E402


# ---- money in cents (integer arithmetic, no float drift) --------------------

def _c(x):
    if x is None:
        return None
    return int(round(float(x) * 100))


def cents(x):
    if x is None:
        return 0
    return int(round(float(x) * 100))


def money(c):
    return round(c / 100.0, 2)


# ---- input gathering --------------------------------------------------------

def gather_inputs(inputs, work_dir):
    files = []
    if not inputs:
        if work_dir:
            files += sorted(glob.glob(os.path.join(work_dir, "*.canonical.json")))
        else:
            raise SystemExit("No inputs. Pass .json files, a directory, a glob, or --work-dir.")
        if not files:
            raise SystemExit(f"No *.canonical.json under {work_dir}")
        return files
    for p in inputs:
        if os.path.isdir(p):
            files += sorted(glob.glob(os.path.join(p, "*.canonical.json")))
        elif os.path.isfile(p):
            files += [p]
        else:
            files += sorted(_glob.glob(p))
    return files


def load_canonical(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    obj["__path"] = path
    return obj


# ---- checks -----------------------------------------------------------------

def close_check(stmt, rows):
    opening = stmt.get("opening_balance")
    closing = stmt.get("closing_balance")
    if opening is None or closing is None:
        return {"status": "na", "reason": "missing opening or closing balance"}
    net = sum(cents(r["amount"]) for r in rows if r.get("amount") is not None)
    expected = cents(opening) + net
    actual = cents(closing)
    ok = abs(actual - expected) <= 1
    return {
        "status": "pass" if ok else "fail",
        "opening": money(cents(opening)),
        "closing": money(cents(closing)),
        "expected": money(expected),
        "actual": money(cents(closing)),
        "delta": money(actual - expected),
        "n_amounts": sum(1 for r in rows if r.get("amount") is not None),
    }


def continuity(inputs_sorted, by_account):
    """For each account, sort its statements by period_start; each consecutive
    pair's prev.closing should equal next.opening. Also flag month gaps."""
    findings = []
    for acc, items in by_account.items():
        seq = sorted(items, key=lambda x: (x["period_start"] is None, x["period_start"] or "", x["source_file"]))
        for a, b in zip(seq, seq[1:]):
            pc = a["statement"].get("closing_balance")
            no = b["statement"].get("opening_balance")
            if pc is None or no is None:
                continue
            ok = abs(cents(pc) - cents(no)) <= 1
            findings.append({
                "account": acc,
                "status": "pass" if ok else "fail",
                "pair": f"{Path(a['source_file']).name} -> {Path(b['source_file']).name}",
                "prev_closing": money(cents(pc)),
                "next_opening": money(cents(no)),
                "delta": money(cents(no) - cents(pc)),
            })
    return findings


def detect_duplicates(rows):
    """rows: global list of canonical rows (each with __file). Flags:
       - exact-id re-reads (same id in the input set)
       - cross-file same-content (same identity keys across >1 distinct file)
    Returns (rows_with_dup_flags, dup_findings)."""
    by_id = {}
    id_count = 0
    for r in rows:
        id_count += 1
        by_id.setdefault(r["id"], []).append(r)
        r["_reads"] = None
    dup_findings = []

    def identity_key(r):
        amt = r.get("amount")
        if amt is None and r.get("amount_debit") is not None:
            amt = -r["amount_debit"]
        if amt is None and r.get("amount_credit") is not None:
            amt = r["amount_credit"]
        return (r.get("source_institution"), r.get("account_masked"),
                r.get("date"), round(float(amt) * 100) if amt is not None else None,
                C.norm_desc(r.get("description")))

    groups = {}
    for r in rows:
        groups.setdefault(identity_key(r), []).append(r)

    for r in rows:
        k = r["_k"] = identity_key(r)
        files_with = {q["__file"] for q in rows if identity_key(q) == k}
        if len(files_with) >= 2:
            r["_dup"] = True
            r["_dup_files"] = sorted({Path(q["__file"]).name for q in rows if identity_key(q) == k and q is not r})
        else:
            r.setdefault("_dup", False)

    for r in rows:
        r.pop("_k", None)
        r["_dup_files"] = [f for f in r.get("_dup_files", []) if f]
        r.setdefault("_dup_files", [])

    for k, grp in groups.items():
        ids = list({r["id"] for r in grp})
        files = sorted({Path(r["__file"]).name for r in grp})
        if len(ids) >= 2 or len(files) >= 2:
            for r in grp:
                r["_dup"] = True
                r["_dup_files"] = sorted({Path(q["__file"]).name for q in grp if q is not r})
            dup_findings.append({
                "key": [None if x is None else str(x) for x in k],
                "row_ids": ids,
                "files": files,
                "count": len(grp),
                "n_distinct_reads": len(ids),
            })
    return rows, dup_findings


def coverage(rows, by_account, year=None, min_year=None, max_year=None):
    findings = []
    for acc, items in by_account.items():
        acc_rows = [r for r in items]
        months = set()
        for r in acc_rows:
            if r.get("date"):
                months.add(r["date"][:7])
        if not months:
            continue
        dates = sorted(r["date"] for r in acc_rows if r.get("date"))
        dmin, dmax = datetime.fromisoformat(dates[0]), datetime.fromisoformat(dates[-1])
        span = range(dmin.year * 12 + dmin.month, dmax.year * 12 + dmax.month + 1)
        expected = set()
        for m in span:
            y, mo = divmod(m - 1, 12)
            expected.add(f"{y:04d}-{mo:02d}")
        missing = sorted(expected - months)
        if year is not None:
            year_prefix = f"{year:04d}-"
            year_expected = {f"{year:04d}-{mm:02d}" for mm in range(1, 13)}
            year_expected = year_expected & expected  # only months in the account's lifetime
            missing = sorted(year_expected - months)
        if missing:
            findings.append({"account": acc, "year": year or (dmin.year, dmax.year), "missing": missing})
    return findings


def summarize_account(acc, rows):
    total_in_c = sum(cents(r["amount"]) for r in rows if (r.get("amount") or 0) > 0)
    total_out_c = sum(cents(-r["amount"]) for r in rows if (r.get("amount") or 0) < 0)
    fees_c = sum(cents(r["fee"]) for r in rows if r.get("fee") is not None)
    interest_c = sum(cents(r["interest"]) for r in rows if r.get("interest") is not None)
    dates = sorted(r["date"] for r in rows if r.get("date"))
    n = len({r["id"] for r in rows})
    dups = sum(1 for r in rows if r.get("_dup"))
    return {
        "account": acc,
        "institution": rows[0].get("source_institution"),
        "account_masked": rows[0].get("account_masked"),
        "account_type": rows[0].get("account_type"),
        "currency": rows[0].get("currency"),
        "n_rows": n,
        "n_duplicate_flagged": dups,
        "min_date": dates[0] if dates else None,
        "max_date": dates[-1] if dates else None,
        "total_in": money(total_in_c),
        "total_out": money(total_out_c),
        "net": money(total_in_c - total_out_c),
        "total_fees": money(fees_c),
        "total_interest": money(interest_c),
    }


# ---- output -----------------------------------------------------------------

def _sheet(ws, headers, rows_of_dicts):
    ws.append(headers)
    for row in rows_of_dicts:
        ws.append([_fmt(row.get(h)) for h in headers])
    _sheet_set_widths(ws, headers, rows_of_dicts)

def _set_width(ws, idx, base):
    from openpyxl.utils import get_column_letter
    ws.column_dimensions[get_column_letter(idx)].width = base


# column widths (rough)
def _sheet_set_widths(ws, headers, rows_of_dicts):
    for idx, h in enumerate(headers, start=1):
        base = min(60, max(len(str(h)), 8))
        if rows_of_dicts:
            base = max(base, max(len(str(_fmt(r.get(h)))) for r in rows_of_dicts) + 2)
        base = min(60, base)
        _set_width(ws, idx, base)


def _fmt(v):
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(v, list):
        return json.dumps(v, ensure_ascii=False, default=str)
    if isinstance(v, (set, tuple)):
        return json.dumps(sorted(v), ensure_ascii=False, default=str)
    return v


def build_xlsx(out_path, big):
    try:
        from openpyxl import Workbook
    except ImportError:
        print("[consolidate] openpyxl not installed - CSV + JSON will be written (no XLSX). Install with:  py -m pip install --user openpyxl")
        return False
    wb = Workbook()
    # README
    ws = wb.active
    ws.title = "README"
    ws.append(["Statement Consolidator - deliverable"])
    ws.append(["Generated (UTC)", big["generated_utc"]])
    ws.append(["Year scope", str(big["year"])])
    ws.append(["Inputs", str(len(big["inputs"])) + " files"])
    ws.append([])
    ws.append(["Sheet", "What it is"])
    ws.append(["Accounts & Summaries", "One row per account: totals in/out/net, fees, interest, dates, dup count. The 'big file summary'."])
    ws.append(["All Transactions", "Every canonical row, same fixed column layout = the 'big file' itself."])
    ws.append(["Reconciliation", "Per-statement close-check (opening + net = closing), pass/fail."])
    ws.append(["Continuity", "Per-account, statement-to-statement continuity (prev.closing == next.opening)."])
    ws.append(["Duplicates", "Rows flagged as re-reads or double-imports across distinct files."])
    ws.append(["Coverage Gaps", "(account, missing month) with expected/actual."])
    ws.append(["Exceptions", "Accumulated anomalies (unparsed, unmapped -> extras, dup flags)."])
    ws.append(["Mappings Used", "Per institution-file: sign_convention, columns_resolved, files_seen. The audit."])

    def rows_for(key):
        return big[key]

    # Accounts
    ws = wb.create_sheet("Accounts")
    acc_headers = ["account", "institution", "account_masked", "account_type", "currency",
                   "n_rows", "n_duplicate_flagged", "min_date", "max_date",
                   "total_in", "total_out", "net", "total_fees", "total_interest"]
    _sheet(ws, acc_headers, big["accounts"])

    # All Transactions
    ws = wb.create_sheet("All Transactions")
    txn_headers = ["id", "source_institution", "source_file", "account_type", "account_masked", "currency",
                   "date", "post_date", "description", "reference", "check_number",
                   "amount", "amount_debit", "amount_credit", "fee", "interest",
                   "balance_after", "category_hint", "dup", "extras"]
    _sheet(ws, txn_headers, big["rows_out"])

    # Reconciliation
    ws = wb.create_sheet("Reconciliation")
    _sheet(ws, ["source_file", "account", "period_start", "period_end", "status",
                "opening", "closing", "expected", "actual", "delta", "n_amounts", "reason"],
           big["reconciliation"])

    # Continuity
    ws = wb.create_sheet("Continuity")
    _sheet(ws, ["account", "status", "pair", "prev_closing", "next_opening", "delta"], big["continuity"])

    # Duplicates
    ws = wb.create_sheet("Duplicates")
    _sheet(ws, ["key", "row_ids", "files", "count", "n_distinct_reads"], big["duplicates"])

    # Coverage Gaps
    ws = wb.create_sheet("Coverage Gaps")
    _sheet(ws, ["account", "year", "missing"], big["coverage"])

    # Exceptions
    ws = wb.create_sheet("Exceptions")
    _sheet(ws, ["source_file", "row", "field", "raw", "reason"], big["exceptions"])

    # Mappings Used
    ws = wb.create_sheet("Mappings Used")
    _sheet(ws, ["mapping_file", "institution", "sign_convention", "date_format",
                "columns_resolved", "resolved_by", "unmapped_headers"], big["mappings_used"])

    wb.save(out_path)
    return True


def build_big_json(inputs, outputs, out, year):
    # load
    statements = [load_canonical(p) for p in outputs]
    # gather all rows with file tag
    all_rows = []
    for st in statements:
        for r in st.get("rows", []):
            r2 = dict(r)
            r2["__file"] = st["source_file"]
            all_rows.append(r2)

    # dedup + dup detection
    all_rows, dup_findings = detect_duplicates(all_rows)

    # per account grouping
    by_account = {}
    for r in all_rows:
        acc = f"{r.get('source_institution') or '?'} / {r.get('account_masked') or 'unknown'}"
        by_account.setdefault(acc, []).append(r)

    # continuity - per account, order its distinct statements by opening balance,
    # check prev.closing == next.opening across consecutive statements.
    def _stmt_for(inst, acct_masked, f):
        for s in statements:
            if s.get("source_file") != f:
                continue
            s_inst = s.get("source_institution") or s.get("institution")
            if s_inst == inst and (s.get("account_masked") or None) == (acct_masked or None):
                return s
        return None

    cont = []
    seen_accounts = set()
    for acc, items in by_account.items():
        inst = items[0].get("source_institution")
        masked = items[0].get("account_masked")
        if (inst, masked) in seen_accounts:
            continue
        seen_accounts.add((inst, masked))
        files_with_bals = []
        for f in dict.fromkeys(i["__file"] for i in items):
            s = _stmt_for(inst, masked, f)
            if s:
                st = s.get("statement") or {}
                if st.get("opening_balance") is not None:
                    files_with_bals.append((st["opening_balance"], f))
        files_with_bals = sorted(set(files_with_bals), key=lambda x: x[0])
        for i in range(len(files_with_bals) - 1):
            _, f1 = files_with_bals[i]
            _, f2 = files_with_bals[i + 1]
            close_prev = (_stmt_for(inst, masked, f1) or {}).get("statement", {}).get("closing_balance")
            open_next = (_stmt_for(inst, masked, f2) or {}).get("statement", {}).get("opening_balance")
            if close_prev is None or open_next is None:
                continue
            ok = abs(cents(close_prev) - cents(open_next)) <= 1
            cont.append({
                "account": acc,
                "status": "pass" if ok else "fail",
                "pair": f"{Path(f1).name} -> {Path(f2).name}",
                "prev_closing": money(cents(close_prev)),
                "next_opening": money(cents(open_next)),
                "delta": money(cents(open_next) - cents(close_prev)),
            })

    # coverage
    cov = coverage(all_rows, by_account, year=year)

    # reconciliation per statement
    rec = []
    for st in statements:
        st_rows = [r for r in all_rows if r["__file"] == st.get("source_file")]
        cc = close_check(st.get("statement") or {}, st_rows)
        stmt = st.get("statement") or {}
        rec.append({
            "source_file": st.get("source_file"),
            "account": f"{st.get('source_institution') or st.get('institution') or '?'} / {st.get('account_masked') or 'unknown'}",
            "period_start": stmt.get("period_start"),
            "period_end": stmt.get("period_end"),
            **cc,
        })

    # accounts summary
    accounts = [summarize_account(acc, rr) for acc, rr in by_account.items()]

    # mappings used
    mu = []
    for st in statements:
        mu.append({
            "mapping_file": (st.get("mapping_used") or {}).get("mapping_file"),
            "institution": st.get("source_institution") or (st.get("mapping_used") or {}).get("institution"),
            "sign_convention": (st.get("mapping_used") or {}).get("sign_convention"),
            "date_format": (st.get("mapping_used") or {}).get("date_format"),
            "columns_resolved": (st.get("mapping_used") or {}).get("columns_resolved"),
            "resolved_by": (st.get("mapping_used") or {}).get("resolved_by"),
            "unmapped_headers": (st.get("mapping_used") or {}).get("unmapped_headers"),
            "source_file": st.get("source_file"),
        })

    # rows out (for All Transactions sheet)
    rows_out = []
    for r in all_rows:
        row_out = dict(r)
        row_out.pop("__file", None)
        row_out["dup"] = bool(r.get("_dup"))
        row_out["_dup_files"] = r.get("_dup_files", [])
        rows_out.append(row_out)

    # exceptions - a meaningful audit list: duplicate-flagged rows, close-check
    # failures, and coverage gaps.
    exceptions = []
    for r in all_rows:
        if r.get("_dup"):
            exceptions.append({
                "source_file": r.get("source_file"),
                "row": r.get("id"),
                "field": "duplicate",
                "raw": f"date={r.get('date')} amount={r.get('amount')} desc={C.norm_desc(r.get('description'))}",
                "reason": f"same identity in: {', '.join(r.get('_dup_files') or []) or 'this file'}",
            })
    for r in rec:
        if r["status"] == "fail":
            exceptions.append({
                "source_file": r.get("source_file"),
                "row": None,
                "field": "close-check",
                "raw": f"open={r.get('opening')} close={r.get('closing')}",
                "reason": f"expected {r.get('expected')} actual {r.get('actual')} delta {r.get('delta')}",
            })
    for cv in cov:
        exceptions.append({
            "source_file": None,
            "row": None,
            "field": "coverage-gap",
            "raw": "account",
            "reason": f"{cv['account']} missing {cv['missing']}",
        })

    big = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "year": year,
        "inputs": [Path(p).name for p in outputs],
        "accounts": accounts,
        "rows": all_rows,
        "rows_out": rows_out,
        "reconciliation": rec,
        "continuity": cont,
        "duplicates": dup_findings,
        "coverage": cov,
        "exceptions": exceptions,
        "mappings_used": mu,
        "summary": {
            "checks_passed": sum(1 for r in rec if r["status"] == "pass"),
            "checks_failed": sum(1 for r in rec if r["status"] == "fail"),
            "checks_na": sum(1 for r in rec if r["status"] == "na"),
            "dup_findings": len(dup_findings),
            "coverage_findings": len(cov),
            "exceptions": len(exceptions),
        },
    }
    # strip non-serializable
    for r in big["rows"]:
        r.pop("_dup_files", None) if False else None
        r.pop("__file", None)
    return big


def main(argv=None):
    ap = argparse.ArgumentParser(description="Consolidate statement files + reconcile")
    ap.add_argument("inputs", nargs="*", help="canonical .json files, a directory, or a glob pattern")
    ap.add_argument("-o", "--out", default="consolidated.xlsx", help="output workbook name (xlsx + csv + json)")
    ap.add_argument("--year", type=int, default=None, help="scope coverage checks to this year")
    ap.add_argument("--work-dir", default=None, help="if no inputs given, scan this dir for *.canonical.json")
    args = ap.parse_args(argv)

    inputs = gather_inputs(args.inputs, args.work_dir)
    print(f"[consolidate] inputs: {len(inputs)} files")
    for p in inputs:
        print(f"[consolidate]   {p}")
    print(f"[consolidate] out: {args.out}  (xlsx + .json + .csv)")
    print(f"[consolidate] year scope: {args.year}")

    outputs = inputs  # already canonical
    big = build_big_json(inputs, outputs, args.out, args.year)

    out_path = Path(args.out)
    base = out_path.with_suffix("")
    # JSON always
    json_path = Path(str(base) + ".json")
    payload = json.loads(json.dumps(big, ensure_ascii=False, sort_keys=False, default=str))
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[consolidate] wrote {json_path}")

    # CSV always (the "big file with the same format")
    csv_path = Path(str(base) + ".csv")
    txn_headers = ["id", "source_institution", "source_file", "account_type", "account_masked", "currency",
                   "date", "post_date", "description", "reference", "check_number",
                   "amount", "amount_debit", "amount_credit", "fee", "interest",
                   "balance_after", "category_hint", "dup", "extras"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=txn_headers)
        w.writeheader()
        for r in big["rows_out"]:
            row = {h: r.get(h) for h in txn_headers if h in r}
            if isinstance(row.get("extras"), (dict, list)):
                row["extras"] = json.dumps(row["extras"], ensure_ascii=False, sort_keys=True)
            w.writerow(row)
    print(f"[consolidate] wrote {csv_path}")

    # XLSX if openpyxl
    if build_xlsx(str(out_path), big):
        print(f"[consolidate] wrote {out_path}")
    else:
        print(f"[consolidate] (no XLSX; install openpyxl and re-run)")

    print(f"[consolidate] summary: passed={big['summary']['checks_passed']} failed={big['summary']['checks_failed']} "
          f"na={big['summary']['checks_na']} dups={big['summary']['dup_findings']} "
          f"coverage_gaps={big['summary']['coverage_findings']} anomalies={big['summary']['exceptions']}")
    for r in big["reconciliation"]:
        mark = r["status"].upper() if r["status"] in ("pass", "fail", "na") else r["status"]
        print(f"[consolidate]   {mark:>4}  {r.get('source_file')}  {r.get('account')}  open={r.get('opening')} close={r.get('closing')} expected={r.get('expected')} actual={r.get('actual')} delta={r.get('delta')}")
    for c in big["continuity"]:
        print(f"[consolidate]   {c['status']:>4}  continuity {c['account']}  {c['pair']}  delta={c['delta']}")
    for d in big["duplicates"]:
        print(f"[consolidate]   dup   {d['key']}  files={d['files']}  rows={d['count']}  distinct_reads={d['n_distinct_reads']}")
    for cv in big["coverage"]:
        print(f"[consolidate]   coverage  {cv['account']}  {cv['year']}  missing={cv['missing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
