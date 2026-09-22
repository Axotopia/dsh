# Mapping profiles

A **mapping profile** is the durable, editable artifact that tells the scripts
how ONE institution's raw headers map onto the canonical schema. It lives in the
workspace `mappings/` folder, is learned once, confirmed once, and then applied
identically to every later statement from that institution. This is the mechanism
that solves "many JSON files with different formats into one big file with the
same format": the formats stay different at the source; the mapping normalizes
them to the canonical schema.

## 1. The confirm-once loop

```
new institution statement
        │
        ├─ header auto-detect  (ingest.py)
        ├─ agent proposes: columns, sign_convention, date_format, classify
        ├─ SHOWS: resolved header table + 3-row canonical sample
        ▼
  NEW? ── yes ──► ask_user_question  (ONE confirmation) ──► save mappings/<inst>.json
     │
     no  ───────────────────────────── apply identical mapping (zero confirms)
```

Rules:
- **One confirmation per NEW institution, then zero.** A mapping is a file the
  user edits, not a guess re-rolled each run.
- **Show, then ask.** Never ask "can I map this?"; show the resolved header
  table + a 3-row canonical sample, then ask the user to approve the NEW
  mapping.
- **When in doubt, `extras` + `raw`.** An unrecognized header is NOT dropped; it
  goes to `extras` verbatim and is listed in the Exceptions output.
- **Drift:** if the same institution's layout changes next year, add the new
  filename to `files_seen` (or split into a second file) and re-confirm only the
  changed parts. The old mapping still applies to the old layout.

## 2. Mapping file shape (JSON)

JSON is used (not YAML) so the scripts need only the standard library —
`openpyxl` is the ONLY third-party import in the whole preset, and only for
`.xlsx`.

```json
{
  "institution": "Example Bank",
  "detect": [ "example bank", "examplebank" ],

  "account_type": "checking",
  "currency": "USD",
  "sign_convention": "two-column",

  "date_format": "%m/%d/%Y",
  "header_hint": "Date",

  "columns": {
    "date":          [ "Date" ],
    "description":   [ "Particulars", "Description", "Details" ],
    "reference":     [ "Ref #", "Reference" ],
    "check_number":  [ "Chq #", "Check No" ],
    "amount":        [ "Amount" ],
    "amount_debit":  [ "Withdrawal", "Debit" ],
    "amount_credit": [ "Deposit", "Credit" ],
    "balance":       [ "Balance", "Running Balance" ]
  },

  "classify": {
    "fee":      [ "service charge", "annual fee", "maintenance fee", "overdraft fee" ],
    "interest": [ "interest earned", "interest paid", "interest charged" ]
  },

  "ignore": [ "Page", "Statement Page" ],

  "first_mapped": "2026-09-22",
  "files_seen": [ "example-bank-2025Q1.csv", "example-bank-2025Q2.csv" ]
}
```

### Field reference

| Key | Required | Meaning |
|-----|----------|---------|
| `institution` | yes | Display name for this institution (used in `source_institution`). |
| `detect[]` | rec. | Lowercase substrings that identify this institution in a filename or the statement text (used by auto-pick + the agent's first look). |
| `account_type` | rec. | Default account type for this institution's statement (`checking`, `savings`, `credit`, `loan`). |
| `currency` | rec. | Default currency (ISO 4217). Per-statement override is legal but not automatic. |
| `sign_convention` | yes | `two-column` or `signed-amount`. Declares HOW the statement signs amounts; the engine then computes `amount`. |
| `date_format` | rec. | `strptime` format (e.g. `%m/%d/%Y`). Declares the institution's date convention ONCE — this is what makes a later "3/4/2025 = March 4" decision auditable. |
| `header_hint` | optional | A header word that must appear on the header row (helps auto-detect when several rows score similarly). |
| `columns{}` | yes (or Tier-2) | Map each canonical field to a LIST of raw-header aliases (any case, any punctuation). Multi-variant lists let one mapping cover several of the institution's historical layouts. |
| `classify{}` | rec. | `fee[]` / `interest[]`: description substrings (lowercase) that, when matched on a row, mark the row's typed `fee`/`interest` value (see CANONICAL-SCHEMA.md §2). |
| `ignore[]` | optional | Raw headers that are known noise (e.g. "Page"); they are dropped BEFORE the `extras` decision, so they are not reported as exceptions. |
| `first_mapped` | rec. | ISO date the mapping was first confirmed (audit). |
| `files_seen[]` | rec. | Filenames the mapping has been applied to. Grows over time; the audit trail for "did this file use a mapping the user confirmed?". |

### Tier-2 fuzzy discovery (built-in)

For any canonical field the user did not alias in `columns`, the engine consults
the built-in synonym table (`SYNONYMS.md`) after normalizing both sides
(lowercase, punctuation/case-insensitive). A hit is provisional; it is reported in
the Exceptions output as "Tier-2 matched" so the user can promote it into the
mapping (or reject it). This is what makes a fresh institution mostly workable on
the first encounter without a full mapping: the agent still gets the header table
right from the builtin lexicon, and only the `detect` / `classify` /
`sign_convention` specifics may need a confirmation.

## 3. Worked examples

See `mappings/example-bank.json` (two-column, checking) and
`mappings/example-credit-card.json` (signed-amount, credit). Both are generic
(sanitized, no real institution identifiers) and reproduce the demo layout in
`examples/`.

### Sign-convention cheat sheet

| Statement style | Detect by | Mapping `sign_convention` | `amount` formula |
|---|---|---|---|
| Separate `Debit` / `Credit` columns | both present | `two-column` | `credit − debit` |
| Column `Amount` with D/C marker text (`15.49 Dr`) | single amount + marker | `signed-amount` | parsed signed (Dr = −) |
| Column `Amount` with parens for debits | single amount, parens | `signed-amount` | parsed signed (parens = −) |
| Column `Amount`, positive = charge (card) | single amount, no marker | `signed-amount` | as printed (positive = added to balance) |

`apply_mapping.py` handles all four: `parse_money` strips currency, commas,
whitespace, D/C markers, and accounting parens, then applies the sign.

## 4. Where mappings live, and why

**In the workspace `mappings/` folder — not inside the preset.** Rationale:

- The preset is **generic** (it ships as a template and is the same for every
  user). The mappings are **the user's institutional memory** — which of the
  user's banks use which layout, in which order, with which `date_format`.
- Keeping them in the workspace means they travel with the user's data across
  machines, are easy to diff in git, and are trivially deletable when an
  institution is retired.
- The preset ships two **example** mappings (`mappings/example-*.json`) in the
  package so the scripts can be demonstrated without a live bank's file. Copy
  one to the workspace as a starting shape for a new institution.
