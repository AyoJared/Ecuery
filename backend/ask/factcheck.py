"""Grounding check: is every number, date and rating in Gemini's answer actually in the data it was given?

Solana only proves an answer wasn't changed after it was made. This is what catches hallucinations:
each checkable claim in the answer must match the evidence (the exact JSON sent to Gemini), allowing
only for rounding. Unsupported claims trigger one rewrite; if any remain, the answer is flagged.
"""

import hashlib
import json
import re
from datetime import date, datetime

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
MONTH_RE = "|".join(list(MONTHS) + [m[:3] for m in MONTHS])
# Reference values Ecuery's own instructions use (health thresholds), always allowed.
ALWAYS_OK = {35.0, 55.0}
# Tokens that contain digits but aren't claims: pollutant names, units, "24-hour", "M2.5+" coverage notes
NOT_CLAIMS = re.compile(r"\bPM\s?2\.5\b|\bPM\s?10\b|\bNO2\b|\bCO2\b|\bO3\b|µg/m³|ft³/s|m³/s|\b24-hour\b|\b8-hour\b|"
                        r"\bM2\.5\+?|\b2\.5 and above\b|\bEF0-EF5\b", re.I)


def evidence_sha256(evidence: dict) -> str:
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _walk(obj, numbers: set, dates: set, strengths: set, texts: list):
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        numbers.add(float(obj))
    elif isinstance(obj, str):
        texts.append(obj)
        for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})", obj):
            try:
                dates.add(date(int(m[1]), int(m[2]), int(m[3])))
            except ValueError:
                pass
        for m in re.finditer(r"\b(EF\d|F\d|M\s?\d+(?:\.\d+)?)\b", obj):
            strengths.add(m[1].replace(" ", "").upper())
        for m in re.finditer(r"-?\d[\d,]*\.?\d*", obj):  # numbers inside strings ("7.32 mi", "M7.5")
            try:
                numbers.add(float(m[0].replace(",", "")))
            except ValueError:
                pass
    elif isinstance(obj, (datetime, date)):
        dates.add(obj if isinstance(obj, date) and not isinstance(obj, datetime) else obj.date())
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _walk(v, numbers, dates, strengths, texts)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            _walk(v, numbers, dates, strengths, texts)


def _decimals(token: str) -> int:
    return len(token.split(".")[1]) if "." in token else 0


def _number_ok(value: float, token: str, numbers: set) -> bool:
    if value in ALWAYS_OK:
        return True
    tol = 0.5 * 10 ** -_decimals(token) + 1e-9
    if any(abs(value - n) <= tol for n in numbers):
        return True
    # "12.6% lower" when the evidence has change_pct -12.6; "4.3 °C warmer" when difference is -4.3
    return any(abs(value - abs(n)) <= tol for n in numbers if n < 0)


def extract_claims(text: str) -> dict:
    clean = NOT_CLAIMS.sub(" ", text)
    claims = {"dates": [], "month_years": [], "strengths": [], "numbers": []}
    consumed = []

    def take(m):
        consumed.append(m.span())

    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", clean):
        claims["dates"].append((m[0], date(int(m[1]), int(m[2]), int(m[3])))); take(m)
    for m in re.finditer(rf"\b({MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b", clean, re.I):
        month = MONTHS.get(m[1].lower()) or next(v for k, v in MONTHS.items() if k.startswith(m[1].lower()[:3]))
        claims["dates"].append((m[0], (month, int(m[2]), int(m[3]) if m[3] else None))); take(m)
    for m in re.finditer(rf"\b({MONTH_RE})\.?\s+(\d{{4}})\b", clean, re.I):
        if not any(a <= m.start() < b for a, b in consumed):
            month = next(v for k, v in MONTHS.items() if k.startswith(m[1].lower()[:3]))
            claims["month_years"].append((m[0], month, int(m[2]))); take(m)
    for m in re.finditer(r"\b(EF\d|F\d|M\s?\d+(?:\.\d+)?)\b", clean):
        claims["strengths"].append(m[1].replace(" ", "").upper()); take(m)
    for m in re.finditer(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?", clean):
        if any(a <= m.start() < b for a, b in consumed):
            continue
        token = m[0].replace(",", "")
        claims["numbers"].append((m[0], float(token), token))
    return claims


def check(answer: str, evidence: dict, question: str = "") -> dict:
    numbers, dates, strengths, texts = set(), set(), set(), []
    _walk(evidence, numbers, dates, strengths, texts)
    q_numbers = {float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", question)}
    years = {d.year for d in dates} | {int(n) for n in numbers if n.is_integer() and 1900 <= n <= 2100}
    claims = extract_claims(answer)
    unsupported, checked = [], 0

    for text, value in claims["dates"]:
        checked += 1
        if isinstance(value, date):
            ok = value in dates
        else:
            month, day, year = value
            ok = any(d.month == month and d.day == day and (year is None or d.year == year) for d in dates)
        if not ok:
            unsupported.append(text)
    for text, month, year in claims["month_years"]:
        checked += 1
        if not (year in years and any(d.year == year and d.month == month for d in dates) or
                any(d.year == year for d in dates) and _span_covers(dates, year, month)):
            unsupported.append(text)
    for s in claims["strengths"]:
        checked += 1
        if s not in strengths:
            unsupported.append(s)
    for text, value, token in claims["numbers"]:
        if value.is_integer() and 1900 <= value <= 2100 and value in years:
            continue  # a year that's in the data / window
        checked += 1
        if not (_number_ok(value, token, numbers) or value in q_numbers):
            unsupported.append(text)
    return {"ok": not unsupported, "checked": checked, "unsupported": unsupported,
            "evidence_sha256": evidence_sha256(evidence)}


def _span_covers(dates: set, year: int, month: int) -> bool:
    """'November 2023' is fine when the evidence spans that month (e.g. plan start..end)."""
    target = date(year, month, 15)
    return bool(dates) and min(dates) <= target <= max(dates)


def feedback_text(unsupported: list[str]) -> str:
    return ("Your previous answer stated values that are not in the data: " + ", ".join(unsupported) +
            ". Rewrite the answer using only numbers, dates and ratings that appear in the data above; "
            "if the data doesn't contain something, say so instead of estimating.")


def grounded(generate, evidence: dict, question: str):
    """generate(feedback | None) -> Analysis. Check it; on unsupported claims, regenerate once with feedback."""
    result = generate(None)
    report = check(result.answer_text, evidence, question)
    if not report["ok"]:
        first = report["unsupported"]
        result = generate(feedback_text(first))
        report = check(result.answer_text, evidence, question) | {"retried": True, "first_attempt_unsupported": first}
    return result, report


def grounding_badge(fact: dict) -> dict:
    if fact["ok"]:
        return {"ok": True, "label": f"All {fact['checked']} figures match the source data" if fact["checked"]
                else "No figures to check"}
    return {"ok": False, "label": "Unverified figures: " + ", ".join(fact["unsupported"][:5])}
