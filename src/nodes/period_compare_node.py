"""AgentCore Platform v1.0 — inner step 3: PeriodCompare."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import survey_service as svc


class PeriodCompareNode(FunctionNode):
    """Deterministic current-vs-prior period metric aggregation (tool-call).

    Last inner step: combines SentimentClassify output with the caller-supplied
    comparison_period config into current/prior/delta metrics.
    """

    # S-1: inner subgraph node — ANONYMOUS (trust authenticated at outer backbone).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        sentiment_results = state.get("sentiment_results")
        if not isinstance(sentiment_results, list) or not sentiment_results:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["PeriodCompareNode: missing sentiment_results"],
            }

        comparison_period = state.get("comparison_period") or {}
        deltas = svc.aggregate_period_metrics(sentiment_results, comparison_period)

        emit_trace_event(
            "period_compared",
            {"correlation_id": state.get("correlation_id"), "has_prior": deltas.get("prior") is not None},
            state,
        )
        return {"period_deltas": deltas, "status": AgentStatus.SUCCESS.value}
