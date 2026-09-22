"""Shared, model-free helpers for the statement-consolidator preset.

Stdlib only (csv, json, datetime, decimal, hashlib, re). Money and dates are
parsed deterministically; a stable id is derived from a row's identity; header
matching normalizes both sides (case/punctuation-insensitive). No network, no
third-party deps, no PHI.
"""
from __future__ import annotations

import datetime
import json
import re
import hashlib
from decimal import Decimal
from pathlib import Path

# Canonical fields the schema can name (priority order for resolution).
CANONICAL_FIELDS = [
    "date", "post_date", "description", "reference", "check_number",
    "amount", "amount_debit", "amount_credit", "fee", "interest", "balance",
]

# Built-in Tier-2 synonym table (values are NORMALIZED forms). Used when a
# mapping does not explicitly alias a canonical field, and to score header-row
# detection. See reference/SYNONYMS.md.
SYNONYMS = {
    "date":         {"date", "post date", "posting date", "transaction date",
                     "value date", "val date", "trx date", "transaction"},
    "post_date":    {"post date", "posting date", "posted date"},
    "description":  {"description", "particulars", "details", "payee", "to",
                     "memo", "narration", "transaction", "vendor", "merchant",
                     "particular", "narrative"},
    "reference":    {"ref", "reference", "ref no", "ref num", "txn", "txn id",
                     "transaction id", "reference number", "transaction no",
                     "ref id", "cheque no", "cheq no"},
    "check_number": {"chq", "chq no", "check no", "check number", "cheque no"},
    "amount":       {"amount", "amt", "net amount", "transaction amount",
                     "amount usd"},
    "amount_debit": {"debit", "withdrawal", "amount out", "dr", "withdrawn",
                     "paid"},
    "amount_credit": {"credit", "deposit", "amount in", "cr", "deposited",
                      "received", "refund"},
    "balance":      {"balance", "running balance", "bal", "current balance",
                     "balance after"},
    "fee":          {"fee", "service charge", "admin fee", "fee amount",
                     "maintenance fee", "annual fee"},
    "interest":     {"interest", "int", "interest paid", "interest charged",
                     "interest earned", "int paid", "int earned"},
}


def norm_header(h) -> str:
    """Normalize a header / alias for matching: lowercase, strip punctuation,
    collapse whitespace. 'Ref #' -> 'ref'; 'Transaction Date' -> 'transaction date'."""
    if h is None:
        return ""
    s = str(h).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_money(value):
    """Parse a money value to a Decimal.

    Returns None when the value is empty/None. Raises ValueError when the value
    is non-empty but not a number (callers route these to `extras` + `raw` and
    flag them). Handles: commas, currency symbols, accounting parens (negative),
    trailing ' Dr'/' Cr' markers, leading/trailing whitespace, and numbers that
    already came in as int/float (e.g. xlsx numeric cells).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"unparseable amount: {value!r}")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(repr(value))
    s = str(value).strip()
    if s == "":
        return None
    neg = False
    if s[0] == "(" and s[-1] == ")":
        neg = True
        s = s[1:-1].strip()
    low = s.lower()
    if low.endswith(" dr"):
        neg = True
        s = s[:-3].strip()
    elif low.endswith(" cr"):
        neg = False
        s = s[:-3].strip()
    cleaned = re.sub(r"[^0-9.\-+]", "", s)
    if cleaned == "" or cleaned in ("-", "+", "."):
        raise ValueError(f"unparseable amount: {value!r}")
    d = Decimal(cleaned)
    if neg:
        d = -d
    return d


_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")


def _valid_iso(y, m, d):
    try:
        return datetime.datetime(int(y), int(m), int(d)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def parse_date(value, fmt=None):
    """Parse a date-like value to ISO 'YYYY-MM-DD', or None if unparseable.

    Tries an ISO match first, then `fmt` (the mapping's declared convention),
    then a fixed ladder (US month-first, then day-first, then year-first).
    """
    if value is None:
        return None
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if not s:
        return None
    m = _ISO_RE.match(s)
    if m:
        return _valid_iso(m.group(1), m.group(2), m.group(3))
    seen = []
    if fmt:
        seen.append(fmt)
    seen += [
        "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m.%d.%Y",
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
        "%d %b %Y", "%d-%b-%Y", "%b %d %Y", "%d %B %Y", "%B %d %Y",
    ]
    for f in dict.fromkeys(seen):
        try:
            dt = datetime.datetime.strptime(s, f)
        except ValueError:
            continue
        return _valid_iso(dt.year, dt.month, dt.day)
    return None


def stable_id(*parts) -> str:
    """Deterministic short id from a row's identity parts. Same content -> same id."""
    key = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:16]


def load_mapping(path) -> dict:
    """Load a mapping file. Mappings are JSON (stdlib-only); a .yml/.yaml file
    must be valid JSON for this preset to parse it without a YAML dependency."""
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8-sig"))


def read_text_utf8(path) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def norm_desc(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())
