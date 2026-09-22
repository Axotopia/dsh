# Statement Consolidator

A **bookkeeper** agent preset for year-end reporting. It reads bank and
credit-card statements in **CSV or Excel** from *any* institution and *any*
layout, turns each into **canonical JSON**, learns and persists the
per-institution field mapping (**confirmed once, reused forever**), and then
consolidates many heterogeneous statement files into **ONE big file with the
same format** — a canonical JSON + CSV **"master transactions"** file plus a
**multi-sheet Excel workbook** (all transactions, account summaries,
reconciliation, continuity, duplicates, coverage gaps, exceptions, and the
mappings-used audit).

Every transformation is **model-free and deterministic**. A reconciliation gate
runs on the money (`opening + Σ transactions == closing`), duplicate and
double-import detection, cross-statement continuity, and month-coverage are
checked. **No number is ever invented and no raw column is ever silently
dropped** — unmapped headers go to `extras`, preserved verbatim.

---

## Contents

| Area | Where |
|---|---|
| What the agent does (protocol of record) | [`skills/statement-consolidation/SKILL.md`](skills/statement-consolidation/SKILL.md) |
| Canonical row / envelope (human) | [`reference/CANONICAL-SCHEMA.md`](reference/CANONICAL-SCHEMA.md) |
| Canonical row / envelope (JSON Schema) | [`reference/CANONICAL-SCHEMA.json`](reference/CANONICAL-SCHEMA.json) |
| Field-mapping profile format + confirm-once loop | [`reference/MAPPING-PROFILES.md`](reference/MAPPING-PROFILES.md) |
| Reconciliation gate (the 5 checks) | [`reference/RECONCILIATION.md`](reference/RECONCILIATION.md) |
| Built-in synonym (Tier-2) discovery table | [`reference/SYNONYMS.md`](reference/SYNONYMS.md) |
| Example mappings (start from these) | [`mappings/`](mappings/) |
| Example statements (run end-to-end from these) | [`examples/`](examples/) |
| Scripts (stdlib-only, no network) | [`scripts/`](scripts/) |

---

## What you get (the deliverable)

For a set of input statements, the preset emits (all in the workspace):

* `consolidated.json` — the big file: one canonical `rows` array under one
  schema, plus the full reconciliation / duplicates / coverage / exceptions
  audit.
* `consolidated.csv` — the same rows, flat, spreadsheet-friendly (the
  "one big spreadsheet").
* `consolidated.xlsx` — a **workbook** with one sheet per concern:

  | Sheet | What it is |
  |---|---|
  | `README` | What the file is and how it was built. |
  | `Accounts` | One row per account: totals in/out/net, fees, interest, min/max dates, dup count. |
  | `All Transactions` | Every canonical row in one fixed column layout — the "big file". |
  | `Reconciliation` | Per-statement close-check (`opening + Σ == closing`) PASS/FAIL with both numbers. |
  | `Continuity` | Per-account statement-to-statement continuity (prev closing == next opening). |
  | `Duplicates` | Rows that are re-reads or double-imports across distinct files. |
  | `Coverage Gaps` | (account, missing month) in the year scope. |
  | `Exceptions` | Accumulated anomalies (unparsed cells, unmapped → extras, dup flags, close-check fails). |
  | `Mappings Used` | Per institution-file: sign_convention, columns resolved, resolved_by, files_seen — the audit trail. |

The deliverable contract (SKILL.md §6) always ends with:
**`OUTPUTS` / `RECONCILIATION` / `ACCOUNTS` / `EXCEPTIONS` / `MAPPINGS USED`**.

---

## Install

1. **Install once** (Windows/macOS/Linux, from the preset folder):

   ```powershell
   # copy the preset into DSH's per-user preset root
   .\INSTALL.cmd
   ```

   On macOS / Linux, copy the folder into `~/.dsh/.agent-presets/`.

2. **Prerequisites**

   * **CSV path: nothing to install.** The CSV input + CSV output pipelines are
     standard-library Python (3.10+).
   * **XLSX path (reading `.xlsx` and writing the final workbook): one
     install:**

     ```powershell
     py -m pip install --user openpyxl   # Windows
     python3 -m pip install --user openpyxl   # macOS / Linux
     ```

     Without `openpyxl` you can still process CSV inputs and emit the CSV /
     JSON "master" outputs — only the `.xlsx` workbook is skipped (with a clear
     note).

3. **Pick the preset** — in the DSH GUI select **Statement Consolidator** and
   point it at the folder of CSV / XLSX statements you want to reconcile for
   the year.

---

## How it works (the 8-step pipeline)

Each file, on each run, goes through:

1. **Ingest** (`scripts/ingest.py`) — read the CSV/XLSX, auto-detect the
   header row among the institution's title / branded / summary rows, capture
   the statement envelope (period, opening / closing balance, printed total,
   summary lines), and emit a `*.raw.json` with every cell preserved. *Nothing
   is dropped*: summary lines lifted off the table are kept verbatim in
   `statement.summary_lines`.
2. **Match fields** (`scripts/apply_mapping.py`) — resolve each canonical
   field to a raw header using the institution's mapping file (Tier-1) with the
   built-in synonym table as fallback (Tier-2). Compute the *signed*
   `amount` from the institution's declared `sign_convention`; preserve
   `amount_debit` / `amount_credit`; classify fee / interest rows into typed
   subtotals; route unclaimed headers to `extras` verbatim; derive a stable
   `id`; attach provenance.
3. **Reconcile** (`scripts/consolidate.py`) — run the deterministic gate
   (close-check, continuity, duplicates, coverage) and build the deliverables.

The **confirm-once** loop (what makes "many files, many formats" cheap over
time) is described in [`reference/MAPPING-PROFILES.md`](reference/MAPPING-PROFILES.md):

```
new institution statement
    └─ header auto-detect + mapping proposal
    └─ SHOW: resolved header table + 3-row canonical sample
    └─ ask_user_question  (ONE confirmation per NEW institution)
    └─ save to <workspace>\mappings\<institution>.json
existing institution statement
    └─ apply the identical mapping (zero confirms)
```

A mapping is a small JSON file the user edits, **not** a re-rolled guess. It
lives in the workspace (`<workspace>/mappings/`), travels with the user's data,
is easy to diff in git, and is trivially deletable when an institution is
retired. This preset is generic; *your* institution memory is in the workspace.

---

## Run it yourself (no agent, just the scripts)

The shipped `examples/` + `mappings/` are intentionally tiny and reconciling
so you can see the whole pipeline in ~five lines:

```powershell
# 1. ingest
py scripts\ingest.py examples\example-bank-2025Q1.csv \
     -o work\bank.raw.json --institution "Example Bank" \
     --account-type checking --currency USD --account-masked "****4821"
py scripts\ingest.py examples\example-credit-card-2025Q1.csv \
     -o work\card.raw.json --institution "Example Card" \
     --account-type credit --currency USD --account-masked "****8890"

# 2. apply mapping  (raw -> canonical)
py scripts\apply_mapping.py work\bank.raw.json  -m mappings\example-bank.json        -o work\bank.canonical.json  --institution "Example Bank" --account-masked "****4821"
py scripts\apply_mapping.py work\card.raw.json  -m mappings\example-credit-card.json -o work\card.canonical.json --institution "Example Card" --account-masked "****8890"

# 3. consolidate + reconcile + deliverable
py scripts\consolidate.py work\bank.canonical.json work\card.canonical.json \
     -o work\consolidated.xlsx --year 2025
```

Expected summary on the shipped examples: **2/2 close-checks PASS, 0 failures,
0 duplicates, 0 coverage gaps**.

On macOS / Linux replace `py` with `python3` (or `python`).

---

## A few hard non-negotiables (see SKILL.md)

* **Money discipline.** Sums in integer cents, never float. `two-column`
  statements compute `amount = credit − debit`; `signed-amount` statements
  parse the printed signed value. Never guess — quote the two numbers.
* **Date discipline.** `date_format` is declared per-institution in the mapping.
  `3/4/2025` is March 4 *in that institution's mapping* — that decision is
  auditable, not a guess.
* **No data loss.** `extras` holds every unmapped raw header verbatim; `raw`
  holds the full original row; `summary_lines` holds the lifted statement
  lines. `ignore[]` is the only way a header leaves the audit.
* **Stable IDs.** Row identity is `sha1-16` over (institution, account, date,
  description, amount, reference). Re-reads and double-imports are detected by
  this ID + an independent content signature.
* **The deliverable always ends** with `OUTPUTS` / `RECONCILIATION` /
  `ACCOUNTS` / `EXCEPTIONS` / `MAPPINGS USED`.

---

## What this preset is NOT

* **Not a PDF extractor.** PDF statements are out of scope on purpose — the
  companion [`ocr-md`](https://github.com/search?q=ocr-md) / `ocr-md-json`
  presets convert PDF → structured Markdown / JSON before this preset sees
  them. Pipe: `pdf → ocr-md → csv/xlsx → this preset`.
* **Not a tax / accounting engine.** It reconciles statements and produces a
  "big file" for your accountant or your own bookkeeping. It does not post
  entries, compute tax, or produce financial statements.
* **Not a cloud service.** No network, no API keys, no PHI beyond what the
  user already put in the input files (account numbers arrive pre-masked).

---

## Layout

```
statement-consolidator/
├─ agent.cordis.yml            # DSH persona: Bookkeeper / statement-consolidator
├─ preset.yml                  # display name + description
├─ INSTALL.cmd                 # one-shot deploy + prerequisite report (no auto-install)
├─ LICENSE                     # MIT
├─ README.md                   # this file
├─ skills/
│   └─ statement-consolidation/
│       └─ SKILL.md            # the protocol of record (8 steps, discipline, deliverable contract)
├─ reference/
│   ├─ CANONICAL-SCHEMA.md     # human-readable schema
│   ├─ CANONICAL-SCHEMA.json   # JSON Schema (draft-07) — validate your canonical files
│   ├─ MAPPING-PROFILES.md     # mapping file reference + confirm-once loop
│   ├─ RECONCILIATION.md       # the 5 checks + the gate's report shape
│   └─ SYNONYMS.md             # built-in Tier-2 discovery table
├─ mappings/
│   ├─ README.md
│   ├─ example-bank.json       # generic (no real institution) — start from this
│   └─ example-credit-card.json
├─ examples/
│   ├─ example-bank-2025Q1.csv        # two-column, checking (reconciles)
│   └─ example-credit-card-2025Q1.csv # signed-amount, credit  (reconciles)
└─ scripts/
    ├─ lib/
    │   ├─ __init__.py
    │   └─ common.py           # stdlib helpers: money, dates, stable_id, norm_header, SYNONYMS
    ├─ ingest.py               # CSV/XLSX -> raw statement JSON (header auto-detect)
    ├─ apply_mapping.py        # raw -> canonical rows (Tier-1 mapping, Tier-2 synonyms)
    └─ consolidate.py          # merge + reconcile + emit JSON/CSV/XLSX workbook
```

---

## License

MIT — see [LICENSE](LICENSE).
