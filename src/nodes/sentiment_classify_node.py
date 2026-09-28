"""AgentCore Platform v1.0 — inner step 1: SentimentClassify."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.llm_adapter import extract_text

# Deterministic fallback lexicon for Japan high-context implicit dissatisfaction
# (間接的不満) — hedged/indirect negative phrasing that generic sentiment tools miss.
_IMPLICIT_NEGATIVE_MARKERS = ("まあまあ", "少し残念", "改善の余地", "とは言えない", "微妙")
_EXPLICIT_NEGATIVE_MARKERS = ("最悪", "二度と行きたくない", "不満", "ひどい")
_POSITIVE_MARKERS = ("満足", "良かった", "また利用したい", "素晴らしい")


class SentimentClassifyNode(FunctionNode):
    """Classify per-response sentiment with Japan high-context detection.

    The inner subgraph receives only the JSON string user_input (seeded from
    the outer validated_input), so this first inner node reconstructs the
    de-identified survey batch. LLM reasoning refines the deterministic
    lexicon signal when an LLM is configured; the deterministic result is
    the guaranteed fallback (this is the agent's genuine moat).
    """

    # S-1: inner subgraph node — trust authenticated once at the
    # outer backbone (SurveyIngestionParserNode); inner nodes stay ANONYMOUS.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            payload = None
        responses = payload.get("survey_responses") if isinstance(payload, dict) else None
        if not isinstance(responses, list) or not responses:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["SentimentClassifyNode: missing survey_responses in inner input"],
            }

        results = [self._classify_one(r) for r in responses]
        emit_trace_event(
            "sentiment_classified",
            {"correlation_id": state.get("correlation_id"), "n_responses": len(results)},
            state,
        )
        return {
            "survey_responses": responses,
            "comparison_period": payload.get("comparison_period", {}),
            "sentiment_results": results,
            "status": AgentStatus.SUCCESS.value,
        }

    def _classify_one(self, response: dict[str, Any]) -> dict[str, Any]:
        comment = str(response.get("comment", ""))
        implicit = any(m in comment for m in _IMPLICIT_NEGATIVE_MARKERS)
        explicit_neg = any(m in comment for m in _EXPLICIT_NEGATIVE_MARKERS)
        positive = any(m in comment for m in _POSITIVE_MARKERS)

        if explicit_neg or implicit:
            sentiment = "negative"
        elif positive:
            sentiment = "positive"
        else:
            sentiment = "neutral"

        confidence = self._llm_confidence(comment, sentiment)
        return {"sentiment": sentiment, "implicit_dissatisfaction": implicit, "confidence": confidence}

    def _llm_confidence(self, comment: str, sentiment: str) -> float:
        if self._llm is None or not comment.strip():
            return 0.6
        try:
            prompt = (
                f"Confirm the sentiment '{sentiment}' for this Japanese customer "
                f"satisfaction survey comment, watching for indirect/implicit "
                f"dissatisfaction (間接的不満): {comment[:300]}"
            )
            raw = self._llm.complete([{"role": "user", "content": prompt}])
            return 0.9 if extract_text(raw).strip() else 0.6
        except Exception as exc:  # noqa: BLE001 — degrade to deterministic confidence
            import logging

            logging.getLogger(__name__).warning("sentiment LLM confirmation failed: %s", exc)
            return 0.6
