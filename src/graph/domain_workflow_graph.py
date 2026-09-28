"""AgentCore Platform v1.0 — RET-C2-062 inner survey analysis workflow (Cat 2).

Instantiated by SurveyAnalysisGraphNode.get_subgraph(). Receives only the JSON
string user_input (seeded from the outer validated_input); the first inner
node reconstructs the de-identified survey payload.

Pipeline: sentiment_classify -> theme_extract -> period_compare
"""

from typing import Any
from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus

from src.nodes.period_compare_node import PeriodCompareNode
from src.nodes.sentiment_classify_node import SentimentClassifyNode
from src.nodes.theme_extract_node import ThemeExtractNode
from src.schemas.state import State


class SurveyAnalysisWorkflowGraph(BaseGraph):
    """Inner multi-step survey sentiment/theme/period-compare workflow."""

    @property
    def name(self) -> str:
        return "ret_c2_062_survey_analysis_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        llm = self.config.get("llm") if hasattr(self, "config") else None
        self._nodes["sentiment_classify"] = SentimentClassifyNode(llm=llm)
        self._nodes["theme_extract"] = ThemeExtractNode(llm=llm)
        self._nodes["period_compare"] = PeriodCompareNode()

    def add_edges(self) -> None:
        self._sg.add_edge(START, "sentiment_classify")
        self._sg.add_edge("sentiment_classify", "theme_extract")
        self._sg.add_edge("theme_extract", "period_compare")
        self._sg.add_edge("period_compare", END)

    def route(self, state: AgentState) -> str:
        return END if state.get("status") == AgentStatus.ERROR.value else "period_compare"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "sentiment_results": state.get("sentiment_results", []),
            "theme_clusters": state.get("theme_clusters", []),
            "period_deltas": state.get("period_deltas", {}),
            "pii_stripped_count": state.get("pii_stripped_count", 0),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
