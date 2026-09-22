#!/usr/bin/env python3
"""apply_mapping.py - map a raw statement JSON onto the canonical schema using a
field-mapping file.

Model-free. Resolves each canonical field to a raw header (mapping aliases
first, built-in synonyms second - the Tier-2 fallback, which is surfaced in the
resolved-header audit so the agent can promote it). Computes the signed `amount`
per `sign_convention`, preserves the original `amount_debit`/`amount_credit`,
classifies fee/interest rows into typed subtotals, routes unclaimed headers to
`extras` verbatim (never dropped), preserves `raw`, derives a stable `id`, and
attaches provenance.

Usage:
    python apply_mapping.py in.raw.json -m mappings/example-bank.json -o out.canonical.json
        [--institution NAME] [--account-masked '****4821']

Output: a canonical statement envelope (see reference/CANONICAL-SCHEMA.md) whose
`rows` each carry: id, date, description, reference, check_number, amount,
amount_debit, amount_credit, fee, interest, balance_after, category_hint, extras,
raw, source_file, source_institution, account_masked, account_type, currency.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import common as C  # noqa: E402


def build_resolver(raw_headers, mapping):
    """Map canonical field -> raw header, marking which tier claimed it."""
    by_norm = {}
    for h in raw_headers:
        n = C.norm_header(h)
        if n and n not in by_norm:
            by_norm[n] = h
    resolver, resolved_by = {}, {}
    # Tier 1: explicit mapping columns.
    for canon, aliases in (mapping.get("columns") or {}).items():
        if canon in resolver:
            continue
        for alias in aliases or []:
            n = C.norm_header(alias)
            if n and n in by_norm:
                resolver[canon] = by_norm[n]
                resolved_by[canon] = "mapping"
                break
    # Tier 2: built-in synonyms (only for fields not yet resolved).
    for canon in C.CANONICAL_FIELDS:
        if canon in resolver:
            continue
        for n, h in by_norm.items():
            if n in C.SYNONYMS.get(canon, set()):
                resolver[canon] = h
                resolved_by[canon] = "synonym"
                break
    return resolver, resolved_by


def apply_row(raw, resolver, mapping, context, exceptions):
    def cell(canon):
        return raw.get(resolver[canon]) if canon in resolver else None

    date_fmt = mapping.get("date_format")
    conv = mapping.get("sign_convention", "signed-amount")

    # date
    date_raw = cell("date")
    date_norm = C.parse_date(date_raw, date_fmt) if date_raw not in (None, "") else None
    if date_raw not in (None, "") and date_norm is None:
        exceptions.append({"row": context["row_no"], "source_file": context["source_file"],
                           "field": "date", "raw": date_raw, "reason": "unparseable date"})

    # post_date (best-effort, same value if only one date column exists)
    post_date = date_norm

    desc_raw = cell("description")
    description = str(desc_raw).strip() if desc_raw not in (None, "") else ""
    ref_raw = cell("reference")
    reference = str(ref_raw).strip() if ref_raw not in (None, "") else None
    chk_raw = cell("check_number")
    check_number = str(chk_raw).strip() if chk_raw not in (None, "") else None

    # amounts
    amount = None
    amount_debit = None
    amount_credit = None
    deb_col, cred_col, amt_col = resolver.get("amount_debit"), resolver.get("amount_credit"), resolver.get("amount")
    try:
        raw_d = raw.get(deb_col) if deb_col else None
        raw_c = raw.get(cred_col) if cred_col else None
        if (raw_d not in (None, "")) or (raw_c not in (None, "")):
            d = C.parse_money(raw_d) if raw_d not in (None, "") else None
            c = C.parse_money(raw_c) if raw_c not in (None, "") else None
            d = Decimal(0) if d is None else d
            c = Decimal(0) if c is None else c
            amount = c - d
            if d:
                amount_debit = d
            if c:
                amount_credit = c
        elif amt_col and raw.get(amt_col) not in (None, ""):
            amount = C.parse_money(raw.get(amt_col))
    except ValueError as e:
        amount = None
        exceptions.append({"row": context["row_no"], "source_file": context["source_file"],
                           "field": "amount", "raw": str(raw.get(deb_col) or raw.get(cred_col) or (raw.get(amt_col) if amt_col else None)),
                           "reason": str(e)})

    # balance-after
    balance_after = None
    if "balance" in resolver and raw.get(resolver["balance"]) not in (None, ""):
        try:
            balance_after = C.parse_money(raw.get(resolver["balance"]))
        except ValueError:
            exceptions.append({"row": context["row_no"], "source_file": context["source_file"],
                               "field": "balance", "raw": str(raw.get(resolver["balance"])), "reason": "unparseable balance"})

    # fee / interest classification (typed subtotals, keeps the signed amount)
    classify = mapping.get("classify") or {}
    fee_kw = [k.lower() for k in classify.get("fee", [])]
    int_kw = [k.lower() for k in classify.get("interest", [])]
    desc_low = description.lower()
    fee = None
    interest = None
    if amount is not None:
        if fee_kw and any(k in desc_low for k in fee_kw):
            fee = amount
        if int_kw and any(k in desc_low for k in int_kw):
            interest = amount

    category_hint = None
    if fee is not None and interest is not None:
        category_hint = "fee,interest"
    elif fee is not None:
        category_hint = "fee"
    elif interest is not None:
        category_hint = "interest"

    # extras: unclaimed raw headers (not mapped, not ignored) - preserved verbatim
    mapped_headers = set(resolver.values())
    ignore = {C.norm_header(x) for x in (mapping.get("ignore") or [])}
    extras = {}
    for h, v in raw.items():
        if h in mapped_headers:
            continue
        if not str(v).strip():
            continue
        if C.norm_header(h) in ignore:
            continue
        extras[h] = v
        exceptions.append({"row": context["row_no"], "source_file": context["source_file"],
                           "field": h, "raw": str(v), "reason": "unmapped header -> extras"})

    amount_f = round(float(amount), 2) if amount is not None else None
    ad_f = round(float(amount_debit), 2) if amount_debit is not None else None
    ac_f = round(float(amount_credit), 2) if amount_credit is not None else None
    bal_f = round(float(balance_after), 2) if balance_after is not None else None
    fee_f = round(float(fee), 2) if fee is not None else None
    interest_f = round(float(interest), 2) if interest is not None else None

    rid = C.stable_id(context["institution"] or "?", context["account_masked"] or "?",
                      date_norm or "", description, "" if amount_f is None else f"{amount_f:.2f}",
                      reference or "")
    return {
        "id": rid,
        "date": date_norm,
        "post_date": post_date,
        "description": description,
        "reference": reference,
        "check_number": check_number,
        "amount": amount_f,
        "amount_debit": ad_f,
        "amount_credit": ac_f,
        "fee": fee_f,
        "interest": interest_f,
        "balance_after": bal_f,
        "category_hint": category_hint,
        "extras": extras,
        "raw": raw,
        "source_file": context["source_file"],
        "source_institution": context["institution"],
        "account_masked": context["account_masked"],
        "account_type": context["account_type"],
        "currency": context["currency"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="raw statement JSON -> canonical rows")
    ap.add_argument("raw")
    ap.add_argument("-m", "--mapping", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--institution", default=None)
    ap.add_argument("--account-masked", default=None)
    args = ap.parse_args(argv)

    raw_stmt = json.loads(Path(args.raw).read_text(encoding="utf-8-sig"))
    mapping = C.load_mapping(args.mapping) if args.mapping else {}

    columns_raw = raw_stmt.get("columns_raw") or []
    resolver, resolved_by = build_resolver(columns_raw, mapping)

    institution = args.institution or raw_stmt.get("institution") or (mapping.get("institution") if isinstance(mapping.get("institution"), str) else None)
    account_masked = args.account_masked or raw_stmt.get("account_masked")
    account_type = raw_stmt.get("account_type") or (mapping.get("account_type") if isinstance(mapping, dict) else None)
    currency = raw_stmt.get("currency") or (mapping.get("currency") if isinstance(mapping, dict) else None)

    context = {
        "source_file": raw_stmt.get("source_file"),
        "institution": institution,
        "account_masked": account_masked,
        "account_type": account_type,
        "currency": currency,
    }

    exceptions = []
    rows = []
    for idx, r in enumerate(raw_stmt.get("rows", []), start=1):
        context["row_no"] = idx
        rows.append(apply_row(r.get("raw") or {}, resolver, mapping, context, exceptions))

    mapped_headers = sorted(set(resolver.values()))
    unmapped_headers = [h for h in columns_raw if h not in mapped_headers]

    out = {
        "source_file": raw_stmt.get("source_file"),
        "institution": institution,
        "account_masked": account_masked,
        "account_type": account_type,
        "currency": currency,
        "statement": raw_stmt.get("statement") or {},
        "rows": rows,
        "row_count": len(rows),
        "mapping_used": {
            "mapping_file": Path(args.mapping).name if args.mapping else None,
            "institution": isinstance(mapping, dict) and mapping.get("institution"),
            "sign_convention": isinstance(mapping, dict) and mapping.get("sign_convention"),
            "date_format": isinstance(mapping, dict) and mapping.get("date_format"),
            "columns_resolved": resolver,
            "resolved_by": resolved_by,
            "unmapped_headers": unmapped_headers,
        },
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[map] {args.raw} -> {args.out}")
    print(f"[map]   institution={institution!r} account={account_masked!r} type={account_type!r} cur={currency!r}")
    print(f"[map]   sign_convention={out['mapping_used']['sign_convention']}  rows={len(rows)}")
    print(f"[map]   resolved: {resolved_by}")
    if unmapped_headers:
        print(f"[map]   unmapped (->extras if non-empty): {unmapped_headers}")
    n_ex = len(exceptions)
    print(f"[map]   anomalies={n_ex}")
    print(f"[map]   wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
