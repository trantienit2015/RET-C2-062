"""AgentCore Platform v1.0 — RET-C2-062 deterministic survey helpers.

Pure, side-effect-free functions used by nodes (SurveyIngestionParser,
PeriodCompare). No agenticstar imports, no credentials, no I/O.
"""

from __future__ import annotations

import re
from typing import Any

from framework.security import detect_credentials, detect_pii

# S-2/S-3 PII detection reuses the framework detectors: detect_pii (email, phone,
# My Number, card numbers, labelled Japanese names, ...) and detect_credentials
# (JWT, Bearer tokens, API keys). The Latin-script "name" heuristic of detect_pii
# is skipped: it matches any two Title Case words and would redact ordinary text.
_IGNORED_PII_TYPES = frozenset({"name"})
# Residual template pattern: Japanese phone numbers written without separators
# or with a single hyphen (0312345678, 03-12345678), which detect_pii's phone_jp
# pattern does not match. Bounded quantifiers only.
_PHONE_JP_RESIDUAL_RE = re.compile(r"(?<!\d)0\d{1,4}-?\d{1,4}-?\d{3,4}(?!\d)")


def _pii_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of PII / credential findings in `text`, merged and sorted."""
    spans = [(f["start"], f["end"]) for f in detect_pii(text) if f["type"] not in _IGNORED_PII_TYPES]
    spans += [(f["start"], f["end"]) for f in detect_credentials(text)]
    spans += [m.span() for m in _PHONE_JP_RESIDUAL_RE.finditer(text)]
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _redact(text: str) -> tuple[str, bool]:
    spans = _pii_spans(text)
    for start, end in reversed(spans):
        text = text[:start] + "[REDACTED]" + text[end:]
    return text, bool(spans)


def parse_survey_batch(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic parse of a mixed structured (Likert) + free-text survey batch.

    Expected shape: {"responses": [{"likert": {...}, "comment": "<text>"}, ...]}.
    Returns a normalized list; malformed entries are dropped, not raised.
    """
    raw_responses = payload.get("responses") if isinstance(payload, dict) else None
    if not isinstance(raw_responses, list):
        return []
    normalized = []
    for entry in raw_responses:
        if not isinstance(entry, dict):
            continue
        likert = entry.get("likert") if isinstance(entry.get("likert"), dict) else {}
        comment = str(entry.get("comment", "") or "")
        normalized.append({"likert": likert, "comment": comment})
    return normalized


def strip_pii(responses: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """S-2: redact PII-shaped content from free-text comments before downstream use.

    Returns (de-identified responses, count of responses where PII was stripped).
    """
    cleaned: list[dict[str, Any]] = []
    stripped_count = 0
    for resp in responses:
        redacted, hit = _redact(str(resp.get("comment", "")))
        if hit:
            stripped_count += 1
        cleaned.append({"likert": resp.get("likert", {}), "comment": redacted})
    return cleaned, stripped_count


def contains_pii(text: str) -> bool:
    """Re-scan helper used by the S-3 aggregate-only output gate."""
    return bool(_pii_spans(text))


def aggregate_period_metrics(
    sentiment_results: list[dict[str, Any]],
    comparison_period: dict[str, Any],
    prior_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic current-vs-prior period metric aggregation.

    `prior_metrics` (optional) carries the prior-period baseline supplied by the
    caller via `comparison_period`; when absent, only current-period metrics are
    returned (delta fields become None).
    """
    total = len(sentiment_results)
    negative = sum(1 for r in sentiment_results if r.get("sentiment") == "negative")
    implicit_negative = sum(1 for r in sentiment_results if r.get("implicit_dissatisfaction"))
    current = {
        "total_responses": total,
        "negative_rate": round(negative / total, 4) if total else 0.0,
        "implicit_dissatisfaction_rate": round(implicit_negative / total, 4) if total else 0.0,
    }
    prior = prior_metrics or (comparison_period.get("prior_metrics") if isinstance(comparison_period, dict) else None)
    if not isinstance(prior, dict):
        return {"current": current, "prior": None, "deltas": None}
    deltas = {
        key: round(current[key] - prior.get(key, 0.0), 4) for key in ("negative_rate", "implicit_dissatisfaction_rate")
    }
    return {"current": current, "prior": prior, "deltas": deltas}
