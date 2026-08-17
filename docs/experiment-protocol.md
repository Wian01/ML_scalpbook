# Experiment Protocol (V1)

Derived from [canonical-spec-v1.0.md](canonical-spec-v1.0.md) (authoritative;
§-references point into it).

## 1. Pre-registration (§37)

Experiment states are immutable: `PLANNED → RUNNING → PASSED | FAILED | INCONCLUSIVE |
SUSPECT_AUDIT_REQUIRED`. Before a registered run, store: experiment ID, creation
timestamp, research question, hypothesis, dataset version, partition, sample-table
version, feature-family versions/hashes, label version, volatility-estimator version,
horizon, latency, fold scheme, seeds, model type, hyperparameters, primary metric,
secondary metrics, acceptance criterion, kill criteria, cost-model version.

Once execution begins the registered specification is immutable. A new idea after
seeing results is a new experiment. Hypotheses are never rewritten retrospectively.

## 2. Registry (§38)

Initial implementation: DuckDB plus one directory per experiment:

```text
experiments/EXP-nnnn/
  prereg.yaml  config.yaml  metrics.json  daily_metrics.parquet
  predictions.parquet  plots/  notes.md  audit.json
```

The registry stores Git commit, dependency-lock hash, source dataset hashes, outputs,
status, parent experiment/hypothesis, and notes. MLflow is not required in V1; metadata
is designed so it can be added later without redesign.

## 3. Multiple-testing controls (§39)

From day one: experiment registration; trial counter; failed-run retention; immutable
hypotheses; fixed primary metric, horizons, and model family; holdout protection;
BH-FDR for batches of mined hypotheses; no silent hyperparameter sweeps — every
hyperparameter configuration counts as a trial. Finalist-stage options: Deflated Sharpe
Ratio, PBO, CPCV. White's Reality Check / SPA not required in V1.

## 4. Hypotheses (§33)

Mined discoveries become numbered hypotheses (`HYP-nnnn`) specifying exact feature
conditions, target, horizon, population, direction, primary metric, and kill criterion,
tested in SELECTION without modification. If K hypotheses are mined together, K is
recorded and the pre-specified correction applied.

## 5. Falsification battery (§35)

One commandable battery; required tests: shifted-label; permuted-label; feature
temporal shift; leakage audit; adjacent-window sensitivity; latency sensitivity
(250/500/1000 ms); sample-volume sensitivity (N/2, N, 2N); evaluation jackknife over
stored predictions (no refit); drop-five-best-sessions concentration stress;
month-drop sensitivity; volatility-tercile split; scheduled-event-day exclusion;
roll-week exclusion; +1 and +2 tick transaction costs; feature-family ablation;
price-only and broad-model baseline comparisons. No candidate survives merely because
the central configuration works.

## 6. "Too good" alarm (§36)

Configurable heuristics (V1 defaults: directional AUC > ~0.58 at ≥60 s; top-5% net
expectancy > ~3 ticks at 60 s; positive-day proportion > ~80%; skill > 3× running best;
metric > 3 SD from registry history) set `SUSPECT_AUDIT_REQUIRED`. Before any
interpretation: timestamp audit, label-alignment audit, feature source-time audit,
shift and permutation tests, feature removal, session concentration, contract/roll
check, train/test overlap check, duplicate-row check.

## 7. Leakage canaries (§52)

Deliberately impossible tests must behave correctly: permuted targets → no skill;
intentionally shifted future targets → detected; a future-derived canary feature →
rejected by source-time validation before training; random noise features → no stable
lift. Any failure blocks research until fixed.

## 8. Scheduled macro events (§40)

Maintain an external calendar (FOMC, CPI, NFP, PPI, GDP, selected Fed events). V1 uses
it for stratification/robustness reporting only — never as broad predictive features.
Report all-sessions / event-sessions / non-event-sessions; state explicitly when a few
event sessions dominate performance.

## 9. Research journal (§42)

Every experiment, including failures, gets a permanent human-readable note using the
template: QUESTION / HYPOTHESIS / WHY THIS TEST / DATA-PARTITION / PRIMARY METRIC /
KILL CRITERIA / RESULT / STABILITY / FALSIFICATION / INTERPRETATION / DECISION /
NEXT QUESTION. The project must make it easier to remember failures than to forget them.

## 10. Reproducibility (§47)

Every run captures Git SHA, Python version, OS/platform, dependency-lock hash, dataset
version/hash, config hash, random seeds, and experiment ID. Deterministic mode where
practical; residual nondeterminism documented.

## 11. Builder/auditor workflow (§44)

Sensitive code (features, labels, sampling, evaluation, holdout, MBO reconstruction) is
implemented in a builder session and adversarially audited in a fresh auditor session
(assume leakage/timestamp/alignment/statistical errors exist; attempt to falsify
correctness) using the reusable prompts in `prompts/`. Sampling, label, partition,
evaluation, holdout, or MBO reconstruction changes additionally require human review.
