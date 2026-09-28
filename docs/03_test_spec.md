# Test Specification

## Test Strategy
- Coverage target: every node ≥1 unit success + ≥1 error/edge; full graph ≥1 integration compile+invoke
- Test types: Unit (`tests/unit/`), Integration (`tests/integration/`), Proof-of-Boundary (`tests/proof_of_boundary/`)

## Framework Compliance Tests (Mandatory) — `tests/unit/test_framework_compliance.py`

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict extends AgentState, added fields NotRequired | Type check pass, no Pydantic/dataclass | PASS |
| TC-02 | Empty/malformed input to `SurveyIngestionParserNode` | Fail-closed ERROR, no raise | PASS |
| TC-03 | No JWT/Credential literals or `os.environ` in `src/` | 0 violations | PASS |
| TC-04 | InvocationContext never stored in State after invoke | 0 leaks | PASS |
| TC-05 | S-4: `ReportNarrateNode` emits domain event; no node re-emits backbone lifecycle events | `report_narrated` present; 0 `node_start/complete/error` re-emits | PASS |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` at class definition if overridden | PASS |
| TC-07 | S-3: `_security_gate_output()` not overridden; `_extra_security_gate_output` overridable and blocks credentials | `TypeError` if `@final` overridden; credential leak blocked | PASS |
| TC-08 | `required_trust_level` declared valid + enforced (insufficient trust → ERROR) | Insufficient trust refused; sufficient trust succeeds | PASS |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-2 | State serialization | `test_state_safety.py` — no credential-shaped field names, no Pydantic/InvocationContext annotations | 0 violations | PASS |
| PB-4 | Import isolation | `test_import_isolation.py` — no `agenticstar` import in `src/` | 0 violations | PASS |
| PB-6 | Invoke execution order | `test_pb_invoke_order.py` — every `src/nodes/` `BaseNode` subclass: S-1 → node_start → S-2 → execute() → S-3 → node_complete | Order verified for all 5 nodes | PASS |
| PB-7 | HITL interrupt propagation | `test_pb7_hitl_interrupt_propagation.py` — `hitl.enabled` is false (no `interrupt()` in this template) → auto-skip | Skipped (N/A) | SKIP (expected) |

## Business Logic Tests — `tests/unit/test_nodes.py`

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | `SurveyIngestionParserNode` parses mixed Likert+free-text batch | 3-response JSON batch | `status=SUCCESS`, 3 `survey_responses` | PASS |
| BL-02 | `SurveyIngestionParserNode` strips PII (email) from comment | Comment containing an email address | `pii_stripped_count == 1`, email redacted | PASS |
| BL-03 | `SentimentClassifyNode` detects implicit dissatisfaction (間接的不満) | Hedged negative comment | `sentiment=negative`, `implicit_dissatisfaction=True` | PASS |
| BL-04 | `ThemeExtractNode` extracts recurring themes | Comments mentioning staff + checkout wait | `store_staff` and `checkout_wait` themes present | PASS |
| BL-05 | `PeriodCompareNode` computes current-vs-prior deltas | Sentiment results + prior_metrics config | `period_deltas.deltas` populated | PASS |
| BL-06 | `ReportNarrateNode` S-3 gate blocks PII leak in report | Report summary containing an email address | `_extra_security_gate_output` → ERROR | PASS |
| BL-07 | `ReportNarrateNode` S-3 gate blocks forbidden identifier key | Report containing `respondent_id` | `_extra_security_gate_output` → ERROR | PASS |
| BL-08 | Full pipeline integration | 3-response survey batch via `Graph().invoke()` | `status=SUCCESS`, `output.aggregate_only=True` | PASS |

## Test Execution Summary
- Execution date: 2026-07-10
- Total tests: unit (TestNodes ~20) + framework compliance (TC-01..08, ~13) + integration (3) + proof_of_boundary (4, incl. 1 skip)
- Pass: all except intentional PB-7 skip (HITL not enabled)
- Coverage: every node has ≥1 success + ≥1 error/edge unit test; full outer+inner pipeline covered by integration test
