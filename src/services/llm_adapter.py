"""AgentCore Platform v1.0 — RET-C2-062 LLM adapter (production wiring).

The standalone entry point (`src/api/server.py`) calls `build_llm()` once at start-up and
passes the result to `Graph(config={"llm": ...})`, so `SentimentClassifyNode` /
`ThemeExtractNode` / `ReportNarrateNode` use the model when `LLM_API_KEY` is available.
The key is optional for the agent as a whole: the entry point catches `LLMConfigError`
and runs the deterministic paths, and a registry-loaded graph receives no client at all,
so `LLM_API_KEY` is not listed in `requires.secrets`.

`build_llm(secrets, *, allow_stub=False)` returns a client exposing
`complete(messages: list[dict]) -> dict` (the canonical `BaseLLM.complete()` shape
the nodes call). Production (`allow_stub=False`, default): the secret is
MANDATORY — a missing or empty key raises `LLMConfigError` at construction
(fail-fast, never a silent demo client). Demo/test (`allow_stub=True`, opt-in
only): returns `None`, so callers use their own deterministic fallback (the
template's intentional deterministic-core mode for unit tests).

Never reads the process environment for the key and never stores it in State —
read once at entry-point construction via the injected `SecretProvider`.
"""

from __future__ import annotations

from typing import Any, Optional

_KEY_SECRET = "LLM_API_KEY"


class LLMConfigError(RuntimeError):
    """Raised when a live LLM client is required but its configuration is missing."""


def extract_text(raw: Any) -> str:
    """Normalize an LLM `.complete()` response to plain text.

    Canonical `BaseLLM.complete(messages: list) -> dict`
    (`shared/services/llm/base_llm.py`: `{"content": str, "tool_calls": list,
    "model": str, "usage": {...}}`) — a live client returns a dict, not a bare
    string. Treating the raw response as a string directly (`.strip()`,
    `.splitlines()`, `str(raw)`) either crashes on a real client or silently
    embeds the dict repr in the output. Accepts a bare string too (test fakes).
    """
    if isinstance(raw, dict):
        content = raw.get("content", "")
        return content if isinstance(content, str) else ""
    if isinstance(raw, str):
        return raw
    return ""


def build_llm(secrets: Any, *, allow_stub: bool = False) -> Optional[Any]:
    """Build the production LLM client from the injected secret provider.

    `secrets` is a `SecretProvider` (from `secrets_factory(...)` / `ctx.secrets`)
    exposing `require(key) -> str`. Returns a live client (`.complete(messages) ->
    dict`) in production, or `None` when `allow_stub=True` (opt-in demo/test) so
    the caller falls back to its own deterministic sentiment/theme/report logic.
    """
    if allow_stub:
        return None

    try:
        api_key = secrets.require(_KEY_SECRET)
    except Exception as exc:  # SecretProvider raises MissingSecret/KeyError variants
        raise LLMConfigError(
            f"live LLM sentiment/theme/report narration requires the {_KEY_SECRET} "
            f"secret; set it, or opt into "
            f"the deterministic fallback explicitly"
        ) from exc
    if not api_key:
        raise LLMConfigError(f"{_KEY_SECRET} is empty; a live LLM key is required in production")

    # Imported lazily so the optional provider SDK dependency is only required
    # in deployments that actually construct a real client.
    from shared.services.llm.anthropic_client import AnthropicClient

    return AnthropicClient({"model": "claude-sonnet-5", "api_key": api_key})
