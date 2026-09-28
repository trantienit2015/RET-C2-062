"""AgentCore Platform v1.0 — outer post_process: ReportNarrate (S-3 gate)."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import survey_service as svc
from src.services.llm_adapter import extract_text

_FORBIDDEN_IDENTIFIER_KEYS = ("respondent_id", "respondent_name", "raw_comment")


class ReportNarrateNode(FunctionNode):
    """Generate the structured Japanese management report.

    Enforced S-3 aggregate-only output gate: FAIL (no suppress, log) if any
    individual respondent is identifiable — either PII-shaped text leaking
    into the narrative, or a per-respondent identifier key present in the
    report structure (APPI compliance).
    """

    # S-1: outer boundary node — matches agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        status = state.get("status")
        if status in ("error", "ERROR") or getattr(status, "value", None) == "error":
            emit_trace_event(
                "report_skipped_upstream_error",
                {"correlation_id": state.get("correlation_id")},
                state,
            )
            return {"status": AgentStatus.ERROR.value}

        theme_clusters = state.get("theme_clusters") or []
        period_deltas = state.get("period_deltas") or {}
        sentiment_results = state.get("sentiment_results") or []
        pii_stripped_count = state.get("pii_stripped_count", 0)

        summary = self._narrate(theme_clusters, period_deltas, len(sentiment_results))
        report = {
            "summary": summary,
            "period_metrics": period_deltas,
            "themes": theme_clusters,
            "n_responses": len(sentiment_results),
            "pii_stripped_count": pii_stripped_count,
            "aggregate_only": True,
        }

        emit_trace_event(
            "report_narrated",
            {"correlation_id": state.get("correlation_id"), "n_themes": len(theme_clusters)},
            state,
        )
        return {
            "management_report": report,
            "formatted_output": report,
            "status": AgentStatus.SUCCESS.value,
        }

    def _narrate(self, theme_clusters: list[dict[str, Any]], period_deltas: dict[str, Any], n_responses: int) -> str:
        top_themes = ", ".join(t.get("theme", "") for t in theme_clusters[:3]) or "特筆すべきテーマなし"
        current = period_deltas.get("current", {}) if isinstance(period_deltas, dict) else {}
        base = (
            f"当期の調査回答は{n_responses}件。主要テーマ: {top_themes}。"
            f"ネガティブ比率: {current.get('negative_rate', 0.0)}、"
            f"暗黙的不満比率: {current.get('implicit_dissatisfaction_rate', 0.0)}。"
        )
        return self._llm_narrate(base) or base

    def _llm_narrate(self, base_summary: str) -> str:
        if self._llm is None:
            return ""
        try:
            prompt = f"Expand this Japanese management report summary: {base_summary}"
            raw = self._llm.complete([{"role": "user", "content": prompt}])
            return extract_text(raw).strip()
        except Exception as exc:  # noqa: BLE001 — degrade to deterministic summary
            import logging

            logging.getLogger(__name__).warning("report LLM narration failed: %s", exc)
            return ""

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-3 aggregate-only enforcement (framework-invoked; never raises)."""
        report = state.get("management_report") or {}
        if not report:
            return state

        for key in _FORBIDDEN_IDENTIFIER_KEYS:
            if key in report:
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": [f"ReportNarrateNode: forbidden per-respondent identifier key '{key}' in output"],
                }

        report_text = json.dumps(report, ensure_ascii=False)
        if svc.contains_pii(report_text):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ReportNarrateNode: PII-shaped content detected in output — aggregate-only violated"],
            }

        if report.get("aggregate_only") is not True:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ReportNarrateNode: aggregate_only marker missing/false"],
            }

        return state
