# Built-in synonym table (Tier-2 discovery)

This is the fallback the matching engine uses when the user's mapping does not
explicitly alias a canonical field. Both sides are normalized
(`norm_header`: lowercase, punctuation stripped, whitespace collapsed) before
comparing, so `"Ref #"` ≡ `"ref"` ≡ `"refnum"` for the purpose of matching this
table.

The agent proposes a mapping FROM the user's actual raw headers, so in practice
Tier-2 mostly matters for the first encounter with an unfamiliar institution
whose headers are close to (but not exactly) these tokens.

| Canonical field | Synonyms (normalized) |
|---|---|
| `date` | `date` · `post date` · `posting date` · `transaction date` · `value date` · `val date` · `trx date` |
| `post_date` | `post date` · `posting date` · `posted date` |
| `description` | `description` · `particulars` · `details` · `payee` · `to` · `memo` · `narration` · `transaction` · `vendor` · `merchant` · `particular` · `narrative` |
| `reference` | `ref` · `reference` · `ref no` · `ref num` · `txn` · `txn id` · `transaction id` · `reference number` · `transaction no` · `ref id` |
| `check_number` | `chq` · `chq no` · `check no` · `check number` · `cheque no` |
| `amount` | `amount` · `amt` · `net amount` · `transaction amount` |
| `amount_debit` | `debit` · `withdrawal` · `amount out` · `dr` · `withdrawn` · `paid` |
| `amount_credit` | `credit` · `deposit` · `amount in` · `cr` · `deposited` · `received` · `refund` |
| `balance` | `balance` · `running balance` · `bal` · `current balance` · `balance after` |
| `fee` | `fee` · `service charge` · `admin fee` · `fee amount` |
| `interest` | `interest` · `interest paid` · `interest charged` · `interest earned` · `int` |

## How the engine uses it

`apply_mapping.py` builds a resolver in this order:

1. For each canonical field named in `mapping.columns`, for each alias in the
   list, look up the raw header whose normalized form matches.
2. For each canonical field NOT matched in step 1 (and not in
   `mapping.ignore`), fall back to this table: the raw header (if any) whose
   normalized form is in the field's synonym set. Mark the field
   `"matched_by": "synonym"` in the resolved-header audit, and surface it in the
   Exceptions output as "Tier-2 matched" so the user can promote
   (or reject) it into the mapping.
3. Any raw header not claimed by steps 1 or 2, and not in `ignore`, goes to
   `extras` on every row, verbatim.

## Extending the table

The table is the ONLY fallback. If a raw header the user has seen is not in this
table and not in the mapping, the agent's job is to add the alias to the
mapping's `columns` list — NOT to add a new line to this file. This file is the
generic floor; the mapping is the per-institution memory.
