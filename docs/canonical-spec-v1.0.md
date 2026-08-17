# NQ Futures Machine Learning Research Platform — V1 CANONICAL SPEC

**Status:** V1.0 FROZEN — implementation baseline  
**Purpose:** Canonical research and engineering specification for a local NQ futures machine-learning research platform  
**Primary implementation assistant:** Claude Code  
**Primary compute environment:** Local workstation  
**Research instrument:** CME E-mini Nasdaq-100 Futures (NQ)  
**Primary trading/research horizon:** Approximately 1 minute and above  
**Not an HFT / next-tick / sub-second scalping project**

**Freeze rule:** Any material change to labels, partitions, timestamp/as-of semantics, sampling, evaluation, or holdout policy after this version requires a documented protocol amendment and version bump.

---

# 1. Mission

Build a local, reproducible quantitative research platform that can discover, test, falsify, and explain statistically persistent market behaviours in NQ futures.

The platform is **not** intended to:

- encode a library of conventional trading strategies and optimize parameters until one backtests well;
- predict the next tick or compete with colocated HFT firms;
- maximize backtest profit during development;
- treat the AI assistant itself as the predictive model;
- search indefinitely until a profitable-looking result appears.

The platform **is** intended to:

1. ingest high-quality NQ market data;
2. construct point-in-time-correct market states;
3. learn relationships between current market state and future price behaviour;
4. discover potentially useful market states or feature interactions that were not explicitly programmed as strategies;
5. convert discoveries into explicit hypotheses;
6. test those hypotheses chronologically and out of sample;
7. measure statistical and economic significance separately;
8. aggressively falsify promising findings;
9. determine whether deeper market data such as MBP-10 or full MBO adds meaningful value beyond MBP-1;
10. eventually turn only robust, understandable findings into executable strategies.

The research philosophy is:

> Use ML as a hypothesis-generation and conditional-state discovery engine, not as a machine for optimizing a backtest.

---

# 2. Current Data Assets and Intended Purchases

## 2.1 Existing trades data

Approximately two years of historical NQ trades data.

Expected Databento trades fields include:

- `ts_recv`
- `ts_event`
- `rtype`
- `publisher_id`
- `instrument_id`
- `action`
- `side`
- `depth`
- `price`
- `size`
- `flags`
- `ts_in_delta`
- `sequence`
- `symbol`

The Databento `side` field is expected to identify aggressor side when populated.

Before assuming this in research, Milestone 0 must measure:

- percentage of rows with `side=None`;
- percentage by day;
- percentage by RTH/ETH;
- percentage by contract;
- whether missing side correlates with unusual market conditions;
- whether `action == "T"` as expected;
- whether `depth == 0` as expected;
- timestamp monotonicity and sequence behaviour.

Trades with unavailable aggressor side must be treated as **unsigned**, not silently dropped unless a documented rule explicitly says otherwise.

## 2.2 Planned two-year MBP-1 dataset

The preferred broad historical market dataset is now **approximately two years of NQ MBP-1** covering the same intended research period as the existing trades data.

Reason:

- MBP-1 provides exact event-level top-of-book changes;
- it supports true bid/ask/mid reconstruction at L1;
- it avoids last-trade bid/ask bounce contamination;
- it allows dynamic L1 features rather than only 1-second snapshots;
- it supports sub-second feature windows while preserving slower 1-minute+ prediction horizons;
- it is a stronger foundation than BBO-1s if the purchase cost is acceptable;
- BBO-1s does not need to be bought separately for the same period if MBP-1 is purchased.

MBP-1 should be treated as the **canonical V1 broad market-data source** once validated.

Before purchasing the full history, acquire approximately one ordinary trading week of MBP-1 and complete the Milestone 0 sample audit: schema, packet/F_LAST semantics, side population, action/depth behaviour, instrument mapping, timestamps, and reconciliation against the existing trades files. Purchase the remaining history only after this sample is PASS.

Storage planning must assume substantially more than raw vendor size. With roughly 361 GB raw MBP-1 plus normalized Parquet, QA artifacts, derived features, experiment outputs, and existing MBO, plan for **at least ~1 TB free NVMe**, with **2 TB preferred** for operational headroom.

The existing trades dataset should still be retained as an independent QA/reference source. Because both sources originate from the same market feed/vendor ecosystem, reconciliation primarily validates download completeness, parsing, filtering, and event interpretation; it is not statistically independent market evidence.

## 2.3 Existing MBO dataset

There are approximately 80–90 NQ MBO trading sessions, scattered over roughly August 2025 through August 2026.

They are **not one continuous block**.

They include isolated sessions and short contiguous blocks.

The approximate observed ranges include:

- 2025-08-18 → 2025-08-26
- 2025-09-08
- 2025-09-19
- 2025-09-24 → 2025-09-25
- 2025-10-01
- 2025-10-09 → 2025-10-13
- 2025-10-20
- 2025-10-30 → 2025-11-07
- 2025-11-18
- 2025-11-26
- 2026-01-06 → 2026-01-13
- 2026-01-16
- 2026-01-22
- 2026-01-28
- 2026-02-05 → 2026-02-06
- 2026-02-23 → 2026-02-24
- 2026-03-04 → 2026-03-09
- 2026-03-18
- 2026-03-24 → 2026-03-26
- 2026-05-08
- 2026-05-15
- 2026-05-27 → 2026-05-28
- 2026-06-02
- 2026-06-08 → 2026-06-10
- 2026-06-18
- 2026-06-29 → 2026-07-06
- 2026-07-10 → 2026-07-13
- 2026-07-16
- 2026-07-22 → 2026-07-28
- 2026-08-04 → 2026-08-07

**These ranges must be replaced by the exact machine-readable session list during Milestone 0.**

Each contiguous MBO run gets a stable `mbo_lab_block_id`.

Because sessions within a contiguous block share market regime and dependence, **MBO inferential resampling must use blocks, not individual days, as the primary bootstrap/CV group**.

---

# 3. Research Horizon

This project is not for 100 ms / 1 second microscalping.

Fast market information may be used as **input**, but the intended economic horizon is slower.

## 3.1 V1 primary prediction horizons

- 60 seconds
- 5 minutes

## 3.2 V1 secondary horizon

- 15 minutes

## 3.3 Diagnostic horizon

- 30 seconds

Do not add 2-minute, 10-minute, or many closely spaced horizons in V1 merely to search for the best result.

Every additional horizon increases the multiple-testing burden.

---

# 4. Core Research Principle: Feature Window != Prediction Horizon

The feature engine may calculate information over very short backward-looking windows such as:

- 100 ms
- 250 ms
- 500 ms
- 1 s
- 2 s
- 5 s
- 10 s
- 30 s
- 60 s

provided those features can be calculated point-in-time correctly from available MBP-1/trades data.

This does **not** imply a sub-second trading strategy.

Example:

```text
last 5 seconds:
    aggressive selling accelerates
    quote-update rate spikes
    bid repeatedly replenishes
    mid barely declines

predict:
    signed normalized return over next 60 seconds / 5 minutes
```

This separation must remain explicit throughout the project.

---

# 5. Data Roles

Use explicit dataset roles. Never combine heterogeneous availability into one table and allow missingness itself to become predictive.

## 5.1 BROAD

Primary research dataset.

Expected V1 source:

```text
MBP-1 + validated trade information
```

approximately two years.

Used for:

- feature research;
- baselines;
- LightGBM;
- pattern discovery;
- development;
- chronological selection;
- final holdout.

## 5.2 MBO_LAB

Explicit set of scattered sessions with full MBO.

Used to determine whether deeper market information adds value beyond the broad MBP-1 model.

Possible tiers:

- T0 = MBP-1 baseline
- T1 = MBP-10-equivalent aggregated depth features
- T2 = full MBO order-level features

If useful, a synthetic/degraded BBO-1s representation can be constructed as a diagnostic tier, but because MBP-1 is now the broad baseline, it is no longer required for the main purchase ladder.

MBO_LAB must have:

- explicit session IDs;
- block IDs;
- partition role;
- documented selection reason if known.

## 5.3 HOLDOUT

Final untouched chronological period.

Tentative target: approximately 4–5 months.

Exact dates must be fixed during Milestone 0 based only on:

- data coverage;
- availability of MBO sessions;
- desired development/selection length;

and **never on model outcomes**.

A candidate boundary discussed during planning is approximately `2026-04-01`, but this is NOT final until Milestone 0 determines exact broad-data coverage.

Any MBO sessions falling inside HOLDOUT are also HOLDOUT and may not be used in MBO discovery or ladder development.

## 5.4 FORWARD

All data collected after project start.

Forward data is considered the cleanest eventual confirmation because it could not have influenced historical research.

Start continuous collection as early as practical.

---

# 6. Partition Rules

The canonical chronology is:

```text
DEV
→
SELECTION
→
HOLDOUT
→
FORWARD
```

`MBO_LAB` is an orthogonal session flag within the historical timeline.

## 6.1 DEV

Allowed:

- exploratory feature development;
- visual analysis;
- SHAP discovery;
- rule mining;
- MBO exploration on MBO_LAB sessions that fall in DEV;
- engineering iterations;
- hypothesis generation.

Not valid as final evidence.

## 6.2 SELECTION

Allowed:

- pre-registered tests;
- chronological walk-forward comparison;
- model selection;
- confirmatory testing of hypotheses discovered in DEV;
- MBO confirmation on MBO_LAB sessions that fall in SELECTION.

Once selection results influence a decision, they are no longer considered untouched OOS evidence.

Call this partition **SELECTION**, not “final OOS.”

## 6.3 HOLDOUT

Forbidden during ordinary development.

May not be used for:

- feature design;
- model selection;
- threshold selection;
- visual inspection;
- MBO exploration;
- hyperparameter selection;
- debugging results;
- regime definition;
- candidate rescue.

Only a frozen evaluation plan may access it.

---

# 7. Holdout Access Policy

Holdout protection must be mechanical, not merely documented.

Recommended controls:

- `data/holdout/` protected by filesystem permissions;
- normal development user has no direct read permission;
- loader refuses HOLDOUT date ranges by default;
- explicit override flag required;
- every override writes an immutable audit entry;
- Claude Code permissions/hooks deny HOLDOUT paths;
- no notebook may directly read holdout files;
- HOLDOUT access command must be separate from normal experiment execution.

Before an opening, commit:

```text
docs/holdout_plan_01.md
```

containing:

- exact frozen candidate IDs;
- exact feature versions;
- exact label version;
- exact model configuration;
- exact sample-table version;
- exact metrics;
- exact cost model;
- exact success/failure criteria;
- exact outputs to be generated;
- statement that no modification is permitted during the opening.

Maximum planned historical holdout openings:

1. opening #1 for the frozen V1 system;
2. opening #2 only after a genuinely documented methodological redesign, not ordinary tuning.

Every opening is permanent and logged.

---

# 8. Futures Contract Handling

NQ futures are separate instruments.

The system must preserve:

- `instrument_id`;
- raw contract symbol;
- continuous selector if used for acquisition;
- roll/switch timestamp;
- session;
- roll-week flag.

For acquisition, volume-leading continuous symbology such as `NQ.v.0` is acceptable if it maps to actual underlying contracts and the underlying `instrument_id` is preserved.

Never back-adjust event-level prices for this research.

Never compute a feature or target across an instrument switch.

Samples must be dropped if:

- feature lookback crosses a contract switch;
- latency interval crosses a switch;
- label horizon crosses a switch.

Roll week should be retained as a robustness flag rather than automatically excluded.

All joins should prefer `instrument_id`, not display symbol.

---

# 9. Time Standard and Timestamp Policy

Define `session_id` as the **CME trading day** using the configured 17:00 America/Chicago session boundary. Partition boundaries must occur only at complete trading-day boundaries.

V1 RTH is configured as **08:30–15:00 America/Chicago**. Storage remains UTC; DST changes the UTC offset of RTH and must never be implemented as a fixed UTC window.

Canonical internal time representation:

```text
UTC nanoseconds
```

Every normalized record must preserve original relevant timestamps.

The project must explicitly document which timestamp is canonical for research:

- `ts_event` for exchange event chronology;
- `ts_recv` only where reception/latency analysis explicitly requires it.

V1 research chronology is based on `ts_event`. `ts_recv` is preserved for QA/latency diagnostics but ignored for event ordering and feature/label chronology. The configured decision latency (primary 500 ms) is intentionally much larger than ordinary feed receipt delay, so research ordering is exchange-event-time based.

Never silently convert to local wall time.

Exchange-local/session fields may be derived separately for:

- RTH segmentation;
- time-of-day features;
- DST handling.

Tests must cover:

- DST transitions;
- CME session boundary;
- holidays;
- shortened sessions;
- midnight UTC crossings;
- out-of-order arrival;
- duplicate timestamps;
- sequence resets;
- gaps.

---

# 10. V1 Session Scope

Registered V1 experiments operate on **RTH only**.

Exact RTH definition must be stored in configuration and not hardcoded throughout code.

ETH/overnight data should still be:

- ingested;
- normalized;
- QA'd;
- flagged;

but not used in registered V1 model selection.

Later research may test transfer/generalization to ETH.

RTH samples **may use backward-looking ETH observations from the same CME trading session** when the feature definition explicitly permits it. No lookback may cross the 17:00 CT trading-session boundary. Include `seconds_since_rth_open` as context. Stateful RTH-specific estimators must document their open initialization rather than accidentally carrying an inappropriate ETH state.

---

# 11. Immutable Raw Data

Raw vendor data is immutable.

Never:

- edit;
- normalize in place;
- delete because it appears bad;
- rewrite;
- silently repair.

Directory model:

```text
data/
  raw/
  normalized/
  qa/
  samples/
  features/
  labels/
  datasets/
  holdout/
```

All derived data must be reproducible from:

- raw input;
- code version;
- config;
- dependency versions.

Raw data is never committed to Git.

---

# 12. Data QA Layer

A persistent QA artifact must exist before any dataset can be used for research.

Each session should receive a QA report containing at minimum:

- row count;
- first/last event timestamp;
- session coverage;
- contract;
- `instrument_id`;
- sequence min/max;
- gap detection;
- duplicate detection;
- out-of-order events;
- spread sanity;
- crossed/locked market checks;
- non-negative quantities;
- trade count;
- traded volume;
- aggressor-side coverage;
- missing values;
- unexpected flags/actions;
- roll proximity;
- session completeness.

Store a machine-readable QA status:

```text
PASS
WARN
FAIL
```

Experiments may only use `PASS` or explicitly approved `WARN` sessions.

Any exclusion must have a reason code.

Do not delete anomalous days just because model performance is bad.

---

# 13. Independent Cross-Source QA

Existing standalone trades data should be used to validate MBP-1-derived trade information.

Compare by session:

- trade count;
- total volume;
- aggressor side counts;
- price distribution;
- first/last timestamps;
- sequence behaviour where comparable.

Discrepancies above tolerance must stop the pipeline.

For MBO reconstruction:

- reconstruct L1 and top-N aggregated book;
- compare reconstructed L1 with MBP-1 where overlapping;
- optionally purchase vendor MBP-10 for a small number of sessions as independent depth ground truth;
- reconcile MBO executions against trades schema.

MBO-specific invariants:

- best bid < best ask unless documented exceptional state;
- no negative order quantity;
- per-level quantity equals sum of resting orders;
- add/cancel/modify/fill lifecycle consistency;
- order IDs handled correctly;
- reset/snapshot rules handled;
- session resets handled;
- contract changes handled;
- sequence ordering correct;
- vendor flags such as `F_LAST` handled correctly where relevant.

If the existing C++ reconstruction engine fails validation:

1. diagnose/fix it;
2. if necessary, use vendor MBP-10 for aggregated depth;
3. defer order-level research;

Do **not** automatically rewrite the engine in Python.

---

# 14. Sample Table

Sampling is a first-class versioned artifact.

Canonical fields:

```text
sample_id
clock_version
timestamp
session_id
instrument_id
raw_contract
sampling_method
sampling_parameter
trigger_sequence
mbo_lab
mbo_lab_block_id
partition
rth_flag
roll_week_flag
```

No feature or label module chooses its own timestamps independently.

Everything joins to `sample_id`.

---

# 15. Sampling Methods

## 15.1 Primary V1: volume clock

Choose N mechanically, not by predictive optimization.

Initial rule:

```text
N = median DEV-period RTH contract volume / 400
```

rounded to a sensible contract count.

Goal: roughly several hundred samples per ordinary RTH session.

N is pre-registered.

Accumulator rule: accumulate eligible traded contracts in event order; when cumulative volume `>= N`, emit one sample at the F_LAST-complete trigger state, subtract N (carry excess forward), and continue. If multiple emissions would share the same nanosecond/F_LAST state, deduplicate to one sample and record the carried accumulator deterministically. `trigger_sequence` anchors the exact event/as-of location. Volume-clock accumulators reset at contract switches and trading-session boundaries.

Sensitivity:

- `N/2`
- `2N`

These are robustness checks, not alternative candidates from which the best result is selected.

## 15.2 Control: time clock

Use a simple fixed interval such as 30 seconds as a control representation.

Do not choose the interval based on which backtests better.

## 15.3 Event clock

Define interface/schema in V1 but do not make event sampling a primary research axis initially.

Later event triggers must be defined from primitive statistical extremes, not named subjective setups.

---

# 16. Point-in-Time Correctness

Every feature family must declare:

- required source(s);
- minimum lookback;
- maximum lookback;
- as-of timestamp;
- whether it uses event or receive time;
- whether it requires continuous book state;
- whether it may cross session boundary (default NO);
- whether it may cross contract boundary (NO).

Automated invariant:

```text
max(source_timestamp_used_by_feature) <= sample.timestamp
```

For Databento packetized book data, any book state used by a feature or label must be an **F_LAST-complete state**. Partial packet states are not valid observations. The trigger event packet is included at T only after that packet is complete.

No forward fill or rolling window may cross:

- session boundary;
- contract boundary;
- disallowed data gap.

---

# 17. Price Definition

Market movement features and labels must use:

```text
mid = (best_bid + best_ask) / 2
```

or another explicitly approved executable/quote-derived price.

Do not use last-trade price as the canonical market return.

Reason: bid/ask bounce can create fake short-horizon mean reversion/predictability.

Internally preserve vendor prices as integer-scaled values (`int64`, vendor 1e-9 scale) or exact integer ticks for equality-sensitive logic. Convert to floating-point only at reporting/model boundaries where appropriate.

Trade price may still be used legitimately as a **trade/execution descriptor**, e.g.:

- execution price relative to mid;
- sweep progression;
- trade-price dispersion;
- aggressive execution levels.

Rule:

> Market returns, momentum, response features, and targets use quote-derived price. Trade prices may describe execution flow but may not substitute for market state.

---

# 18. Latency Model

Observation occurs at `T`.

Economic availability begins at:

```text
T + δ
```

V1:

- primary `δ = 500 ms`;
- sensitivity `δ = 250 ms`;
- sensitivity `δ = 1000 ms`.

Because MBP-1 is event-level, entry/reference state at `T + δ` means the **first F_LAST-complete state at or after `T + δ`**. Horizon-end price means the **last F_LAST-complete state with `ts_event <= T + δ + H`**. These rules are versioned and tested.

`latency_ms` belongs to the **label/evaluation version**, not sample identity; changing δ must not duplicate the sample table.

Do not assume execution at the exact feature timestamp.

Keep latency as configuration and include it in:

- sample-table version;
- label version;
- experiment registration.

---

# 19. Labels

Feature and label code must be physically/logically separate.

V1 should use **one main target family** to control trial count.

For horizon H:

```text
r_H(T) = mid(T + δ + H) - mid(T + δ)
```

or log/point-equivalent return as specified in the label config.

Normalize by volatility known strictly at T:

```text
y_H = clip(r_H(T) / sigma_H(T), -3, +3)
```

Primary model task:

```text
regression
```

Primary horizons:

- 60 s
- 5 min

Secondary:

- 15 min

Diagnostic:

- 30 s

Do not make barriers/MFE/MAE primary V1 targets.

---

# 20. Volatility Estimator

V1 initial estimator:

- EWMA of squared 1-second mid returns;
- approximately 10-minute half-life;
- strictly backward-looking;
- floor to prevent numerical explosion in very quiet intervals;
- scale to horizon H using square-root-of-time as the simple V1 approximation.

The 10-minute half-life is a fixed V1 design choice, not an optimized parameter.

Development QA should test normalized target variance across:

- RTH time-of-day buckets;
- volatility terciles;
- months.

The RTH open requires an explicit, strictly backward-looking warm-start policy so ETH carryover cannot mechanically understate 08:30 CT volatility. The initial candidate is the median realized variance for 08:30–08:40 over the prior 20 eligible sessions. **This is a normalization/QA parameter, not a trading parameter:** validate on DEV for target-scale stability before freezing the label version; do not choose it by predictive performance. If changed, version the volatility estimator. Any time-of-day profile must be estimated from past/DEV data only.

---

# 21. Diagnostic Labels

Even though not primary model targets, calculate factual diagnostics independently:

- raw future mid return in points;
- normalized return;
- MFE;
- MAE;
- max upward excursion;
- max downward excursion;
- fixed-point barrier outcomes;
- volatility-scaled barrier outcomes;
- spread at candidate entry;
- future realized volatility.

These are for interpretation/economic analysis and must not silently become alternative model targets without a registered experiment.

---

# 22. Economic Evaluator

Keep market labels separate from execution assumptions.

Market label asks:

> What did the market do?

Economic evaluator asks:

> Could this state plausibly have been monetized?

Economic config includes:

- assumed entry type;
- observed spread;
- commissions/fees;
- slippage in ticks;
- latency;
- assumed exit type;
- optional adverse fill assumptions.

Report multiple slippage scenarios, e.g.:

- base;
- +1 tick;
- +2 ticks.

Never change the economic cost model after viewing candidate performance without versioning it and creating a new experiment.

---

# 23. Feature Philosophy

Prefer primitive and interpretable market information.

Do not prohibit all conventional indicators dogmatically.

The restriction is:

> Do not start from arbitrary hard-coded trading rules or threshold-heavy indicator strategies.

Legitimate derived quantities include:

- VWAP;
- normalized distance from session reference;
- trailing returns;
- volatility;
- rolling statistics.

Every feature must be explainable in terms of information available at T.

---

# 24. Initial Feature Families

Start with approximately 15–25 **families**, not hundreds/thousands of features.

## 24.1 Trade activity

- trade count;
- contract volume;
- mean/median trade size;
- trade-size quantiles;
- max trade size;
- large-trade share;
- inter-arrival time;
- trade-rate acceleration.

## 24.2 Signed trade flow

Using native aggressor side when valid:

- aggressive buy volume;
- aggressive sell volume;
- signed volume;
- delta;
- signed trade count;
- signed-flow acceleration;
- short/medium window ratios.

Unsigned trades remain separately counted.

## 24.3 Mid-price state

- signed mid return;
- normalized mid return;
- short-term momentum;
- short-term reversal;
- local range;
- price velocity;
- acceleration.

## 24.4 Price response to flow

Priority family.

Examples:

- mid change per signed contract;
- signed-flow magnitude vs realized mid response;
- response shortfall vs trailing norm;
- aggressive selling with weak downward response;
- aggressive buying with weak upward response;
- persistence after flow burst.

Avoid hard-coding “absorption” as a label.

Represent primitives/relationships and let models determine usefulness.

## 24.5 L1 book state from MBP-1

- spread;
- best bid size;
- best ask size;
- order count;
- L1 imbalance;
- normalized L1 imbalance;
- quote-update rate;
- bid/ask size velocity;
- bid/ask size acceleration;
- L1 replenishment/depletion proxies;
- quote persistence;
- touch migration;
- spread changes.

## 24.6 Context

- RTH time since open;
- time to close;
- session VWAP distance;
- session high/low distance calculated only from data available up to T;
- trailing volume;
- trailing volatility;
- roll-week flag.

Scheduled-event information should initially be used for stratification rather than predictive features.

---

# 25. Baseline Ladder

Every sophisticated result must be compared to strong baselines.

## Baseline 0 — Unconditional

Predict the training-set conditional mean or equivalent naive target baseline.

## Baseline 1 — Volatility/activity/time-only

Allowed:

- unsigned volatility at multiple backward windows;
- volatility ratios;
- unsigned volume;
- trade rate;
- spread;
- unsigned range;
- time of day;
- day of week.

Not allowed:

- signed returns;
- signed flow;
- directional VWAP distance;
- features being tested as order-flow signal.

## Baseline 2 — Price-only

Baseline 1 plus:

- signed mid returns over several windows;
- simple price momentum/reversal descriptors.

Purpose:

> Any claimed order-flow edge must beat not just volatility, but also plain price-history predictability.

## Baseline 3 — Regularized linear model

Use ridge/elastic-net/logistic equivalent depending on target as a simplicity/linearity reference.

## Capacity-matched baseline rule

Every substantive feature-set comparison must also be run under the **same model class and fixed comparable capacity**. In particular, fit B1/B2/B3 feature sets with LightGBM using the same fixed hyperparameter policy as the full model. The primary incremental claim compares:

```text
LightGBM(price-only feature set)
vs
LightGBM(price + signed-flow/L1 feature set)
```

This prevents nonlinear model capacity from being mistaken for new information. Ridge remains a diagnostic baseline, not the primary comparator for a LightGBM claim.

## Model 1 — LightGBM

Only one primary GBDT family in V1.

Do not add XGBoost/CatBoost merely because LightGBM underperforms.

---

# 26. Model Selection Metric

Primary predictive metric:

```text
per-session skill improvement over the **capacity-matched LightGBM price-only baseline**
```

For regression, define a pre-registered skill score such as:

```text
1 - MSE_model / MSE_price_baseline
```

Compute at the session level.

Report:

- mean;
- median;
- session bootstrap CI;
- monthly distribution;
- fraction positive.

Aggregate AUC may be reported for derived direction classifications but is not the primary model-selection metric.

---

# 27. Economic Metric

Primary economic metric:

```text
cost-adjusted expectancy in pre-registered extreme score buckets
```

Use fixed candidate tails such as:

- top 5%;
- bottom 5%;
- optionally top/bottom 10%.

Critical rule:

> Bucket thresholds are derived from the TRAINING fold score distribution, never from the test fold distribution.

Report per bucket:

- observations;
- sessions represented;
- blocks represented where relevant;
- mean return;
- median;
- normalized return;
- MFE;
- MAE;
- favourable-outcome probability;
- net expectancy in ticks/points;
- positive-session proportion;
- positive-month proportion;
- CI;
- concentration in best/worst days.

Finer percentile buckets may be descriptive only.

---

# 28. Statistical Unit and Dependence

Broad research primary inference unit:

```text
trading session
```

Do not treat millions of intraday rows as independent evidence.

Use:

- session-grouped CV;
- purging;
- horizon-aware embargo;
- per-session metrics;
- session bootstrap;
- month-by-month stability.

For MBO_LAB:

```text
contiguous MBO block
```

is the primary inferential bootstrap/CV unit.

Report both:

- positive blocks;
- positive days;

but do not use days within the same contiguous MBO block as independent resampling units.

---

# 29. Walk-Forward Selection

All CV remains chronological.

Never random-shuffle market observations.

Use rolling or expanding walk-forward folds with:

- session grouping;
- purge interval;
- embargo >= relevant forward horizon;
- preprocessing fit only on training fold;
- bucket thresholds fit only on training fold;
- feature selection performed within allowed partition logic.

The SELECTION period is a selection environment, not pristine final OOS.

There is **no automated feature selection in V1**. Feature families are pre-registered per experiment. Robustness configurations (δ, N, and cost sensitivities) are registered children of the parent experiment and are robustness checks, not a pool from which the best configuration is selected.

---

# 30. MBO Lab Selection Bias

The MBO sessions are not assumed random.

During Milestone 0:

- document why each block was acquired if known;
- compare MBO_LAB distribution to the broad population on:
  - trailing volatility;
  - RTH volume;
  - scheduled-event flag;
  - day of week;
  - roll week;
  - month/year.

Do not automatically reweight MBO sessions.

Instead report external-validity limitations.

If MBO_LAB is heavily skewed toward high-volatility/interesting days and gains concentrate there, report the measured gain as conditional and possibly an upper bound for ordinary sessions.

---

# 31. MBO Incremental-Information Ladder

Purpose:

> Determine whether deeper market information adds predictive value beyond the two-year MBP-1 broad model.

Do **not** compare independently optimized models trained only on the small MBO sample.

## 31.1 BROAD_LADDER

Create a dedicated frozen broad model:

- identical feature families/config/hyperparameters to the main broad model;
- trained on allowed DEV+SELECTION history;
- **exclude all MBO_LAB sessions**, regardless of which lab subset is currently being evaluated.

Reason:

If broad model trains on lab sessions, broad scores on those sessions become in-sample and may bias the incremental tier test.

## 31.2 Tier structure

Tentative:

```text
T0 = BROAD_LADDER score + MBP-1 baseline features
T1 = T0 + aggregated MBP-10-like depth features
T2 = T1 + full MBO order-level features
```

If useful, additional diagnostic degraded representations may be tested, but each is a registered tier/trial.

Tier feature families are explored only on DEV-lab blocks, then frozen. The pre-registered ladder may use all eligible non-HOLDOUT DEV+SELECTION MBO blocks under block-grouped CV for power, but must report both **all-lab** and **SELECTION-only lab** results.

A small vendor MBP-10 validation sample (at least several representative sessions/contracts) is **required** before T1 depth results are trusted; L1 agreement alone does not validate levels 2–10.

All tiers use:

- identical sample table;
- identical labels;
- identical folds;
- fixed hyperparameters where possible.

## 31.3 Capacity/permutation control

For each added tier, run approximately **10 independently seeded permutation draws** and report the control distribution rather than relying on a single permutation.

- preserve feature count and marginal distributions;
- permute new tier values within appropriate day/block constraints;
- destroy temporal alignment.

Compare:

1. real tier vs T0;
2. real tier vs permuted-tier control.

Interpretation:

- gain over T0 = information + extra capacity;
- gain over permutation control = evidence that aligned information matters.

## 31.4 MBO ladder metrics

Primary predictive metric:

- paired block/session skill difference vs T0.

Primary economic metric:

- paired difference in cost-adjusted tail expectancy.

Report:

- block-bootstrap 95% CI;
- positive-block proportion;
- positive-day proportion;
- first-half vs second-half lab period;
- volatility-tercile stratification;
- concentration in best five sessions/blocks;
- effect size.

Do not claim "MBO has no value" from a null result.

Correct language:

> Within this sample, improvement is below the estimated confidence-bound magnitude.

The scattered MBO lab can detect large, reasonably consistent incremental effects; it has limited power to distinguish tiny improvements.

---

# 32. MBO Feature Families

## 32.1 Aggregated depth

- depth at L1/L3/L5/L10;
- distance-weighted depth;
- depth slope;
- bid/ask depth ratio;
- order-count depth ratio;
- depth velocity;
- depth acceleration.

## 32.2 Additions/cancellations

Where genuinely recoverable:

- bid additions;
- ask additions;
- bid cancellations;
- ask cancellations;
- add/cancel ratio;
- near-touch vs deeper activity;
- cancellation acceleration.

Do not describe inferred aggregate changes as individual-order cancellations unless MBO order identity proves them.

## 32.3 Execution/liquidity interaction

- execution-to-displayed ratio;
- aggressive flow vs resting liquidity;
- liquidity consumed per price movement;
- price response after queue depletion.

## 32.4 Replenishment

Represent quantitatively rather than hard-code "absorption":

- executed quantity at level;
- new resting quantity after executions;
- persistence;
- net replenishment;
- repeated replenishment;
- response of price to sustained execution.

## 32.5 Liquidity pulling

- near-touch cancellation bursts;
- asymmetric withdrawal;
- depth collapse;
- liquidity migration;
- price response after withdrawal.

## 32.6 True MBO-only information

- individual order lifecycle;
- order persistence;
- order persistence and lifecycle statistics;
- order replacement behaviour where directly observable;
- order-age distributions.

Queue-position inference and repeated re-entry/identity-pattern research are deferred to V2 unless a later protocol amendment demonstrates a precise, validated definition.

Every MBO-only feature must document exactly what is observable and what is inferred.

---

# 33. Discovery vs Confirmation

This separation is mandatory.

## Discovery

Allowed in DEV:

- LightGBM SHAP analysis;
- shallow-tree leaf mining;
- exploratory plots.

Discovery generates hypotheses.

It does not prove them.

## Confirmation

Every interesting rule becomes a numbered hypothesis:

```text
HYP-0001
HYP-0002
...
```

A hypothesis must specify:

- exact feature conditions;
- target;
- horizon;
- population;
- direction;
- primary metric;
- kill criterion.

Test in SELECTION without modifying the hypothesis.

If K hypotheses are mined simultaneously, record K.

Use Benjamini-Hochberg FDR or another pre-specified correction for batches of mined hypotheses where trial counts become large.

---

# 34. Clustering

Clustering/UMAP/HDBSCAN are **not part of V1 implementation**. They may be proposed in a future protocol amendment for regime context or QA, but may not expand the V1 research surface.

---

# 35. Falsification Battery

Every candidate that graduates from exploration must be run through one commandable battery.

Required tests include:

- shifted-label test;
- permuted-label test;
- feature temporal-shift test;
- leakage audit;
- adjacent-window sensitivity;
- latency sensitivity (250/500/1000 ms);
- sample-volume sensitivity (`N/2`, `N`, `2N`);
- evaluation jackknife over stored predictions (no refit);
- drop the five best sessions as a concentration stress test;
- month-drop sensitivity;
- volatility-tercile split;
- scheduled-event-day exclusion;
- roll-week exclusion;
- transaction-cost +1 tick;
- transaction-cost +2 ticks;
- feature-family ablation;
- price-only baseline comparison;
- broad-model baseline comparison.

No candidate survives merely because the central configuration works.

---

# 36. "Too Good" Alarm

Unexpectedly strong results trigger suspicion before excitement.

Use configurable absolute and relative thresholds.

Possible V1 defaults for investigation only:

- directional AUC unexpectedly > ~0.58 at >=60 s;
- top-5% net expectancy > ~3 ticks at 60 s;
- positive-day proportion > ~80%;
- skill score > 3x the running best comparable experiment;
- metric > 3 SD from comparable registry history.

If triggered:

```text
status = SUSPECT_AUDIT_REQUIRED
```

Before interpretation run:

- timestamp audit;
- label alignment audit;
- feature source-time audit;
- shift test;
- permutation test;
- feature removal;
- session concentration;
- contract/roll check;
- train/test overlap check;
- duplicate-row check.

Threshold values are configurable heuristics, not universal truths.

---

# 37. Pre-Registration

Experiments have immutable states:

```text
PLANNED
RUNNING
PASSED
FAILED
INCONCLUSIVE
SUSPECT_AUDIT_REQUIRED
```

Before a registered run store:

- experiment ID;
- creation timestamp;
- research question;
- hypothesis;
- dataset version;
- partition;
- sample-table version;
- feature-family versions/hashes;
- label version;
- volatility estimator version;
- horizon;
- latency;
- fold scheme;
- seeds;
- model type;
- hyperparameters;
- primary metric;
- secondary metrics;
- acceptance criterion;
- kill criteria;
- cost-model version.

Once execution begins, the registered specification is immutable.

New idea after seeing results = new experiment.

Never rewrite the hypothesis retrospectively.

---

# 38. Experiment Registry

Initial implementation:

```text
DuckDB
```

plus one directory per experiment.

Example:

```text
experiments/
  EXP-0042/
    prereg.yaml
    config.yaml
    metrics.json
    daily_metrics.parquet
    predictions.parquet
    plots/
    notes.md
    audit.json
```

Registry stores:

- Git commit;
- dependency lock hash;
- source dataset hashes;
- outputs;
- status;
- parent experiment/hypothesis;
- notes.

MLflow is not required in V1.

Design metadata so MLflow can be added later without redesign.

---

# 39. Multiple Testing

Controls required from day one:

- experiment registration;
- trial counter;
- failed-run retention;
- immutable hypotheses;
- fixed primary metric;
- fixed primary horizons;
- fixed model family;
- holdout protection;
- BH-FDR for batches of mined hypotheses;
- no silent hyperparameter sweeps;
- every hyperparameter configuration counts as a trial.

Later/finalist controls may include:

- Deflated Sharpe Ratio;
- PBO;
- CPCV.

White's Reality Check / SPA are not required in V1 unless later justified.

---

# 40. Scheduled Macro Events

Create an external calendar table for known scheduled events such as:

- FOMC;
- CPI;
- NFP;
- PPI;
- GDP;
- selected major Fed events if sourced reliably.

V1:

- use for stratification/robustness reporting;
- do not use as broad predictive features.

Report candidate results:

- all sessions;
- event sessions;
- non-event sessions.

If a small number of event sessions dominate performance, state it explicitly.

---

# 41. Normalization and Non-Stationarity

The feature registry must reject model-input features that encode dataset/era identity rather than market state. Forbidden as direct model inputs in V1:

- `instrument_id`;
- raw contract symbol;
- `session_id`;
- partition;
- `mbo_lab` / `mbo_lab_block_id`;
- absolute calendar date, calendar month, or calendar year;
- raw absolute NQ price level.

Raw absolute volume is not universally forbidden because it is observable market information, but long-horizon models should prefer trailing/relative/normalized volume measures; any raw-volume feature must justify stationarity and pass era-stability checks. Dataset-availability/missingness flags are forbidden predictive inputs.

Any scaler/statistic must be fit using past/training data only.

Preferred:

- ratios;
- volatility scaling;
- trailing z-scores;
- trailing ranks;
- same-time-of-day trailing statistics if later justified.

Never normalize using full-dataset mean/std.

Never use future session statistics.

Avoid raw point thresholds where volatility-scaled equivalents make more sense.

---

# 42. Research Journal

Every experiment, including failures, gets a human-readable note.

Template:

```text
QUESTION
HYPOTHESIS
WHY THIS TEST
DATA/PARTITION
PRIMARY METRIC
KILL CRITERIA
RESULT
STABILITY
FALSIFICATION
INTERPRETATION
DECISION
NEXT QUESTION
```

Failed experiments are retained permanently.

The project should make it easier to remember failures than to forget them.

---

# 43. Claude Code Operating Rules

The repository must include a concise `CLAUDE.md` generated from this canonical spec.

Non-negotiable rules:

1. Objective is a correct answer, not a profitable result.
2. Never use future information in a feature.
3. Never shuffle observations across train/test boundaries or across time for model evaluation. Permutation canaries/controls and model-internal bagging are allowed only when explicitly specified and cannot alter chronological evaluation.
4. Never access HOLDOUT without explicit authorized workflow.
5. Raw data is immutable.
6. Never silently alter labels/evaluation to improve results.
7. Never weaken/change a test solely to make implementation pass.
8. Any legitimate test change must document the changed requirement.
9. Changes to sampling, labels, evaluation, partitions, or cost model require explicit review.
10. Every experiment is registered before execution.
11. Failed/null experiments are retained and reported.
12. Do not add another model family merely because the current model failed.
13. "Too good" results trigger audit.
14. All timestamps use canonical UTC nanoseconds with explicit event/receive semantics.
15. No rolling/forward-fill operation crosses session or contract boundary.
16. Any feature must declare its as-of window and dependencies.
17. No feature may use source data timestamped after its sample timestamp.
18. Bucket thresholds are trained on training folds only.
19. Do not optimize indefinitely on SELECTION.
20. Holdout output may not be used for iterative rescue.
21. Every result must link to dataset/config/code version.
22. Every MBO inference reports block-level uncertainty.
23. AI-generated interpretations are hypotheses, not evidence.
24. Claude must challenge leakage and selection bias before suggesting optimization.

---

# 44. Builder/Auditor Workflow

For sensitive code, separate implementation and audit contexts.

## Builder session

Implements:

- feature;
- label;
- sampling change;
- model;
- pipeline.

## Auditor session

Fresh context.

Prompt assumption:

> Assume this implementation may contain leakage, timestamp errors, alignment errors, invalid statistical assumptions, or accidental holdout contamination. Attempt to falsify correctness.

Reusable prompts:

```text
prompts/
  audit_feature.md
  audit_label.md
  audit_sampling.md
  audit_evaluation.md
  audit_holdout.md
  audit_mbo_reconstruction.md
```

Every feature family gets:

- automated point-in-time tests;
- a lightweight audit.

Sampling, label, partition, evaluation, holdout, or MBO reconstruction changes require stronger audit/human review.

---

# 45. Repository Structure

```text
nq-research/
│
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── uv.lock
│
├── docs/
│   ├── research-protocol.md
│   ├── data-specification.md
│   ├── experiment-protocol.md
│   ├── holdout-policy.md
│   └── architecture.md
│
├── config/
│   ├── data/
│   ├── partitions/
│   ├── sampling/
│   ├── features/
│   ├── labels/
│   ├── models/
│   ├── costs/
│   └── experiments/
│
├── data/
│   ├── raw/
│   │   ├── trades/
│   │   ├── mbp1/
│   │   └── mbo/
│   ├── normalized/
│   ├── qa/
│   ├── samples/
│   ├── features/
│   ├── labels/
│   ├── datasets/
│   └── holdout/
│
├── src/
│   └── nqresearch/
│       ├── ingest/
│       ├── normalize/
│       ├── qa/
│       ├── sessions/
│       ├── sampling/
│       ├── features/
│       ├── labels/
│       ├── volatility/
│       ├── models/
│       ├── experiments/
│       ├── evaluation/
│       ├── discovery/
│       ├── falsification/
│       ├── economics/
│       ├── mbo/
│       └── reporting/
│
├── tests/
│   ├── unit/
│   ├── property/
│   ├── integration/
│   └── leakage/
│
├── experiments/
├── reports/
├── prompts/
└── notebooks/
```

Notebooks are exploratory only.

Production research logic must live in tested modules.

---

# 46. Recommended Stack

## Python environment

- Python 3.12+ unless dependency compatibility dictates otherwise
- `uv`
- pinned dependency versions

## Data

- Parquet
- PyArrow
- Polars
- DuckDB

## Validation/config

- Pydantic
- YAML for human-authored config

## ML

V1:

- scikit-learn
- LightGBM

Later only if justified:

- PyTorch

## Testing

- pytest
- Hypothesis property-based tests where useful

No MLflow, MCP, sequence model stack, or distributed compute required in V1.

---

# 47. Reproducibility

Every run must capture:

- Git SHA;
- Python version;
- OS/platform;
- dependency lock hash;
- dataset version/hash;
- config hash;
- random seeds;
- experiment ID.

Deterministic mode should be used where practical.

If a library remains nondeterministic, document it.

---

# 48. Feature Registry

Each feature family has metadata:

```yaml
name:
version:
sources:
lookback:
asof_policy:
session_crossing: false
contract_crossing: false
requires_mbo: false
requires_depth:
normalization:
description:
```

The registry should support automated leakage tests.

Feature code should not be an untracked collection of dataframe expressions.

---

# 49. Label Registry

Each label includes:

```yaml
name:
version:
horizon:
latency_ms:
price_source:
volatility_version:
normalization:
clip:
session_crossing: false
contract_crossing: false
```

No experiment may define an ad hoc label in notebook code.

---

# 50. Data Exclusion Rules

Allowed exclusions:

- vendor-corrupt session;
- unrecoverable data gap;
- invalid book reconstruction;
- session missing required coverage;
- feature window crossing contract boundary;
- target horizon crossing contract boundary;
- predefined holiday/partial-session rule.

Forbidden exclusions:

- "bad P&L day";
- "unusual market";
- "model doesn't work here";
- outlier removed after seeing performance;
- event day removed solely because it hurts results.

Every exclusion has a machine-readable reason.

---

# 51. Missing Data

Never silently forward-fill across:

- contract switches;
- sessions;
- long quote gaps.

For small allowed gaps, the imputation rule must be:

- explicit;
- feature-specific;
- point-in-time;
- tested.

Missingness indicators may be included only if missingness is a legitimate real-time observable rather than a dataset-availability artifact.

Never allow:

```text
has_mbo = 1
```

or missing MBO columns to become a predictive proxy for calendar era.

---

# 52. Leakage Canary Tests

The system should include deliberately impossible tests.

## Permuted target

Randomly permute targets within safe grouping.

Model should return no meaningful predictive skill.

## Shifted future target

Apply intentionally incorrect shift to ensure tests detect leakage behaviour.

## Future feature canary

A deliberately future-derived test feature should be caught by source-time validation and rejected before training.

## Random noise features

Adding noise should not systematically create stable lift.

Any failure blocks research until fixed.

---

# 53. First Registered Research Question

The first meaningful ML experiment should remain narrow:

> Does price response to signed aggressive order flow contain predictive information for future 60-second / 5-minute normalized mid return beyond volatility, activity, and price-history baselines?

Do not start with dozens of simultaneous hypotheses.

Suggested comparison:

```text
B0 unconditional
B1 volatility/activity/time
B2 price-only
B3 signed-flow primitives
M1 price-response + signed-flow LightGBM
```

Primary claim requires M1 LightGBM to beat the **capacity-matched LightGBM price-only baseline** and the corresponding signed-flow baseline, not merely a linear baseline or an absolute model score.

---

# 54. Pattern Interpretation

If LightGBM finds value, ask:

> What behaviour is it detecting?

Use:

- SHAP interaction;
- shallow surrogate trees;
- feature ablation;
- local examples.

Example discovered state:

```text
strong aggressive selling
+
weak negative mid response
+
trade-rate acceleration
+
specific volatility context
```

This becomes a hypothesis.

Do not simply tune LightGBM to increase aggregate score.

---

# 55. Strategy Construction Is Later

No general strategy/backtesting engine is required before stable predictive behaviour exists.

Candidate evolution:

```text
market behaviour
→
prediction evidence
→
interpretation
→
falsification
→
economic evaluator
→
execution hypothesis
→
strategy
→
final holdout
→
forward test
```

Do not invert this.

---

# 56. Sequence Models

Not V1.

Sequence modelling becomes eligible only if:

- tabular signal is stable;
- simple models survive SELECTION;
- microstructure dynamics clearly add value;
- enough historical input coverage exists;
- sequence model has a defined incremental question.

Potential later inputs:

- MBP-1 event sequences;
- trades + L1 quote sequences;
- MBO sequences only if sufficient history is acquired.

Potential architectures:

- TCN;
- LSTM/GRU;
- Transformer;
- state-space model.

Complexity must earn itself by beating simpler baselines.

---

# 57. MCP

Not V1.

First build a CLI/API.

Possible future commands:

```text
nqr exp list
nqr exp show EXP-0042
nqr exp compare EXP-0042 EXP-0043
nqr hypothesis show HYP-0017
nqr falsify EXP-0042
nqr lab compare
```

MCP may later wrap safe functions.

Future MCP should expose:

- read-only experiment queries;
- comparisons;
- interpretation summaries;
- fenced similar-state search;
- validated experiment execution.

Do not expose:

- raw HOLDOUT;
- arbitrary registry mutation;
- deletion;
- unrestricted SQL;
- ad hoc label/evaluation changes.

---

# 58. CLI Expectations

Eventually prefer reproducible CLI commands over notebooks.

Examples:

```bash
nqr data audit
nqr data normalize
nqr samples build --config config/sampling/volume_v1.yaml
nqr labels build --config config/labels/return_v1.yaml
nqr features build --config config/features/broad_v1.yaml
nqr exp register config/experiments/EXP-0001.yaml
nqr exp run EXP-0001
nqr exp show EXP-0001
nqr falsify EXP-0001
nqr mbo validate
nqr mbo ladder
```

Exact CLI framework is implementation detail.

---

# 59. Hardware / Performance

Design for local operation.

Expected priorities:

1. NVMe storage;
2. sufficient RAM;
3. CPU cores;
4. GPU later.

32 GB RAM should be sufficient for the derived research table if processing is streamed/batched.

64 GB preferred for comfortable feature generation and large joins.

Storage: target at least **1 TB free NVMe** before the full MBP-1 download; **2 TB preferred** because raw MBP-1 (~361 GB estimated), normalized data, features, MBO, caches, and experiment artifacts can coexist.

Do not load multi-hundred-GB raw MBP-1/MBO into RAM.

Processing pattern:

```text
read session
→ validate
→ derive needed state/features
→ write partitioned Parquet
→ release memory
```

Training occurs on derived sample datasets, not raw event files.

---

# 60. Milestone 0 — Data Audit

**Must happen before architecture code depends on assumptions.**

Deliverables:

1. exact trades coverage dates;
2. exact MBP-1 intended purchase dates;
3. exact MBO session list;
4. contiguous MBO block IDs;
5. side-field population report;
6. action/depth field report;
7. symbology report;
8. instrument-ID mapping;
9. timestamp semantics;
10. session coverage/gap report;
11. candidate DEV/SELECTION/HOLDOUT dates;
12. count of MBO sessions/blocks in each candidate partition;
13. documented reason MBO blocks were collected if known;
14. one-week MBP-1 sample audit PASS before full-history purchase;
15. verify `.v.0`/chosen continuous selector switches exactly as expected, occurs at a session boundary for the selected acquisition logic, and has no duplicate/multiple active switch within a roll;
16. storage capacity check before full download.

Definition of done:

- data assumptions are written into `docs/data-specification.md`;
- partition dates are frozen before feature research.

---

# 61. Milestone 1 — Foundation

Build:

- repository;
- `uv`;
- package layout;
- Pydantic configs;
- DuckDB registry;
- experiment states;
- CLAUDE.md;
- research protocol;
- data spec;
- experiment protocol;
- holdout policy;
- raw-data protections;
- holdout loader fence;
- audit logging;
- base tests.

Definition of done:

- empty test suite passes;
- holdout cannot be read by normal pipeline;
- experiment can be registered but no market feature exists yet.

---

# 62. Milestone 2 — MBP-1 Base Dataset

Start with one month.

Implement:

- raw reader;
- schema validation;
- session assignment;
- instrument handling;
- L1 state;
- mid/spread;
- trade reconciliation;
- QA artifacts;
- normalized Parquet.

Then scale to full two years.

Definition of done:

- one month manually/automatically validated;
- cross-source trade counts reconcile within defined tolerance;
- QA reports generated;
- roll/session/DST tests pass.

---

# 63. Milestone 2b — MBO Reconstruction Validation

Parallel engineering track.

Use selected MBO sessions.

Validate:

- L1 reconstruction against overlapping MBP-1;
- top-N reconstruction against vendor MBP-10 for a small purchased validation sample (**required**);
- execution reconciliation;
- order invariants.

Do not begin MBO feature research until reconstruction status is PASS.

---

# 64. Milestone 3 — Sample + Label Engine

Implement:

- sample table;
- volume clock;
- time clock control;
- event-clock interface only;
- volatility estimator;
- latency-aware labels;
- diagnostic labels;
- economic-cost config.

Definition of done:

- point-in-time tests pass;
- session/contract crossing impossible;
- target canary tests pass;
- label alignment reviewed by auditor.

---

# 65. Milestone 4 — Baselines

Implement all four baseline tiers.

Produce standard reporting:

- per-day metrics;
- monthly metrics;
- bootstrap CI;
- normalized target checks;
- calibration/diagnostics.

Definition of done:

- baseline report is generated from one command;
- no LightGBM yet required.

---

# 66. Milestone 5 — First LightGBM Research

Implement carefully limited feature set.

Register first hypothesis:

> price-response-to-signed-flow adds information beyond volatility/activity/price-only baselines.

Use DEV for exploration and SELECTION for registered comparison.

Run falsification battery on any promising candidate.

Definition of done:

- registered experiment;
- reproducible output;
- failed/null result acceptable;
- interpretation states what model appears to use.

---

# 67. Milestone 6 — Discovery / Hypothesis Extraction

Implement:

- SHAP interaction reporting;
- shallow rule extraction;
- optional RuleFit/stability selection only as Milestone 6b if SHAP + shallow trees are insufficient;
- numbered hypothesis registry;
- BH-FDR for batches.

Definition of done:

- at least one discovery can be converted into a frozen hypothesis and tested without modifying its rule.

---

# 68. Milestone 7 — MBO Lab

Create tiers on allowed MBO_LAB sessions.

Ensure:

- exact shared sample table;
- same labels;
- BROAD_LADDER excludes **all MBO_LAB sessions**;
- grouped/block CV;
- permutation controls.

Definition of done:

- T0/T1/T2 can be compared with paired block-level uncertainty.

---

# 69. Milestone 8 — Historical Depth Purchase Decision

Based on MBO ladder:

Decide whether more history is justified for:

- MBP-10;
- full MBO;
- neither.

Do not purchase because a feature is intuitively appealing.

Purchase consideration requires:

- consistent incremental predictive lift;
- information gain beyond permutation/capacity control;
- economic relevance;
- stability across blocks/time;
- no domination by a handful of sessions.

---

# 70. Milestone 9 — Freeze

Freeze:

- data pipeline;
- features;
- labels;
- sampling;
- volatility estimator;
- candidate hypotheses;
- model;
- hyperparameters;
- economic model;
- evaluation plan.

Commit `holdout_plan_01.md`.

No further tuning.

---

# 71. Milestone 10 — Holdout Opening #1

Execute only the frozen plan.

Evaluate:

- broad candidate(s);
- pre-registered metrics;
- frozen MBO ladder on HOLDOUT MBO days if applicable.

Do not alter code during evaluation except to fix a demonstrable execution bug, in which case the opening is considered contaminated and must be documented.

Report PASS / FAIL / INCONCLUSIVE.

A failed holdout is a valid project result.

---

# 72. Milestone 11 — Forward Evaluation

Continue collecting new data.

Apply frozen candidate prospectively.

No retrospective edits.

Forward performance eventually becomes the strongest evidence.

---

# 73. V1 Things Explicitly Deferred

Do not build these initially:

- CatBoost/XGBoost benchmarking;
- deep neural networks;
- sequence transformers;
- online RL;
- reinforcement learning;
- clustering as primary edge discovery;
- complex regime engine;
- dozens of target definitions;
- 1-second trading strategy;
- general-purpose backtester;
- MLflow server;
- MCP server;
- distributed cluster;
- cloud deployment;
- live trading/execution;
- strategy optimizer.

---

# 74. Edge Cases Checklist

Implementation must explicitly handle or test:

- no trades in a window;
- no quote update in a short window;
- zero/near-zero volatility denominator;
- spread widening;
- crossed/locked market;
- duplicate timestamps;
- multiple events at same nanosecond;
- out-of-order `ts_recv`;
- sequence gaps;
- vendor reset/snapshot messages;
- trading halt;
- shortened session;
- holiday;
- DST transition;
- session open;
- session close;
- contract roll;
- feature lookback crossing open;
- label horizon crossing close;
- feature window crossing data gap;
- unsigned trades;
- enormous trade-size outlier;
- extreme quote-size outlier;
- missing MBO block;
- corrupted session;
- partial raw download;
- stale/duplicate input file;
- schema version change;
- different symbology across datasets;
- instrument-ID mismatch;
- accidental holdout path inclusion;
- feature column silently changing dtype;
- training preprocessor seeing validation data;
- score threshold calculated from test data;
- duplicate samples across folds;
- overlapping label horizon across fold boundary;
- model seed/config mismatch;
- stale feature cache after code change;
- MBP-1 partial-packet state before F_LAST;
- `R` clear/reset/snapshot semantics at session/book initialization;
- implied/spread-leg or otherwise unsigned trades appearing on the outright with `side=None`;
- int64 vendor price scaling and tick conversion;
- America/Chicago RTH definition across DST while storage remains UTC;
- label horizon touching a partition boundary (partition boundaries are whole trading days, so such samples must be rejected);
- continuous-contract switch not occurring where expected;
- stateful counters not resetting on contract switch.

---

# 75. Definition of a Candidate Edge

A candidate is not an edge because:

- AUC > 0.5;
- one month is profitable;
- SHAP shows an intuitive feature;
- a cluster looks interesting;
- one threshold works;
- a chart looks convincing.

A candidate may progress only if it demonstrates:

1. incremental information beyond strong baselines;
2. chronological stability;
3. session/month dispersion;
4. reasonable robustness to sampling/latency;
5. no obvious leakage;
6. no single-session domination;
7. economic relevance after realistic costs;
8. understandable conditional behaviour or at minimum reproducible state definition;
9. survival through falsification;
10. eventual locked/forward confirmation.

---

# 76. Success Criteria for the Project

The project is successful even if the conclusion is:

> No economically meaningful and robust predictive edge was found.

Success means:

- trustworthy data;
- reproducible experiments;
- protection from leakage;
- honest trial accounting;
- valid statistical inference;
- ability to reject false ideas efficiently;
- clear evidence about whether MBP-10/MBO history is worth purchasing;
- a durable local research platform.

Finding an edge is an outcome, not a requirement for success.

---

# 77. Final Instruction to Claude / Claude Code

When reviewing or implementing this specification:

- challenge genuine methodological flaws;
- do not redesign architecture merely for elegance;
- prefer the simplest implementation that preserves scientific validity;
- surface assumptions explicitly;
- stop implementation when data validity is uncertain;
- never optimize around a failed holdout;
- never infer a trading edge from model performance alone;
- distinguish exploratory discovery from confirmatory evidence;
- preserve the ability to reconstruct exactly how every result was produced.

For the final pre-implementation spot-check, specifically look for:

1. leakage paths;
2. incorrect timestamp/as-of assumptions;
3. invalid MBO lab inference;
4. partition conflicts;
5. unnecessary multiple-testing surface;
6. economic-execution assumptions accidentally embedded in market labels;
7. ways dataset availability could leak calendar era;
8. contract-roll contamination;
9. places where the spec asks for more complexity than V1 needs;
10. any missing data-validation edge case that could materially invalidate results.

Do not expand V1 unless the issue is material to research validity.

This document is now the **V1.0 frozen implementation baseline**. Before coding, Claude Code should decompose it without changing scientific meaning into:

```text
CLAUDE.md
docs/research-protocol.md
docs/data-specification.md
docs/experiment-protocol.md
docs/holdout-policy.md
docs/architecture.md
```

Implementation should then begin with **Milestone 0**, not with ML.

---

# 78. V1.0 Freeze Validation Checklist

The following checks were performed during the final design review and are requirements for implementation:

- [x] Broad source upgraded from BBO-1s to two-year MBP-1.
- [x] Full purchase gated by a one-week MBP-1 QA sample.
- [x] Storage headroom specified.
- [x] Same-model-class/capacity-matched baselines required.
- [x] CME trading-day and America/Chicago RTH semantics defined.
- [x] ETH-to-RTH lookback policy explicit.
- [x] RTH-open volatility initialization explicitly governed and DEV-QA validated.
- [x] F_LAST-complete state required for features and labels.
- [x] Entry and horizon-end as-of rules pinned.
- [x] Integer-scaled/tick price handling specified.
- [x] Latency moved out of sample identity into label/evaluation version.
- [x] Volume-clock accumulator and trigger sequence defined.
- [x] MBO tier discovery vs ladder evaluation ambiguity resolved.
- [x] BROAD_LADDER excludes all MBO_LAB sessions.
- [x] Multi-draw permutation control required.
- [x] Vendor MBP-10 validation required for depth reconstruction.
- [x] Era/dataset identity features explicitly forbidden.
- [x] Continuous-contract and state-reset rules specified.
- [x] No automated feature selection in V1.
- [x] Robustness runs cannot become selection sweeps.
- [x] UMAP/HDBSCAN removed from V1.
- [x] RuleFit deferred.
- [x] MBO queue/re-entry research deferred to V2.
- [x] Falsification concentration tests clarified.
- [x] Partial-packet/reset/DST/partition edge cases added.
- [x] Holdout remains mechanically protected.
- [x] Prediction horizons remain 60 s and 5 min primary; 15 min secondary; 30 s diagnostic.
- [x] Project remains explicitly non-HFT despite use of sub-second backward-looking features.

## Freeze condition

Implementation may begin after Milestone 0 inputs are supplied. Any future change that alters scientific meaning must be recorded in `docs/protocol-amendments/` and increment the relevant spec/component version. Ordinary bug fixes that restore conformance to this spec do not constitute a research redesign, but must still be tested and logged.
