# Reconciliation gate

The reconciliation gate is the non-negotiable step between "the big file is
built" and "done". It runs in `consolidate.py`, is entirely model-free, and its
output is the audit trail for the final workbook. If a check fails, the
deliverable still ships — but the failure is QUOTED in the deliverable contract,
not smoothed over.

## 1. Per-statement close-check

For each statement (canonical JSON) that carries BOTH an opening and a closing
balance:

```
expected  = opening_balance + Σ(row.amount)
actual    = closing_balance
pass if   |actual − expected| ≤ 0.01
```

- For `two-column` statements `row.amount = credit − debit`, so `Σ(amount)` is
  already the net change and the formula is identical to
  `opening + Σ(credit) − Σ(debit)`.
- For `signed-amount` statements `Σ(amount)` is the signed net change.
- If the statement has NO opening or closing balance, the check is `na` (not a
  pass, not a fail) — say so in the deliverable. Do NOT fabricate a balance to
  make it pass.
- If a row's date or amount is unparseable it is excluded from `Σ(amount)` and
  listed in Exceptions. A failing close-check with unparseable rows is the most
  common first-pass signal of a signing-convention error → confirm the mapping's
  `sign_convention` and re-run.

### Why this is the gate

It is the single check that catches: a mis-detected header row, a sign
convention error (all debits counted as credits), an off-by-one row, a summary
line that was accidentally read as a transaction (or vice-versa), any duplicated
transaction, a dropped or duplicated statement. It is cheaper to report it as
"close-check failed: opening 1,000.00 + change 5,450.11 = 6,450.11 expected,
6,403.51 printed" than to find it on the accountant's side.

## 2. Cross-statement continuity

For each (institution, account_masked):

1. Sort that account's statements by `period_start`.
2. For each consecutive pair (S[i], S[i+1]):
   - `S[i].closing_balance` should equal `S[i+1].opening_balance`.
   - `S[i].period_end` should be within ~1–2 days of `S[i+1].period_start`
     (a 1-day gap is fine — month-end statements often post a day late; a 30-day
     gap is a coverage hole).
3. Report each break: which account, which pair, the two numbers, and the gap
   in days.

This is the check that catches a **double-import** (same statement appears twice
in the input set → continuity breaks because the second occurrence's opening
does not equal the first occurrence's closing), a **missing statement** (a
month's file never landed in the folder), and a **statement split** (one
calendar month's transactions in two files).

## 3. Duplicate / double-import detection

Across files (the classic year-end error — the same statement imported from two
sources):

1. Compute `id` for every canonical row (stable hash, see CANONICAL-SCHEMA.md §3).
2. **Exact re-reads**: a `id` that appears more than once in the input set (the
   same row re-imported) → dedupe, keep one, count removals.
3. **Cross-file same-content**: rows with the same (source_institution,
   account_masked, date, `round(amount,2)`, `norm(description)`) that appear in
   2+ DISTINCT source files → flag `dup=true` on the second-and-later occurrences,
   list them in the Duplicates sheet. Keep all of them in the master rows array
   (never silently merge) — the flag + sheet is the audit.
4. If a flagged duplicate set also breaks the close-check on one of its
   statements, surface BOTH findings together (they are the same root cause).

## 4. Month-coverage

For each account, over the requested year (or the min-date..max-date range,
whichever the user scoped):

```
months_present = { row.date[:7] for row in account_rows }
years_requested = 2025  # or the user's scope
months_expected = [ "2025-01", ..., "2025-12" ]   # intersected with the account's lifetime span
missing = months_expected − months_present
```

- A month with zero rows for an account that clearly should have activity in
  that month is a coverage finding → list it in the Coverage Gaps sheet.
- An account that only appears part of the year (opened mid-year, closed
  mid-year) is not a finding if the user's scope excludes the out-of-lifetime
  months; note it in Accounts & Summaries, not Coverage Gaps.
- Coverage is scoped to the year(s) the user named for the consolidation; a
  full-year consolidation with a `2025-06` hole on a checking account is a
  finding.

## 5. The gate's report shape

`consolidate.py` emits (and the Excel workbook renders) five blocks:

1. **Reconciliation** — one row per statement: source_file, account, period,
   opening, closing, expected, actual, delta, PASS/FAIL/NA.
2. **Continuity** — one row per statement pair (per account): prev_file, next_file,
   prev_closing, next_opening, delta, PASS/FAIL.
3. **Duplicates** — one row per flagged duplicate set: institution, account,
   date, amount, description, files, row-ids.
4. **Coverage Gaps** — one row per (account, missing month): account, month,
   expected, actual (0), context.
5. **Exceptions** — one row per anomaly: row id, source_file, field, raw value,
   reason (unparseable date / unparseable amount / unmapped header → extras /
   Tier-2 matched / dup / close-check-fail).

## 6. Delivery rule

The deliverable contract (SKILL.md §6) block 2 — RECONCILIATION — quotes the
gate's output verbatim: which accounts PASSED, which FAILED (with both the
expected and the printed number), which were NA, and the full list of
continuity breaks, duplicates, coverage gaps, and exceptions. **A consolidation
with a failing close-check is not a successful consolidation.** Ship the file,
quote the failure, name the offending rows — and stop.
