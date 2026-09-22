---
name: statement-consolidation
description: Use on ANY statement-consolidation task on the Statement Consolidator preset — reading bank/credit-card statements (CSV/XLSX, any institution) into canonical JSON, the learn-once field-mapping protocol, the deterministic reconcile gate, the canonical schema, output format, and deliverable contract.
---

# Statement consolidation method

A folder of bank and credit-card statements from several institutions, several
layouts, several account types becomes ONE canonical, reconciled, audited
result: a big JSON + a multi-sheet Excel workbook + a flat mirror CSV, ready for
year-end reporting. This skill is the protocol of record. The reference files
beside it are the source of truth:

| # | File | What it owns |
|---|------|--------------|
| 1 | `reference/CANONICAL-SCHEMA.md` | The canonical row + statement envelope (human); `reference/CANONICAL-SCHEMA.json` is the machine-checkable JSON Schema |
| 2 | `reference/MAPPING-PROFILES.md` | The mapping-file format, the confirm-once loop, worked examples |
| 3 | `reference/RECONCILIATION.md` | The reconciliation gate: close-check, continuity, duplicates, coverage |
| 4 | `reference/SYNONYMS.md` | The built-in header→canonical synonym table (Tier-2 discovery) |

Read all four before your first step. When a script and a reference file
disagree, the reference file wins.

## 1. Non-negotiables

1. **No invented numbers.** Every total, subtotal, pass/fail, duplicate, and
   coverage finding comes from `ingest.py` / `apply_mapping.py` /
   `consolidate.py` output. You quote the script's number; you never "round it
   in" or "fix it to match." A reconciliation mismatch is a finding.
2. **No silently dropped data.** A raw header the schema does not name lands in
   `extras` (verbatim) and is listed in output + the Exceptions sheet. A cell you
   could not parse stays in `raw` and is flagged, never deleted.
3. **One confirm per new institution.** Propose the mapping with a resolved
   header table + 3-row sample; ask once; save to `mappings/<institution>.json`;
   apply identically to every later statement from that institution.
4. **Reconcile before delivering.** Close-check, continuity, duplicates,
   coverage (see `reference/RECONCILIATION.md`). No "done" until the gate ran.
5. **Preserve provenance on every row**: `raw` (original cells), `source_file`,
   `source_institution`, `account_masked`, stable `id`, and the mapping used.
6. **PDFs are out of scope.** Route to `ocr-md` / `ocr-md-json` as the upstream
   document→text stage. Never transcribe a PDF or OCR a page in this preset.

## 2. The three layers

1. **Canonical schema** — fixed; every institution normalizes into it
   (`reference/CANONICAL-SCHEMA.md`).
2. **Mapping profiles** — per institution; persist in the workspace `mappings/`
   folder; learned once, edited as files, never re-guessed
   (`reference/MAPPING-PROFILES.md`).
3. **Deterministic scripts** — the mechanical read, map, merge, reconcile,
   write. Model-free. This is why the numbers are trustworthy.

## 3. Pipeline (exact order)

Work relative to the session workspace; put intermediates in `work/` and final
deliverables at the workspace root (or a folder the user names).

### Step 0 — Frame (ask only what the user owns)
Folder? Which accounts? Which year/period? Bank-only or bank+card? Keep
per-currency or one base currency? Then profile the rest yourself.

### Step 1 — Ingest (CSV/XLSX → raw statement JSON)
```
python scripts\ingest.py  "statements\example-bank-2025Q1.csv"  -o  work\example-bank-2025Q1.raw.json
```
- Auto-detects the header row among the institution's title/branded rows.
- Captures summary lines (opening/closing balance, period) into the `statement`
  block; records them verbatim in `skipped_meta_lines` (nothing dropped).
- Emits `columns_raw`, `rows[].raw` (original header→cell), `row_count`.
- If the header it found looks wrong, override: `--header-row N` (0-based), or fix
  the mapping's `header_hint`.
- Openpyxl: `python scripts\ingest.py in.xlsx -o out.raw.json`
  (needs the one install — `.csv` works with no third-party packages).

### Step 2 — Map (raw → canonical rows), with the confirm-once loop
Pick the mapping for the institution (`mappings/<institution>.json`). If it does
not exist, or the layout drifted, PROPOSE one:

- Show the agent's resolved header table: each canonical ← which raw header,
  the sign convention, the date format, and the `classify` fee/interest words.
- Show a **3-row sample** of canonical rows so the user can verify amounts/dates.
- **NEW institution → ask for ONE confirmation** (ask_user_question).
- Save `mappings/<institution>.json` (see
  `reference/MAPPING-PROFILES.md` for the exact shape). Add the filename to
  `files_seen`; set/keep `first_mapped`.
```
python scripts\apply_mapping.py  --raw  work\example-bank-2025Q1.raw.json  --mapping  mappings\example-bank.json  -o  work\example-bank-2025Q1.canonical.json
```
- Fills `amount` (per sign convention) + preserves `amount_debit`/`amount_credit`.
- Sets typed `fee` / `interest` (from a column, or value-detected from the
  description via the mapping's `classify` lists — deterministic, never a guess).
- Unmapped headers → `extras`; original cells → `raw`; stable `id`; provenance.
- If a cell is unparseable as a date/amount, it is routed to `extras`, kept in
  `raw`, and flagged in `unparsed` — never silently coerced.

### Step 3 — Reconcile (the gate) — run by consolidate.py
Read `reference/RECONCILIATION.md`, then:
```
python scripts\consolidate.py  work\*.canonical.json  --outdir  out  --year  2025
```
The gate (all model-free):
- **Close-check per statement**: `opening + Σ(amount) == closing` (≤ 1¢) when the
  statement carries balances.
- **Continuity**: for each account, this statement's opening == previous
  statement's closing (sorted by period).
- **Duplicates / double-import**: same (institution, account, date, amount,
  description) across different files → flagged, never silently merged.
- **Coverage**: months with zero rows for an account that should have activity →
  flagged.

### Step 4 — Deliver (the deliverable contract, §6)

## 4. Money & date discipline

- **Sign convention** is declared per mapping:
  - `two-column`: separate Debit/Credit columns → `amount = credit − debit`.
  - `signed-amount`: one signed `Amount` column (positive = added to balance;
    negative = payment/credit reducing it) → use as-is.
- `amount_debit` / `amount_credit` (the raw split) are preserved for audit on
  every row, even when `two-column` was the source.
- **Dates**: ISO-8601 `YYYY-MM-DD` in the canonical field; the original string
  stays in `raw`. Ambiguous `3/4/2025` (US vs EU) — DO NOT guess: confirm the
  convention once for that institution in the mapping (`date_format`), then
  apply it identically.
- **Currency** is per account (a `currency` field). No silent FX conversion.
  If the user wants one base currency, convert EXPLICITLY with a rate the user
  supplies and record the rate in the output.
- **Typed fee/interest** are subtotal-able columns (year-end interest & fees),
  derived deterministically, always backed by `raw`.

## 5. Where things live

| Data | Location | Notes |
|------|----------|-------|
| Institution mappings | workspace `mappings/<institution>.json` | durable; edit as files; travel with the user's data; survive across sessions |
| Raw per-file JSON | `work/<name>.raw.json` | step 1 output; audit of ingest + summary capture |
| Canonical per-file JSON | `work/<name>.canonical.json` | step 2 output; the merge inputs |
| Big consolidated file | `out/consolidated-<year>.json` | step 3 output |
| Excel workbook | `out/consolidated-<year>.xlsx` | step 3 output (multi-sheet) |
| Mirror CSV | `out/all-transactions-<year>.csv` | the flat "one big file, same format" |
| Reconciliation/audit | in the JSON + the Excel sheets | close-check, continuity, duplicates, coverage, exceptions, mappings used |

## 6. The deliverable contract

Every consolidation response ends with these five blocks, in this order, and no
more:

1. **OUTPUTS** — the exact paths of the big JSON, the .xlsx, and the mirror CSV.
2. **RECONCILIATION** — per account: close-check pass/fail (with the two numbers
   if it failed), continuity breaks, duplicate flags, coverage gaps. Quote the
   script's output verbatim.
3. **ACCOUNTS** — one line each: institution, account (masked), period, row
   count, net, total fees, total interest.
4. **EXCEPTIONS** — every row with `extras` or `unparsed`, every unparseable
   cell, every mapping gap. Named, never counted away.
5. **MAPPINGS USED** — which `mappings/<institution>.json` applied to which
   files (audit trail).

If a check failed or data is in `extras`, say so in block 2 or 4. Never close on a
summary when details are still in `extras`.

## 7. Failure handling (be loud, not quiet)

- **Header not found** → ingest reports the per-row header-candidate scores;
  set `--header-row` or add a `header_hint` to the mapping; re-run.
- **Amount unparseable** → routed to `extras` + `raw`, flagged in `unparsed`.
  Do not coerce a `$` vs `-` vs `Dr/Cr` you are unsure of: confirm the convention
  in the mapping, then re-run.
- **Statement has no balances** → close-check is `na`; continuity/coverage still
  run. Say so in the deliverable.
- **Two layouts from one institution** → two mapping files
  (`<institution>-a.json`, `<institution>-b.json`) or a `files_seen` split; name
  which file used which.
- **Conflicting amounts for the same account/date across two files** → that is
  the duplicate/continuity gate's job; surface it, do not average.

## 8. Delegation

For a full year across several institutions, fan ingest+map out to subagents
(one per institution). Reconciliation, consolidation, and the deliverable stay in
the top-level agent. A subagent's output still passes through the same
`consolidate.py` gate — a delegated read is never a delegated number.
