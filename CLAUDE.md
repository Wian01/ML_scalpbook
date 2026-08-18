# NQ Futures ML Research Platform — Claude Code Operating Guide

**Authoritative specification:** [docs/canonical-spec-v1.0.md](docs/canonical-spec-v1.0.md) (V1.0 FROZEN).
This file is a concise operating guide derived from it. If anything here appears to
conflict with the canonical spec, the canonical spec wins. Any material change to
labels, partitions, timestamp/as-of semantics, sampling, evaluation, or holdout policy
requires a documented protocol amendment in `docs/protocol-amendments/` and a version bump.

## Mission

Use ML as a hypothesis-generation and conditional-state discovery engine for NQ futures
(1-minute-and-above horizons), **not** as a machine for optimizing a backtest. A correct
answer — including "no robust edge found" — is success. This is not an HFT project.

## Document map

| Document | Contents |
|---|---|
| [docs/canonical-spec-v1.0.md](docs/canonical-spec-v1.0.md) | Full frozen V1.0 spec (verbatim; authoritative) |
| [docs/research-protocol.md](docs/research-protocol.md) | Horizons, partitions, sampling, labels, baselines, metrics, discovery vs confirmation, MBO ladder |
| [docs/data-specification.md](docs/data-specification.md) | Data assets, observed Milestone 0 facts, QA rules, timestamps, contracts, exclusions |
| [docs/experiment-protocol.md](docs/experiment-protocol.md) | Pre-registration, registry, multiple testing, falsification battery, "too good" alarm |
| [docs/holdout-policy.md](docs/holdout-policy.md) | Holdout definition, mechanical protection, opening procedure |
| [docs/architecture.md](docs/architecture.md) | Repository layout, stack, data flow, milestones, reproducibility |
| [docs/implementation-audit-log.md](docs/implementation-audit-log.md) | Append-only log of every material change, finding, and artifact regeneration (rule 21) |

## Non-negotiable rules (canonical §43)

1. Objective is a correct answer, not a profitable result.
2. Never use future information in a feature.
3. Never shuffle observations across train/test boundaries or across time for model
   evaluation. Permutation canaries/controls and model-internal bagging are allowed only
   when explicitly specified and cannot alter chronological evaluation.
4. Never access HOLDOUT without the explicit authorized workflow.
5. Raw data is immutable — never edit, rename, move, re-compress, "repair", or delete
   anything under `<data_root>/raw/` (canonical wording: `data/raw/`; the data root
   is configured, currently `D:/nq-research/data`). Read-only access only.
6. Never silently alter labels/evaluation to improve results.
7. Never weaken/change a test solely to make implementation pass; legitimate test changes
   must document the changed requirement.
8. Changes to sampling, labels, evaluation, partitions, or cost model require explicit review.
9. Every experiment is registered before execution; failed/null experiments are retained.
10. Do not add another model family merely because the current model failed (V1: LightGBM only).
11. "Too good" results trigger audit (`SUSPECT_AUDIT_REQUIRED`), not excitement.
12. All timestamps are UTC nanoseconds with explicit event/receive semantics; research
    chronology uses `ts_event`. Never silently convert to local wall time.
13. No rolling/forward-fill operation crosses a session boundary, contract boundary, or
    disallowed gap.
14. Every feature declares its as-of window and sources; no feature may use source data
    timestamped after its sample timestamp. Only F_LAST-complete book states are valid
    observations.
15. Bucket thresholds are computed on training folds only.
16. Do not optimize indefinitely on SELECTION; holdout output is never used for iterative rescue.
17. Every result links to dataset/config/code versions.
18. MBO inference reports block-level uncertainty (contiguous blocks, not days, are the unit).
19. AI-generated interpretations are hypotheses, not evidence.
20. Claude must challenge leakage and selection bias before suggesting optimization.
21. **Maintain the implementation audit log**
    ([docs/implementation-audit-log.md](docs/implementation-audit-log.md)). Every
    assistant working on this repository must append an entry for each material:
    implementation fix or improvement; audit/review finding; test addition,
    removal, or behavioral change; artifact regeneration; data-quality
    discovery; protocol-relevant decision. Entries are **append-only**: previous
    findings — including mistakes and superseded conclusions — are never edited
    or erased. Each entry records affected files, validation evidence, artifact
    hashes where applicable, unresolved risks, and the Git commit SHA once one
    exists.

## Key design invariants (quick reference)

- **Horizons:** primary 60 s and 5 min; secondary 15 min; diagnostic 30 s. Do not add more.
- **Partitions:** DEV → SELECTION → HOLDOUT → FORWARD, boundaries at whole CME trading
  days only. `MBO_LAB` is an orthogonal session flag.
- **Sessions:** CME trading day starts 17:00 America/Chicago; V1 RTH = 08:30–15:00 CT
  (config, not hardcoded). Registered V1 experiments are RTH-only; RTH lookbacks may use
  same-session ETH but never cross the 17:00 CT boundary.
- **Price:** market returns/labels use quote-derived mid = (bid+ask)/2, never last trade.
  Vendor prices stay int64 (1e-9 scale) internally.
- **Latency:** observation at T, availability at T+δ (primary δ=500 ms; sensitivities
  250/1000 ms). δ lives in the label/evaluation version, not sample identity.
- **Labels:** one main family — volatility-normalized future mid return, clipped ±3;
  regression task. Volatility: backward-only EWMA of squared 1 s mid returns, ~10 min
  half-life, floored, √t horizon scaling.
- **Sampling:** volume clock primary (pre-registered N; N/2 and 2N are robustness checks,
  never selection candidates); 30 s time clock control; event clock interface only.
- **Baselines:** B0 unconditional, B1 vol/activity/time, B2 price-only, B3 regularized
  linear, all also capacity-matched under LightGBM. The primary comparison is
  LightGBM(full) vs capacity-matched LightGBM(price-only).
- **Metric:** per-session skill vs the capacity-matched price-only LightGBM baseline;
  economic metric is cost-adjusted expectancy in pre-registered training-fold-derived
  tail buckets.
- **Inference units:** trading session (broad); contiguous MBO block (MBO lab).
- **No automated feature selection in V1.** Feature families are pre-registered.
- **Forbidden model inputs:** instrument_id, contract symbol, session_id, partition,
  mbo_lab flags, calendar date/month/year, raw absolute price level, dataset-availability
  missingness flags.
- **Deferred from V1:** sequence models, clustering/UMAP, extra GBDT families, MCP,
  backtester, live execution (canonical §73).

## Data handling

- The data tree lives OUTSIDE the repository on the dedicated data volume:
  `config/data/paths.yaml` `data_root` (overridable via `NQR_DATA_ROOT`),
  **currently `D:/nq-research/data`**. Raw vendor data (`<data_root>/raw/`) is
  immutable and read-only. The root-anchored `/data/` gitignore rule stays as a
  safety net against ever committing licensed data from a repo-local tree.
- Physical storage policy: everything large or regenerable (raw, normalized, QA
  artifacts + audit caches, samples, features, labels, datasets, holdout, model
  binaries, predictions, SHAP/interpretation caches, temp processing files) lives
  under `<data_root>` on D:; the Git repo on C: keeps only code, config, tests,
  docs, protocol amendments, and lightweight experiment definitions/registry
  records/metrics/audit metadata/compact reports (details: `docs/architecture.md`).
- Every derived artifact must be reproducible from raw + code version + config + lock file.
- No dataset may be used for research without a persistent QA artifact (PASS/WARN/FAIL);
  exclusions require machine-readable reason codes (allowed/forbidden list: canonical §50).
- Symbology note: all purchased data uses Databento parent symbology (`NQ.FUT`), so files
  contain outrights **and** spreads — see `docs/data-specification.md` for the observed
  facts and filtering rules.

## Workflow

- Environment: `uv` with pinned Python 3.12 (`uv sync`; run tools via `uv run ...`).
- Tests: `uv run pytest`. Production research logic lives in tested modules under
  `src/nqresearch/`; notebooks are exploratory only.
- CLI: `uv run nqr ...` (Milestone 0: `nqr data audit`).
- Builder/auditor separation for sensitive code (features, labels, sampling, evaluation,
  holdout, MBO reconstruction): implement in one session, audit adversarially in a fresh
  session using `prompts/audit_*.md`.

## Current status

- Milestone 0 (data audit) executed against: two-week MBP-1 sample (2026-08-03 → 2026-08-14),
  two years of trades (2024-08-09 → 2026-08-07), and 85 MBO files fully decoded
  (all vendor manifests validated by SHA-256). One MBO job also contains expected
  ES.FUT data, excluded from NQ research via instrument mappings. Authoritative NQ
  MBO session/block counts, results, and gate status: `docs/data-specification.md`
  and `<data_root>/qa/m0/`. Data lives on the dedicated D: volume
  (`data_root: D:/nq-research/data`).
- **The two-year MBP-1 purchase is complete (2026-08-18).** Two exactly adjacent
  annual jobs — `GLBX-20260817-P3KX4KXDQF` [2024-08-17, 2025-08-17) and
  `GLBX-20260817-S9GCQWS6L8` [2025-08-17, 2026-08-17) — are the **canonical
  research corpus** (`FULL_HISTORY_CANONICAL`). The two-week job is retained
  solely as the Milestone 0 QA source (`MILESTONE0_QA_SAMPLE`,
  research_eligible=false) and **must never be combined with the annual corpus
  for training** (its 11 dates are canonical in the recent annual job;
  identity established at the decoded-record level — cross-request file
  hashes differ by design via per-request container metadata, while each copy
  matches its own vendor manifest). Source selection is registry-driven:
  `config/data/mbp1_sources.yaml` + `nqresearch.sources` (never recursive
  globbing of raw/mbp1). Acquisition QA: `<data_root>/qa/mbp1_full_history/`.
  Parent-symbology reminder: the corpus contains outrights AND spreads;
  outright/spread classification remains mandatory downstream.
- **Milestone 0 closeout complete (commit `3c7aee5e`, AL-0028):** effective
  CME calendar integrated (baseline + official overrides); full-history
  coverage 507 PASS / 8 WARN / 0 FAIL of 516 expected sessions; causal
  front/roll rule defined; MBO computational closeout inventory of 77
  sessions / 30 blocks (activation state
  PROVISIONAL_DOCUMENT_VERIFICATION_PENDING);
  partition proposal structurally valid but **PROPOSED_NOT_ACTIVE,
  PROVISIONAL_DOCUMENT_VERIFICATION_PENDING, activation_ready=false** —
  activation requires document-level CME verification + explicit human
  approval. Current state: `docs/data-specification.md` §6a/§6b.
- No features, labels, sampling, models, experiments, activated holdout
  partition, protected holdout dataset, or holdout opening exists yet; only
  the unactivated tentative HOLDOUT proposal exists (data-spec §6a).
