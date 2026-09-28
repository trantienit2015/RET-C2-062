"""AgentCore Platform v1.0 — outer pre_process: SurveyIngestionParser (S-1 + S-2)."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services import survey_service as svc

MAX_INPUT_CHARS = 200_000


class SurveyIngestionParserNode(FunctionNode):
    """Parse a mixed structured (Likert) + free-text survey batch and strip PII.

    Accepts a JSON payload:
        {"responses": [{"likert": {...}, "comment": "<text>"}, ...],
         "comparison_period": {...}}
    Deterministic parse (tool-call, not LLM) followed by an enforced S-2 PII
    strip on free-text comments before any downstream node sees them.
    Serializes the de-identified batch to validated_input (JSON string) for
    the inner subgraph.
    """

    # S-1: outer boundary node — matches agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        emit_trace_event(
            "survey_ingestion_started",
            {"correlation_id": state.get("correlation_id")},
            state,
        )
        if not isinstance(raw, str) or not raw.strip():
            return {"status": AgentStatus.ERROR.value, "error_log": ["SurveyIngestionParserNode: empty input"]}
        if len(raw) > MAX_INPUT_CHARS:
            return {"status": AgentStatus.ERROR.value, "error_log": ["SurveyIngestionParserNode: input too large"]}

        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return {"status": AgentStatus.ERROR.value, "error_log": ["SurveyIngestionParserNode: payload must be JSON"]}
        if not isinstance(payload, dict):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["SurveyIngestionParserNode: payload must be a JSON object"],
            }

        responses = svc.parse_survey_batch(payload)
        if not responses:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["SurveyIngestionParserNode: no valid survey responses"],
            }

        de_identified, pii_count = svc.strip_pii(responses)
        comparison_period = (
            payload.get("comparison_period") if isinstance(payload.get("comparison_period"), dict) else {}
        )

        validated = {"survey_responses": de_identified, "comparison_period": comparison_period}
        emit_trace_event(
            "survey_pii_stripped",
            {"correlation_id": state.get("correlation_id"), "pii_stripped_count": pii_count},
            state,
        )
        return {
            "survey_responses": de_identified,
            "comparison_period": comparison_period,
            "pii_stripped_count": pii_count,
            "validated_input": json.dumps(validated, ensure_ascii=False),
            "status": AgentStatus.SUCCESS.value,
        }
