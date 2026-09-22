# Canonical schema

The canonical schema is the ONE shape every statement — from every institution,
any layout, any account type — normalizes into. It is deliberately boring and
audit-friendly: a typed `amount` plus the raw debit/credit split preserved, typed
`fee`/`interest` columns, an `extras` bucket for anything the schema does not
name, a per-cell `raw` copy, a stable `id`, and provenance.

The machine-checkable form is in `CANONICAL-SCHEMA.json` (JSON Schema,
draft-07). This file is the human reading + worked examples.

## 1. Statement envelope

A per-file (statement-level) record. One envelope per source statement.

```json
{
  "source_file": "example-bank-2025Q1.csv",
  "account": {
    "institution": "Example Bank",
    "account_masked": "••••4821",
    "account_type": "checking",
    "currency": "USD"
  },
  "statement": {
    "period_start": "2025-01-01",
    "period_end":   "2025-03-31",
    "opening_balance": 1000.00,
    "closing_balance": 6450.11,
    "printed_total":   6450.11,
    "summary_lines":   ["Opening Balance: 1,000.00", "Closing Balance: 6,450.11"]
  },
  "rows": [ "<canonical row>", "<canonical row>", "…" ]
}
```

Optional fields are `null` when the statement does not carry them. **Never
invent a balance the statement does not print** — if the statement has no opening
or closing value, it is `null` and the close-check is reported `na` (see
`RECONCILIATION.md`).

`summary_lines` is the verbatim text of the lines ingest lifted out of the table
area (opening/closing/period/total). This is the audit that nothing was dropped:
the exact strings the agent read are preserved, so the user can see what the raw
source said at the moment it was lifted off the transaction table.

## 2. Canonical row

One object per transaction. Field order is not authoritative; the JSON Schema is.

```json
{
  "id": "example-bank-4821-20250112-netflix.com-15.49",
  "source_institution": "Example Bank",
  "source_file":        "example-bank-2025Q1.csv",
  "account_masked":     "••••4821",
  "account_type":       "checking",
  "currency":           "USD",
  "date":               "2025-01-12",
  "post_date":          null,
  "description":        "NETFLIX.COM",
  "reference":          "1002",
  "check_number":       null,
  "amount":             -15.49,
  "amount_debit":       15.49,
  "amount_credit":      null,
  "fee":                null,
  "interest":           null,
  "balance_after":      3484.51,
  "category_hint":      "subscription",
  "dup":                false,
  "extras":             {},
  "raw": {
    "Date": "01/12/2025",
    "Particulars": "NETFLIX.COM",
    "Ref #": "1002",
    "Deposit": "", "Withdrawal": "15.49",
    "Balance": "3,484.51"
  }
}
```

### Field guide

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Stable sha1-16 from (institution, account_masked, date, description, amount, reference). Same content → same id. Dedup key. |
| `source_institution` | string | From the mapping file, not the filename. |
| `source_file` | string | Original source filename (basename). |
| `account_masked` | string | The account as the institution printed it (with masking). |
| `account_type` | enum | `checking` · `savings` · `credit` · `loan` (or `other`). |
| `currency` | string | ISO 4217. Per-account. No silent FX conversion. |
| `date` | string (ISO-8601) | Transaction date as the statement printed it, normalized. |
| `post_date` | string or null | If the statement carries a separate posting/settling date (many banks do). |
| `description` | string | Merchant/particulars/description — verbatim, not re-worded. |
| `reference` | string or null | Ref / txn / transaction id (per institution convention). |
| `check_number` | string or null | Cheque/check number, if a separate column. |
| `amount` | number | **Signed** per the mapping's `sign_convention`. Positive = added to the account balance; negative = removed / payment to the account. |
| `amount_debit` | number or null | Raw debit/withdrawal side, preserved for audit (when `two-column`). |
| `amount_credit` | number or null | Raw credit/deposit side, preserved for audit (when `two-column`). |
| `fee` | number or null | Typed fee/charge for that row (subtotal-able). |
| `interest` | number or null | Typed interest for that row (subtotal-able). |
| `balance_after` | number or null | Running balance as printed, if the statement carries it. |
| `category_hint` | string or null | Optional, derived from `classify` (fee/interest) or from a merchant category you explicitly map. Never a guess. |
| `dup` | bool | True when the duplicate/continuity gate flagged this row as a double-import (kept, not dropped). |
| `extras` | object | Verbatim copy of any raw header the mapping did not resolve. Keys are the raw header names, values the raw cell values. |
| `raw` | object | The original header→cell dict, verbatim, for that row. Audit of record. |

### Amount conventions (declared per mapping)

- `two-column`: statement prints separate Debit / Credit columns.
  `amount = credit − debit`. `amount_debit`/`amount_credit` are the raw values.
  Positive `amount` = credit (money in); negative = debit (money out).
- `signed-amount`: statement prints one signed `Amount` column.
  `amount` is as printed (positive = added to balance; negative = payment/credit
  reducing it). `amount_debit`/`amount_credit` are `null` unless a column is
  actually present.

### `fee` / `interest` — typed, subtotal-able

Derived deterministically (from the description text or an explicit column),
**never a guess**:

1. If the mapping has an explicit `fee`/`interest` COLUMN (rare, some
   statements), use it.
2. Otherwise, value-detect from the description: a row whose
   description contains any of the mapping's `classify.fee` words gets
   `fee = <the row's signed amount on the "charge" side>`; same for
   `classify.interest`.
3. A single row can carry both (e.g. "Service Fee + Interest") if the mapping
   lists words for both and the description matches both.

Subtotals (for the Accounts & Summaries sheet and year-end reporting):
`fees = Σ fee`, `interest = Σ interest` per account. These are script-computed,
not estimated.

## 3. Stable id

`id = sha1(institution|account_masked|date|norm(description)|str(amount)|str(reference))[:16]`

- `norm(description)` is case/punctuation-insensitive so "NETFLIX" and
  "netflix.com" map to the same id only when the other identity fields also
  match (they usually won't — description + date + amount + reference are
  specific enough).
- Same content → same id. This is the dedup key: re-running the pipeline on the
  same inputs yields the same `id` set, so `consolidate.py` can drop exact
  re-reads and flag cross-file duplicates without changing any value.
- An id is never re-generated by re-wording a description — the raw
  description is the norm source, so two re-reads of the same raw cell agree.
