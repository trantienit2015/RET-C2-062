# RET-C2-062 — Retail Customer Satisfaction Survey Analysis & Report Agent

> **Category**: Cat 2 (orchestrates multiple steps to accomplish a specific use case)
> **Industry**: RET

## Overview

A retail CX or store-operations team submits a batch of customer-satisfaction survey
responses (Likert scores plus Japanese free-text comments). The agent removes personal data,
classifies the sentiment of each comment, including indirect dissatisfaction typical of
Japanese feedback (for example 少し残念, まあまあ), groups the comments into themes, compares
the period with an optional prior-period baseline, and returns an aggregate-only management
report in Japanese.

Input is a JSON string:

```json
{"responses": [{"likert": {"overall_satisfaction": 4}, "comment": "スタッフの接客がとても良かったです"},
               {"likert": {"overall_satisfaction": 2}, "comment": "レジの待ち時間が長くて少し残念でした"}],
 "comparison_period": {"prior_metrics": {"negative_rate": 0.3, "implicit_dissatisfaction_rate": 0.1}}}
```

`responses` is required; `comparison_period` is optional. The output is a report with
`summary`, `period_metrics` (current, prior and deltas of the negative and
implicit-dissatisfaction rates), `themes`, `n_responses`, `pii_stripped_count` and
`aggregate_only: true`.

How it works today:

- **Ingestion** (outer `pre_process`): parses the batch, drops malformed entries, and redacts
  personal data in each comment (email, phone numbers, My Number, card numbers, tokens) with
  the framework PII and credential detectors plus a pattern for phone numbers without
  separators.
- **Inner workflow** (a `GraphNode` in the `main` slot):
  1. classifies each comment as positive, negative or neutral with fixed Japanese marker lists,
     and flags indirect dissatisfaction;
  2. counts theme mentions with fixed keyword buckets (staff, product quality, checkout wait,
     cleanliness, pricing);
  3. computes the current-period rates and, when a prior baseline is supplied, the deltas.
- **Report** (outer `post_process`) writes the summary and applies an output gate that fails the
  run if the report contains personal data, a per-respondent identifier key, or lacks the
  `aggregate_only` marker.

The Likert scores are parsed and carried along but are not used in the metrics today; every
rate is derived from the comment text.

No model is required. The standalone HTTP entry point builds an Anthropic client when the
`LLM_API_KEY` secret is available; the model then relabels the theme keys, expands the report
summary and raises the per-comment confidence value, while the sentiment label, counts and
rates stay deterministic. Any model error falls back to the deterministic output. Without the
key everything runs on the deterministic paths described above.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | 3.11 or later |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and test specification
```

See `docs/02_design.md` for the design and `docs/03_test_spec.md` for the test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
