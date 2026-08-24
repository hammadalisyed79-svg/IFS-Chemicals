"""Translate cash-book narrations to Urdu for director print (ledger report only)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache

# Longer phrases first (applied in order)
_PHRASE_MAP: list[tuple[str, str]] = [
    (r"FUEL\s+EXPENSE", "ایندھن کا خرچ"),
    (r"fuel\s+expense", "ایندھن کا خرچ"),
    (r"Mobile\s+charges", "موبائل چارجز"),
    (r"mobile\s+charges", "موبائل چارجز"),
    (r"toll\s+tax", "ٹول ٹیکس"),
    (r"Lunch\s+Route", "دوپہر کا روٹ"),
    (r"lunch\s+route", "دوپہر کا روٹ"),
    (r"bill\s+tea", "چائے کا بل"),
    (r"Receipt\s+from", "وصولی از"),
    (r"receipt\s+from", "وصولی از"),
    (r"Payment\s+to", "ادائیگی"),
    (r"payment\s+to", "ادائیگی"),
    (r"Customer\s+Receipt", "گاہک کی وصولی"),
    (r"Supplier\s+Payment", "سپلائر کی ادائیگی"),
    (r"Expense\s+Payment", "اخراجات کی ادائیگی"),
    (r"Party\s+Transfer", "پارٹی ٹرانسفر"),
    (r"Journal\s+Voucher", "جرنل واؤچر"),
    (r"Cash\s+Book", "روزنامچہ نقدی"),
    (r"Bank\s+Book", "روزنامچہ بینک"),
    (r"\bSale\b", "فروخت"),
    (r"\bReceipt\b", "وصولی"),
    (r"\bPayment\b", "ادائیگی"),
    (r"\bEXPENSE\b", "خرچ"),
    (r"\bExpense\b", "خرچ"),
    (r"\bMonth\b", "ماہ"),
    (r"\bRoute\b", "روٹ"),
    (r"\bvia\b", "بطریق"),
    (r"\bfrom\b", "سے"),
    (r"\bby\b", "از طرف"),
    (r"\bto\b", "کو"),
    (r"\bsb\b", "صاحب"),
    (r"\bSkt\b", "سکندر"),
    (r"\bSKT\b", "سکندر"),
]

_TOKEN_RE = re.compile(
    r"(?:"
    r"[A-Z]{2,}[-/][A-Za-z0-9]+|"  # SAL-26060018, LCT-5435
    r"GTS[-\s]?\d+|"  # GTS-576
    r"[A-Z]{2,}\d{4,}|"
    r"Rs\.?\s*[\d,]+(?:\.\d+)?|"
    r"\d{4}-\d{2}-\d{2}|"
    r"\d+(?:\.\d+)?"
    r")",
    re.IGNORECASE,
)

_PLACEHOLDER = "⟦{i}⟧"


def _protect_tokens(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def repl(m: re.Match) -> str:
        tokens.append(m.group(0))
        return _PLACEHOLDER.format(i=len(tokens) - 1)

    return _TOKEN_RE.sub(repl, text), tokens


def _restore_tokens(text: str, tokens: list[str]) -> str:
    for i, tok in enumerate(tokens):
        text = text.replace(_PLACEHOLDER.format(i=i), tok)
    return text


def _apply_phrase_map(text: str) -> str:
    for pat, ur in _PHRASE_MAP:
        text = re.sub(pat, ur, text, flags=re.IGNORECASE)
    return text


_LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9\s.'-]*")


@lru_cache(maxsize=512)
def _translate_online_cached(text: str) -> str:
    if not text or not str(text).strip():
        return text or ""
    q = str(text).strip()[:450]
    params = urllib.parse.urlencode({
        "client": "gtx",
        "sl": "en",
        "tl": "ur",
        "dt": "t",
        "q": q,
    })
    url = f"https://translate.googleapis.com/translate_a/single?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "IFS-ERP/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        parts = payload[0] if payload else []
        return "".join(p[0] for p in parts if p and p[0]) or text
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError):
        return text


def _translate_latin_runs(text: str) -> str:
    """Translate only English fragments so phrase-map Urdu is kept."""

    def repl(m: re.Match) -> str:
        chunk = m.group(0).strip()
        if len(chunk) < 2 or not re.search(r"[A-Za-z]{2,}", chunk):
            return m.group(0)
        return _translate_online_cached(chunk)

    return _LATIN_RUN.sub(repl, text)


def translate_narration_to_urdu(text: str, *, use_online: bool = True) -> str:
    """English narration → Urdu; keeps voucher refs, dates, and amounts unchanged."""
    if not text:
        return ""
    raw = str(text).strip()
    if re.search(r"[\u0600-\u06FF]", raw):
        return raw
    protected, tokens = _protect_tokens(raw)
    mapped = _apply_phrase_map(protected)
    if use_online and re.search(r"[A-Za-z]{2,}", mapped):
        mapped = _translate_latin_runs(mapped)
    mapped = _apply_phrase_map(mapped)
    return _restore_tokens(mapped, tokens)


def translate_ledger_rows(rows: list[dict], cache: dict | None = None) -> list[dict]:
    """Copy rows with particulars translated for Urdu print."""
    cache = cache if cache is not None else {}
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        p = str(r.get("particulars", "") or "")
        if p not in cache:
            cache[p] = translate_narration_to_urdu(p)
        row["particulars"] = cache[p]
        out.append(row)
    return out
