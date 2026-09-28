# RET-C2-062 — Integration test: full graph compile + invoke.

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import Graph


class FakeLLM:
    def complete(self, *a, **k):
        return "narration note"


def _ctx(session="it-1"):
    return InvocationContext(session_id=session, caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="tester")


def _agent():
    a = Graph(config={"llm": FakeLLM(), "max_retry": 1})
    a.compile()
    return a


_BATCH = json.dumps(
    {
        "responses": [
            {"likert": {"overall": 2}, "comment": "まあまあでした。改善の余地があると思います。"},
            {"likert": {"overall": 5}, "comment": "スタッフの接客が素晴らしく、また利用したい。"},
            {"likert": {"overall": 1}, "comment": "最悪でした。二度と行きたくない。"},
        ],
        "comparison_period": {"current": "2026Q2", "prior_metrics": {"negative_rate": 0.3, "implicit_dissatisfaction_rate": 0.1}},
    }
)


def test_full_pipeline_success():
    result = _agent().invoke(_BATCH, ctx=_ctx())
    assert result["status"] in (AgentStatus.SUCCESS, AgentStatus.SUCCESS.value)
    nh = result.get("node_history") or []
    assert len(nh) >= 5, f"expected >=5 nodes, got {len(nh)}: {nh}"
    report = result.get("output") or {}
    assert isinstance(report, dict)
    assert report.get("aggregate_only") is True
    assert report.get("n_responses") == 3


def test_empty_input_errors():
    result = _agent().invoke("", ctx=_ctx("it-2"))
    assert result["status"] in (
        AgentStatus.ERROR, AgentStatus.ERROR.value, AgentStatus.CANCELLED, AgentStatus.CANCELLED.value,
    )


def test_no_pii_or_secret_in_output():
    result = _agent().invoke(_BATCH, ctx=_ctx("it-3"))
    blob = json.dumps(result, default=str).lower()
    assert "sk-" not in blob and "eyj" not in blob
    assert "@example.com" not in blob
