"""AgentCore Platform v1.0 — RET-C2-062 outer graph (Cat 2).

Outer (AgentBaseGraph): initialize -> pre_process(SurveyIngestionParser)
-> main(SurveyAnalysisGraphNode) -> post_process(ReportNarrate) -> finalize.
Inner (BaseGraph): sentiment_classify -> theme_extract -> period_compare.

The GraphNode wrapper lives in THIS file (not src/nodes/) so the PB-6
invoke-order probe does not mis-assert its deliberately-delegated lifecycle.
"""

from typing import Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.report_narrate_node import ReportNarrateNode
from src.nodes.survey_ingestion_parser_node import SurveyIngestionParserNode
from src.schemas.state import State


class SurveyAnalysisGraphNode(GraphNode):
    """Wraps the inner sentiment/theme/period-compare workflow (main slot)."""

    # S-1: outer boundary node (main slot, first to receive dispatched input) —
    # matches agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, llm: Any = None) -> None:
        super().__init__()
        self._llm = llm

    def get_subgraph(self) -> Any:
        from src.graph.domain_workflow_graph import SurveyAnalysisWorkflowGraph

        sg = SurveyAnalysisWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        emit_trace_event(
            "survey_analysis_dispatched",
            {"correlation_id": state.get("correlation_id")},
            state,
        )
        return cast(str, state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        emit_trace_event(
            "survey_analysis_completed",
            {"correlation_id": state.get("correlation_id"), "n_themes": len(sub_result.get("theme_clusters", []))},
            state,
        )
        return {
            "sentiment_results": sub_result.get("sentiment_results", []),
            "theme_clusters": sub_result.get("theme_clusters", []),
            "period_deltas": sub_result.get("period_deltas", {}),
            "pii_stripped_count": sub_result.get("pii_stripped_count", state.get("pii_stripped_count", 0)),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {"llm": self._llm}


class Graph(AgentBaseGraph):
    """RET-C2-062 — Retail Customer Satisfaction Survey Analysis & Report Agent."""

    @property
    def name(self) -> str:
        return "ret-c2-062"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()
        llm = self.config.get("llm") if hasattr(self, "config") else None
        self._nodes["pre_process"] = SurveyIngestionParserNode()
        self._nodes["main"] = SurveyAnalysisGraphNode(llm=llm)
        self._nodes["post_process"] = ReportNarrateNode(llm=llm)

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.
