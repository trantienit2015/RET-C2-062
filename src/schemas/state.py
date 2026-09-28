"""AgentCore Platform v1.0 — RET-C2-062 state schema."""

# Flat TypedDict only (msgpack-safe). Extend AgentState with agent-specific
# fields; no credentials, secrets, or Pydantic models in State.

from typing import NotRequired

from framework.schemas.agent_state import AgentState


# Type-check note: the wheel ships no py.typed, so mypy resolves AgentState to Any
# and reports every NotRequired below as valid-type. The fields are correct (the state
# contract requires NotRequired) -- the report is a packaging artifact, suppressed per field.
# Drop these ignores once the wheel ships py.typed.
class State(AgentState):
    """Retail Customer Satisfaction Survey Analysis & Report Agent state.

    Shared fields (user_input, validated_input, status, node_history, result,
    formatted_output, ...) are inherited from AgentState. All agent-specific
    fields are NotRequired[...] and read via state.get(...).
    """

    # Parsed + de-identified survey responses (Likert + free-text), post S-2 PII strip.
    survey_responses: NotRequired[list[dict]]  # type: ignore[valid-type]
    # Comparison period config supplied by the caller (e.g. {"current": "...", "prior": "..."}).
    comparison_period: NotRequired[dict]  # type: ignore[valid-type]
    # Count of responses where PII was detected and stripped (audit-only, no raw content).
    pii_stripped_count: NotRequired[int]  # type: ignore[valid-type]
    # Per-response sentiment classification (Japan high-context implicit-dissatisfaction detection).
    sentiment_results: NotRequired[list[dict]]  # type: ignore[valid-type]
    # Recurring themes extracted from de-identified free-text.
    theme_clusters: NotRequired[list[dict]]  # type: ignore[valid-type]
    # Current-vs-prior period metric deltas.
    period_deltas: NotRequired[dict]  # type: ignore[valid-type]
    # Final structured Japanese management report (aggregate-only, S-3 enforced).
    management_report: NotRequired[dict]  # type: ignore[valid-type]
