# Research Protocol (V1)

Derived from [canonical-spec-v1.0.md](canonical-spec-v1.0.md) (authoritative; §-references
below point into it). Any material change here requires a protocol amendment in
`docs/protocol-amendments/` and a version bump.

## 1. Mission and philosophy (§1)

Discover, test, falsify, and explain statistically persistent behaviours in NQ futures.
ML is a hypothesis-generation and conditional-state discovery engine, not a backtest
optimizer. The platform must not encode conventional strategies and tune them, predict
next ticks, maximize development backtest profit, treat the AI assistant as the model,
or search until something looks profitable. "No robust edge found" is a valid success (§76).

## 2. Horizons (§3, §4)

- Primary prediction horizons: **60 s** and **5 min**. Secondary: **15 min**. Diagnostic: **30 s**.
- Do not add further horizons in V1 (multiple-testing burden).
- Feature windows (100 ms … 60 s backward-looking) are independent of prediction
  horizons; sub-second inputs never imply a sub-second strategy. The separation must
  stay explicit.

## 3. Data roles and partitions (§5, §6)

Roles: **BROAD** (two-year MBP-1 + validated trades; all main research),
**MBO_LAB** (scattered full-MBO sessions; incremental-depth question only),
**HOLDOUT** (final untouched chronological period; see [holdout-policy.md](holdout-policy.md)),
**FORWARD** (all data collected after project start; cleanest confirmation).
Never combine heterogeneous availability so that missingness becomes predictive.

Chronology: `DEV → SELECTION → HOLDOUT → FORWARD`; MBO_LAB is an orthogonal session flag.
Partition boundaries fall only on whole CME trading days.

- DEV: exploration, SHAP, rule mining, engineering. Never final evidence.
- SELECTION: pre-registered tests, walk-forward comparison, confirmation of DEV
  hypotheses. Once a selection result influences a decision it is no longer untouched
  OOS. It is called SELECTION, never "final OOS".
- HOLDOUT: forbidden during development for any purpose (§6.3).

## 4. Sampling (§14, §15)

The sample table is a versioned first-class artifact; all features/labels join on
`sample_id` — no module chooses its own timestamps. Canonical fields per §14.

- **Primary: volume clock.** `N = median DEV-period RTH contract volume / 400`, rounded
  sensibly, pre-registered, chosen mechanically — never by predictive optimization.
  Accumulate eligible traded contracts in event order; on cumulative volume ≥ N emit one
  sample at the F_LAST-complete trigger state, subtract N (carry excess), deduplicate
  same-nanosecond emissions deterministically. Accumulators reset at contract switches
  and trading-session boundaries. `N/2` and `2N` are robustness checks only.
- **Control: time clock** at a fixed 30 s, not tuned.
- **Event clock:** interface/schema defined in V1, not a research axis.

## 5. Point-in-time correctness (§16)

Every feature family declares sources, min/max lookback, as-of policy, event/receive
time, book-state requirement, and session/contract crossing (both default NO).
Automated invariant: `max(source_timestamp_used) <= sample.timestamp`. Only
F_LAST-complete book states are valid observations. No forward-fill or rolling window
crosses a session boundary, contract boundary, or disallowed gap.

## 6. Price, latency, labels, volatility (§17–§21)

- Market state/returns/labels use `mid = (bid + ask)/2` (quote-derived); last-trade
  price never substitutes for market state (bid/ask bounce). Trade prices may describe
  execution flow. Prices stay int64 (vendor 1e-9 scale) or exact ticks internally.
- Observation at T; availability at `T + δ`; V1 primary δ = 500 ms (sensitivities
  250/1000 ms). Entry state = first F_LAST-complete state at/after `T+δ`; horizon end =
  last F_LAST-complete state with `ts_event <= T+δ+H`. δ belongs to the label/evaluation
  version, not sample identity.
- One main target family: `y_H = clip(r_H(T)/sigma_H(T), -3, +3)` with
  `r_H(T) = mid(T+δ+H) − mid(T+δ)`; regression task. Barriers/MFE/MAE are diagnostic
  labels only (§21), never silently promoted to targets.
- Volatility: strictly backward EWMA of squared 1 s mid returns, ~10 min half-life
  (fixed design choice), floored, √t scaling to H. RTH-open warm start: initial
  candidate is the median realized 08:30–08:40 variance over the prior 20 eligible
  sessions — a normalization/QA parameter validated on DEV for target-scale stability,
  never chosen by predictive performance (§20).

## 7. Session scope (§10)

Registered V1 experiments are RTH-only (08:30–15:00 America/Chicago, from config).
ETH is ingested/QA'd/flagged but unused in registered V1 selection. RTH lookbacks may
use same-session ETH observations where the feature definition permits; no lookback
crosses the 17:00 CT session boundary. Include `seconds_since_rth_open` as context.

## 8. Features (§23, §24, §41)

Prefer primitive, interpretable, point-in-time-explainable information; start with
~15–25 families (trade activity; signed flow; mid-price state; **price response to
flow** (priority); L1 book state; context — see §24). No hard-coded threshold
strategies; "absorption" is represented by primitives, not encoded as a label.
Era/dataset-identity inputs are forbidden (§41): instrument_id, symbol, session_id,
partition, mbo_lab flags, calendar date/month/year, raw absolute price level,
availability/missingness flags. Scalers/statistics fit on past/training data only.
**No automated feature selection in V1** — families are pre-registered per experiment (§29).

## 9. Baselines and metrics (§25–§27, §53)

Baseline ladder: B0 unconditional; B1 volatility/activity/time-only; B2 price-only;
B3 regularized linear; M1 LightGBM (only GBDT family in V1). **Capacity-matched rule:**
every substantive feature-set comparison also runs under LightGBM with the same fixed
hyperparameter policy; the primary incremental claim is
`LightGBM(price-only) vs LightGBM(price + signed-flow/L1)`.

- Primary predictive metric: per-session skill vs the capacity-matched LightGBM
  price-only baseline, e.g. `1 − MSE_model/MSE_price_baseline`; report mean, median,
  session-bootstrap CI, monthly distribution, fraction positive.
- Primary economic metric: cost-adjusted expectancy in pre-registered extreme score
  buckets (top/bottom 5%, optionally 10%); bucket thresholds always from TRAINING-fold
  score distributions. Report the full per-bucket panel of §27 and slippage scenarios
  (base/+1/+2 ticks); never change the cost model after viewing results without
  versioning a new experiment (§22).

First registered question (§53): does price response to signed aggressive order flow
add predictive information for 60 s / 5 min normalized mid returns beyond volatility,
activity, and price-history baselines?

## 10. Statistical inference (§28, §29)

Primary inference unit: trading session (broad); contiguous MBO block (lab). Never
treat intraday rows as independent evidence. Chronological walk-forward only —
session-grouped folds, purging, embargo ≥ forward horizon, preprocessing and bucket
thresholds fit on training folds only. Never random-shuffle market observations.
Robustness configurations (δ, N, cost sensitivities) are registered children of the
parent experiment — never a pool to select the best from.

## 11. Discovery vs confirmation (§33, §54)

Discovery (DEV only): SHAP, shallow-tree leaf mining, exploratory plots — generates
hypotheses, proves nothing. Every interesting rule becomes a numbered frozen hypothesis
(HYP-nnnn: exact conditions, target, horizon, population, direction, metric, kill
criterion) tested in SELECTION unmodified. Record the mined batch size K; apply BH-FDR
(or pre-specified correction) to mined batches. Interpret models (SHAP interactions,
surrogate trees, ablation) rather than tuning aggregate score.

## 12. MBO incremental ladder (§30–§32)

Question: does deeper data add value beyond the broad MBP-1 model? Never compare
independently optimized small-sample models. BROAD_LADDER: frozen broad model trained
on allowed DEV+SELECTION history **excluding all MBO_LAB sessions**. Tiers:
T0 = broad score + MBP-1 features; T1 = + aggregated MBP-10-like depth;
T2 = + full MBO order-level features. Identical sample table, labels, folds, fixed
hyperparameters. ~10 seeded permutation draws as capacity control; a purchased vendor
MBP-10 validation sample is **required** before trusting T1 depth results. Metrics:
paired block/session skill difference vs T0; paired tail-expectancy difference; report
block-bootstrap CI, positive-block/day proportions, stability splits, concentration.
Selection bias of lab sessions is documented, not reweighted (§30). A null result reads
"improvement below the confidence-bound magnitude in this sample", never "MBO has no value".
Queue-position/identity research deferred to V2 (§32.6).

## 13. Falsification and alarms (§35, §36, §52)

Every graduating candidate runs the full commandable battery of §35 (shift/permutation
tests, leakage audit, latency and N sensitivities, jackknife, best-session drops,
month drops, volatility terciles, event-day and roll-week exclusions, +1/+2 tick costs,
ablations, baseline comparisons). Unexpectedly strong results (§36 thresholds) set
`SUSPECT_AUDIT_REQUIRED` and trigger the audit sequence before interpretation.
Leakage canary tests (§52: permuted target, shifted target, future-feature canary,
noise features) must pass; any failure blocks research until fixed.

## 14. Candidate edge definition and strategy staging (§55, §75)

A candidate progresses only on the ten criteria of §75 (incremental information,
chronological stability, dispersion, robustness, no leakage, no single-session
domination, economic relevance after costs, reproducible state definition, falsification
survival, forward confirmation). Strategy construction follows the §55 pipeline; no
general backtester before stable predictive behaviour exists.

## 15. Explicitly deferred from V1 (§34, §56, §73)

Clustering/UMAP/HDBSCAN; sequence models; additional GBDT families; RL; regime engines;
many targets; 1-second strategies; general backtester; MLflow; MCP; distributed/cloud;
live execution. Complexity must earn itself against simpler baselines.
