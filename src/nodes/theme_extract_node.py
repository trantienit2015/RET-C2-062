"""AgentCore Platform v1.0 — inner step 2: ThemeExtract."""

import json
from collections import Counter
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.llm_adapter import extract_text

# Deterministic domain-keyword buckets — theme clustering fallback when no LLM configured.
_THEME_KEYWORDS = {
    "store_staff": ("スタッフ", "接客", "店員"),
    "product_quality": ("品質", "商品", "鮮度"),
    "checkout_wait": ("レジ", "待ち時間", "行列"),
    "store_cleanliness": ("清潔", "清掃", "汚れ"),
    "pricing": ("価格", "値段", "コスパ"),
}


class ThemeExtractNode(FunctionNode):
    """Extract recurring themes from de-identified free-text responses.

    Runs after SentimentClassifyNode in the inner subgraph. LLM refines theme
    labeling when configured; the deterministic keyword-bucket clustering is
    the guaranteed fallback.
    """

    # S-1: inner subgraph node — ANONYMOUS (trust authenticated at outer backbone).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        responses = state.get("survey_responses")
        if not isinstance(responses, list) or not responses:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ThemeExtractNode: missing survey_responses"],
            }

        counts: Counter[str] = Counter()
        for resp in responses:
            comment = str(resp.get("comment", ""))
            for theme, keywords in _THEME_KEYWORDS.items():
                if any(kw in comment for kw in keywords):
                    counts[theme] += 1

        clusters = [{"theme": theme, "mention_count": n} for theme, n in counts.most_common()]
        clusters = self._llm_refine(clusters)

        emit_trace_event(
            "themes_extracted",
            {"correlation_id": state.get("correlation_id"), "n_themes": len(clusters)},
            state,
        )
        return {"theme_clusters": clusters, "status": AgentStatus.SUCCESS.value}

    def _llm_refine(self, clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """LLM relabels each cluster's `theme` key in place; mention_count/order
        (the deterministic ranking, this agent's guaranteed fallback) never
        changes — only whether a human-readable label replaces the keyword-
        bucket key. Any shape mismatch discards the LLM output and keeps the
        deterministic clusters."""
        if self._llm is None or not clusters:
            return clusters
        try:
            prompt = (
                "Return a JSON array of human-readable Japanese retail-survey theme "
                "labels, one per input cluster, same order, same length. Input "
                f"clusters (keyword-bucket key + mention_count): {json.dumps(clusters, ensure_ascii=False)}"
            )
            raw = self._llm.complete([{"role": "user", "content": prompt}])
            labels = json.loads(extract_text(raw))
        except Exception as exc:  # noqa: BLE001 — degrade to deterministic clustering
            import logging

            logging.getLogger(__name__).warning("theme LLM refinement failed: %s", exc)
            return clusters

        if not isinstance(labels, list) or len(labels) != len(clusters):
            return clusters
        return [
            {**cluster, "theme": label if isinstance(label, str) and label.strip() else cluster["theme"]}
            for cluster, label in zip(clusters, labels)
        ]
