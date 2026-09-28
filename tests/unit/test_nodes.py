# RET-C2-062 — Unit tests (per node: success + error/edge).

import json

from framework.schemas.agent_status import AgentStatus

from src.nodes.period_compare_node import PeriodCompareNode
from src.nodes.report_narrate_node import ReportNarrateNode
from src.nodes.sentiment_classify_node import SentimentClassifyNode
from src.nodes.survey_ingestion_parser_node import SurveyIngestionParserNode
from src.nodes.theme_extract_node import ThemeExtractNode


def _s(**kw):
    st = {"node_history": [], "error_log": [], "execution_time": {}, "correlation_id": "c"}
    st.update(kw)
    return st


_BATCH = json.dumps(
    {
        "responses": [
            {"likert": {"overall": 3}, "comment": "まあまあでした。改善の余地があると思います。"},
            {"likert": {"overall": 5}, "comment": "スタッフの接客が素晴らしく、また利用したい。"},
            {"likert": {"overall": 1}, "comment": "最悪でした。二度と行きたくない。"},
        ],
        "comparison_period": {"current": "2026Q2", "prior_metrics": {"negative_rate": 0.2, "implicit_dissatisfaction_rate": 0.1}},
    }
)


class TestSurveyIngestionParserNode:
    def setup_method(self):
        self.node = SurveyIngestionParserNode()

    def test_success(self):
        r = self.node.execute(_s(user_input=_BATCH))
        assert r["status"] == AgentStatus.SUCCESS
        assert len(r["survey_responses"]) == 3
        assert json.loads(r["validated_input"])["survey_responses"]

    def test_empty(self):
        assert self.node.execute(_s(user_input=""))["status"] == AgentStatus.ERROR

    def test_not_json(self):
        assert self.node.execute(_s(user_input="not json"))["status"] == AgentStatus.ERROR

    def test_no_responses(self):
        p = json.dumps({"responses": []})
        assert self.node.execute(_s(user_input=p))["status"] == AgentStatus.ERROR

    def test_pii_stripped(self):
        p = json.dumps({"responses": [{"likert": {"overall": 2}, "comment": "連絡先 test@example.com です。不満です。"}]})
        r = self.node.execute(_s(user_input=p))
        assert r["status"] == AgentStatus.SUCCESS
        assert r["pii_stripped_count"] == 1
        assert "test@example.com" not in r["survey_responses"][0]["comment"]


class TestSentimentClassifyNode:
    def setup_method(self):
        self.node = SentimentClassifyNode()

    def test_success_detects_implicit_negative(self):
        inner = json.dumps({"survey_responses": [{"likert": {}, "comment": "まあまあでした。改善の余地があります。"}]})
        r = self.node.execute(_s(user_input=inner))
        assert r["status"] == AgentStatus.SUCCESS
        assert r["sentiment_results"][0]["sentiment"] == "negative"
        assert r["sentiment_results"][0]["implicit_dissatisfaction"] is True

    def test_positive(self):
        inner = json.dumps({"survey_responses": [{"likert": {}, "comment": "また利用したいです。"}]})
        r = self.node.execute(_s(user_input=inner))
        assert r["sentiment_results"][0]["sentiment"] == "positive"

    def test_missing_responses(self):
        assert self.node.execute(_s(user_input=json.dumps({})))["status"] == AgentStatus.ERROR


class TestThemeExtractNode:
    def setup_method(self):
        self.node = ThemeExtractNode()

    def test_success(self):
        responses = [{"comment": "スタッフの接客が良かった"}, {"comment": "レジの待ち時間が長い"}]
        r = self.node.execute(_s(survey_responses=responses))
        assert r["status"] == AgentStatus.SUCCESS
        themes = {c["theme"] for c in r["theme_clusters"]}
        assert "store_staff" in themes
        assert "checkout_wait" in themes

    def test_missing_responses(self):
        assert self.node.execute(_s())["status"] == AgentStatus.ERROR


class TestPeriodCompareNode:
    def setup_method(self):
        self.node = PeriodCompareNode()

    def test_success_with_prior(self):
        sentiment_results = [{"sentiment": "negative", "implicit_dissatisfaction": True}, {"sentiment": "positive", "implicit_dissatisfaction": False}]
        comparison_period = {"prior_metrics": {"negative_rate": 0.6, "implicit_dissatisfaction_rate": 0.5}}
        r = self.node.execute(_s(sentiment_results=sentiment_results, comparison_period=comparison_period))
        assert r["status"] == AgentStatus.SUCCESS
        assert r["period_deltas"]["deltas"] is not None

    def test_missing_sentiment_results(self):
        assert self.node.execute(_s())["status"] == AgentStatus.ERROR


class TestReportNarrateNode:
    def setup_method(self):
        self.node = ReportNarrateNode()

    def test_success(self):
        r = self.node.execute(
            _s(
                theme_clusters=[{"theme": "store_staff", "mention_count": 2}],
                period_deltas={"current": {"negative_rate": 0.1, "implicit_dissatisfaction_rate": 0.05}, "prior": None, "deltas": None},
                sentiment_results=[{"sentiment": "positive"}],
                pii_stripped_count=0,
            )
        )
        assert r["status"] == AgentStatus.SUCCESS
        assert r["management_report"]["aggregate_only"] is True

    def test_upstream_error(self):
        assert self.node.execute(_s(status="error"))["status"] == AgentStatus.ERROR

    def test_s3_gate_blocks_pii_leak(self):
        bad = _s(management_report={"summary": "contact test@example.com", "aggregate_only": True})
        assert self.node._extra_security_gate_output(bad)["status"] == AgentStatus.ERROR

    def test_s3_gate_blocks_identifier_key(self):
        bad = _s(management_report={"summary": "ok", "aggregate_only": True, "respondent_id": "r1"})
        assert self.node._extra_security_gate_output(bad)["status"] == AgentStatus.ERROR

    def test_s3_gate_blocks_missing_aggregate_marker(self):
        bad = _s(management_report={"summary": "ok"})
        assert self.node._extra_security_gate_output(bad)["status"] == AgentStatus.ERROR

    def test_s3_gate_passes_valid(self):
        good = _s(management_report={"summary": "ok", "aggregate_only": True})
        assert self.node._extra_security_gate_output(good) is good
