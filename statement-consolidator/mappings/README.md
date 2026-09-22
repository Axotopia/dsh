# Institution mappings

This folder is the **starting point** for your per-institution field mappings.
The two files here are **generic, sanitized examples** (no real institution
names, account numbers, or balances) that reproduce the demo statements in
`examples/`. They exist so you can run the scripts and see the full pipeline —
ingest → map → reconcile — with zero external data.

## How to use this folder

1. **Copy** an example to the workspace (the place the agent keeps mappings):

   ```powershell
   Copy-Item mappings\example-bank.json      ..\mappings\example-bank.json
   Copy-Item mappings\example-credit-card.json ..\mappings\amex.json
   ```

   (In practice the agent does this for you: on a NEW institution it proposes a
   mapping, you confirm once, and it saves to `<workspace>\mappings\<institution>.json`.)

2. **Edit** the copy to match your real institution: `detect`, `account_type`,
   `currency`, `sign_convention`, `date_format`, `columns` (multi-variant header
   lists), and `classify` (fee/interest words).

3. The engine matches a raw header against each canonical field's alias list
   (punctuation/case-insensitive); anything not claimed → `extras` (never
   dropped). See `reference/MAPPING-PROFILES.md` for the full field reference.

## What belongs here vs. what does NOT

- **Here (generic, shipped):** the two example mappings + this README. The preset
  is a template and stays generic.
- **In the workspace, not here (your data):** your real institution mappings,
  learned and confirmed per institution. These travel with your financial data,
  are easy to diff in git, and are trivially deletable when an institution is
  retired.

## Adding a new institution

Copy `example-bank.json` (or the card one), rename to `<institution>.json`, and
change:
- `institution` + `detect` — your institution's name / filename tokens.
- `columns` — the raw header names your statement actually uses.
- `sign_convention` — `two-column` (separate Debit/Credit) or `signed-amount`
  (one signed Amount column).
- `date_format` — your statement's date style (`%m/%d/%Y`, `%d/%m/%Y`, …).
- `classify.fee` / `classify.interest` — the words that mark fee and interest
  rows on your statement, for the typed `fee`/`interest` subtotals.

Then confirm it against a 3-row sample once (see `reference/MAPPING-PROFILES.md`).
