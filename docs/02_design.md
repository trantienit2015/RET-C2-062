# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `Graph` (`src/graph/graph.py`)
- **L1 Base**: AgentBaseGraph (outer) — Cat 2, `main` slot wraps an inner `BaseGraph` via `GraphNode`
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

### Outer graph (`src/graph/graph.py`)

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version, session_id, trust_level | — | — | InitializeNode (default) |
| pre_process | `SurveyIngestionParserNode` — parse mixed Likert+free-text batch, enforced S-2 PII strip | `user_input` | `survey_responses`, `comparison_period`, `pii_stripped_count`, `validated_input` | FunctionNode |
| main | `SurveyAnalysisGraphNode` — dispatches to inner subgraph | `validated_input` | `sentiment_results`, `theme_clusters`, `period_deltas` | GraphNode |
| post_process | `ReportNarrateNode` — narrate JA management report, enforced S-3 aggregate-only gate | `theme_clusters`, `period_deltas`, `sentiment_results` | `management_report`, `formatted_output` | FunctionNode |
| finalize | response_metadata, total_time_ms | — | — | FinalizeNode (default) |

### Inner subgraph (`src/graph/domain_workflow_graph.py`)

| Node | Responsibility |
|------|---------------|
| sentiment_classify | `SentimentClassifyNode` — Japan high-context implicit-dissatisfaction sentiment classification (the moat) |
| theme_extract | `ThemeExtractNode` — recurring theme extraction from de-identified free-text |
| period_compare | `PeriodCompareNode` — deterministic current-vs-prior metric aggregation |

### Data Flow

```
Outer:  START → initialize → pre_process → main(GraphNode) → post_process → finalize → END
Inner:  START → sentiment_classify → theme_extract → period_compare → END
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| survey_responses | `NotRequired[list[dict]]` | Parsed + de-identified survey responses | No |
| comparison_period | `NotRequired[dict]` | Caller-supplied comparison period config | No |
| pii_stripped_count | `NotRequired[int]` | Audit count of PII-stripped responses | No |
| sentiment_results | `NotRequired[list[dict]]` | Per-response sentiment classification | No |
| theme_clusters | `NotRequired[list[dict]]` | Extracted recurring themes | No |
| period_deltas | `NotRequired[dict]` | Current-vs-prior period metrics | No |
| management_report | `NotRequired[dict]` | Final structured JA report (aggregate-only) | No |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle)
- [ ] ConnectionPolicy (retry/timeout strategy)
- [ ] SecurityViolationError
- [x] S-2: `_extra_security_gate_input()` — not needed. The framework input gate masks PII
      in `user_input` first; `SurveyIngestionParserNode.execute()` then strips each comment
      again with the framework detectors (`detect_pii`, `detect_credentials`) plus a bounded
      residual pattern for Japanese phone numbers without separators, before the inner
      subgraph sees any free text.
- [x] S-3: `_extra_security_gate_output()` — `ReportNarrateNode` re-checks the final report
      for PII-shaped content (same detectors) and forbidden per-respondent identifier keys, and asserts the
      `aggregate_only` marker is present (APPI enforcement).
- [x] S-4: `emit_trace_event()` — every node emits >=1 domain event inside `execute()`
      (`survey_ingestion_started`, `survey_pii_stripped`, `sentiment_classified`,
      `themes_extracted`, `period_compared`, `survey_analysis_dispatched`/`_completed`,
      `report_narrated`).

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` / `RemoteAgentNode` → deliberate no-op (upstream or remote node's gate already applied)

### Composition Pattern

- **Pattern**: GraphNode (subgraph) — `SurveyAnalysisGraphNode` wraps `SurveyAnalysisWorkflowGraph`
- **Composition target**: inner `BaseGraph` (`src/graph/domain_workflow_graph.py`)
- **Error propagation strategy**: `propagate` (fail fast — no HITL in this template)

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph | Fixed 5-step pipeline, no autonomous loop needed |
| Composition pattern | Flat (Cat 1 style) | GraphNode + inner subgraph | GraphNode + inner subgraph | Cat 2 — `gate-composition` requires GraphNode wrapping, not a flat MainNode |
| S-2 PII handling | Rely on framework default scan only | Deterministic strip in pre_process + framework scan | Deterministic strip in pre_process | Free-text comments must be de-identified before ThemeExtract sees them, not just scanned |
| S-3 aggregate-only enforcement | Advisory prompt only | Enforced gate (`_extra_security_gate_output`) | Enforced gate | APPI requires a hard guarantee, not a best-effort prompt instruction |
