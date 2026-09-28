# RET-C2-062 - Framework compliance tests TC-01..TC-08,
# adapted to this template's real architecture (Cat 2: outer pre/post + GraphNode-wrapped inner nodes).

import json
import os
import re

from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.nodes import report_narrate_node, survey_ingestion_parser_node
from src.schemas.state import State

_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
TRUST = TrustLevel.VERIFIED_EXTERNAL.value

_BATCH = json.dumps(
    {
        "responses": [{"likert": {"overall": 5}, "comment": "スタッフの接客が素晴らしかった。また利用したい。"}],
        "comparison_period": {"current": "2026Q2"},
    }
)


def _src_files():
    for root, _d, files in os.walk(_SRC):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


# TC-01 - State is a flat TypedDict extending AgentState; agent-specific fields
# are JSON-serializable (list/dict/scalar, all NotRequired-wrapped in source).
class TestTC01StateContract:
    def test_state_is_typeddict_extending_agent_state(self):
        assert hasattr(State, "__annotations__")
        assert "user_input" in State.__annotations__
        assert set(AgentState.__annotations__).issubset(set(State.__annotations__))

    def test_added_fields_are_json_serializable_typed(self):
        added = [k for k in State.__annotations__ if k not in AgentState.__annotations__]
        assert added, "State must declare agent-specific fields"
        # Every added field is NotRequired-wrapped in src/schemas/state.py.
        with open(os.path.join(_SRC, "schemas", "state.py"), encoding="utf-8") as f:
            content = f.read()
        for name in added:
            assert re.search(rf"{name}\s*:\s*NotRequired\[", content), f"{name} must be NotRequired[...]"


# TC-02 - Empty/missing input yields a fail-closed ERROR outcome, no raise.
class TestTC02Validation:
    def test_empty_input_no_raise(self):
        node = survey_ingestion_parser_node.SurveyIngestionParserNode()
        out = node.execute({"user_input": ""})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_malformed_json_no_raise(self):
        node = survey_ingestion_parser_node.SurveyIngestionParserNode()
        out = node.execute({"user_input": "not json"})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]


# TC-03 - No JWT / API keys / secrets in src/; no direct os.environ reads.
class TestTC03NoCredentials:
    def test_no_credential_literals(self):
        pat = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                content = f.read()
            # exclude the deterministic S-2/S-3 JWT-pattern regex definitions themselves.
            if "_JWT_RE" in content:
                content = re.sub(r'_JWT_RE = re\.compile\([^\n]+\)', "", content)
            if pat.search(content):
                offenders.append(fp)
        assert offenders == []

    def test_no_os_environ_secret_reads(self):
        # src/api/server.py is the sole permitted os.environ call site (entry-point
        # exception): it reads the caller-auth tokens and RET_C2_062_ALLOW_STUB_LLM, a
        # boolean demo/test opt-in flag, not a credential. The LLM_API_KEY secret itself
        # is read only through the secret provider in llm_adapter.py.
        exempt = os.path.join("api", "server.py")
        pat = re.compile(r"os\.environ\s*(\[|\.\w+\()")
        offenders = []
        for fp in _src_files():
            if fp.replace(os.sep, "/").endswith(exempt.replace(os.sep, "/")):
                continue
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []


# TC-04 - InvocationContext is never stored in State after invoke.
class TestTC04ContextIsolation:
    def test_no_invocationcontext_in_state_after_invoke(self):
        from src.graph.graph import Graph

        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="tc04", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="analyst-tc04")
        result = agent.invoke(_BATCH, ctx=ctx)
        for v in result.values():
            assert not isinstance(v, InvocationContext)

    def test_from_state_available(self):
        assert hasattr(InvocationContext, "from_state")


# TC-05 - Domain events: ReportNarrateNode emits >=1 domain event; no node
# under src/nodes/ ever re-emits a framework backbone lifecycle event.
class TestTC05Audit:
    def test_audit_node_emits_domain_event(self, monkeypatch):
        events = []
        monkeypatch.setattr(report_narrate_node, "emit_trace_event", lambda e, p, s: events.append(e))
        state = {
            "theme_clusters": [{"theme": "store_staff", "mention_count": 1}],
            "period_deltas": {"current": {"negative_rate": 0.0, "implicit_dissatisfaction_rate": 0.0}, "prior": None, "deltas": None},
            "sentiment_results": [{"sentiment": "positive"}],
            "pii_stripped_count": 0,
        }
        out = report_narrate_node.ReportNarrateNode().execute(state)
        assert out["status"] == AgentStatus.SUCCESS
        assert len(events) >= 1
        assert "report_narrated" in events
        assert not ({"node_start", "node_complete", "node_error", "node_skip"} & set(events))

    def test_source_has_no_backbone_events(self):
        pat = re.compile(r'emit_trace_event\(\s*["\'](node_start|node_complete|node_error|node_skip)["\']')
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []


# TC-06 / TC-07 - moved to tests/unit/test_framework_compliance_tc06_tc07.py
# (exact-name scaffold invariant file; see that file for the S-2/S-3 @final tests).


# TC-08 - required_trust_level enforced: insufficient trust -> ERROR state, no raise.
class TestTC08TrustGate:
    def test_declared_trust_levels_valid(self):
        for cls in (
            survey_ingestion_parser_node.SurveyIngestionParserNode,
            report_narrate_node.ReportNarrateNode,
        ):
            assert cls.required_trust_level in (TrustLevel.ANONYMOUS, TrustLevel.VERIFIED_EXTERNAL, TrustLevel.INTERNAL)

    def test_insufficient_trust_returns_error(self):
        node = survey_ingestion_parser_node.SurveyIngestionParserNode()
        out = node({"caller_trust_level": TrustLevel.ANONYMOUS.value, "user_input": _BATCH})
        assert str(out.get("status")).lower().endswith("error")

    def test_sufficient_trust_succeeds(self):
        node = survey_ingestion_parser_node.SurveyIngestionParserNode()
        out = node({"caller_trust_level": TRUST, "user_input": _BATCH})
        assert out["status"] == AgentStatus.SUCCESS
