# Architecture (V1)

Derived from [canonical-spec-v1.0.md](canonical-spec-v1.0.md) §45–§49, §57–§74
(authoritative).

## 1. Repository layout (§45)

Target layout per canonical §45 (`config/`, `data/`, `src/nqresearch/` with
ingest/normalize/qa/sessions/sampling/features/labels/volatility/models/experiments/
evaluation/discovery/falsification/economics/mbo/reporting, `tests/` with
unit/property/integration/leakage, `experiments/`, `reports/`, `prompts/`,
`notebooks/`). Directories are created as milestones need them, not speculatively.
Notebooks are exploratory only; production research logic lives in tested modules.

Currently implemented (Milestone 0 scope):

```text
config/data/
  paths.yaml    # data_root (overridable via NQR_DATA_ROOT) + storage-gate thresholds
  sessions.yaml # session boundary 17:00 CT, RTH 08:30-15:00 CT (config, not code)
src/nqresearch/
  config.py     # pydantic config models + YAML loading
  paths.py      # repo root + configurable data-root resolution
  sessions.py   # CME trading-day + RTH assignment (scalar reference + polars
                # vectorized), driven by SessionWindowConfig
  symbols.py    # NQ outright/spread classification; generic product roots;
                # NQ-research classification over mixed-product files
  filenames.py  # vendor filename date parsing
  flags.py      # DBN flag bits (F_LAST etc.), UNDEF_PRICE sentinel
  dbnio.py      # read-only chunked DBN reading
  cli.py        # `nqr data audit`, `nqr data storage-gate`
  qa/
    status.py cache.py storage.py manifest.py report.py
    mbp1_audit.py trades_audit.py reconcile.py mbo_inventory.py mbo_audit.py
tests/unit/     # sessions (incl. DST + config), symbols/products, flags, MBO
                # blocks, status, filenames, config/paths, cache keys, storage
                # gate, manifest validation, git-sha, reconcile units
```

Audit caches (`<data_root>/qa/m0/cache/`) key on: source path relative to the
data root, vendor manifest SHA-256 plus size/mtime, a hash of the package
source tree, the effective configuration hash, and the audit parameters —
never filename+size alone.

## 2. Stack (§46)

Python 3.12 via `uv` (lock file committed); Parquet/PyArrow/Polars/DuckDB for data;
Pydantic + YAML for config; scikit-learn + LightGBM for V1 ML (LightGBM is the only
GBDT family); pytest + Hypothesis for tests. PyTorch only if later justified. No
MLflow/MCP/distributed compute in V1 (§57, §73).

## 3. Data directories and immutability (§11)

The data tree root is **configurable** (`config/data/paths.yaml` `data_root`,
overridden by `NQR_DATA_ROOT`) and lives on a dedicated NVMe volume —
**currently `D:/nq-research/data`** (migrated 2026-08-17, audit-log AL-0019).
The storage gate (`nqr data storage-gate`) measures free space on that volume.

```text
<data_root>/raw/{trades,mbp1,mbo}   # immutable vendor data, read-only, never in Git
<data_root>/normalized/  qa/  samples/  features/  labels/  datasets/  holdout/
```

### 3a. Physical storage policy (C: repo vs D: data volume)

Stored on the **D: data volume under `<data_root>`** — everything large or
regenerable: raw vendor data; normalized data; QA artifacts and audit caches;
samples; features; labels; datasets and holdout data; large model binaries;
predictions; SHAP/interpretation caches; temporary processing files; and other
large or regeneratable experiment artifacts. Components not yet implemented
(normalized/samples/features/labels/datasets/holdout, model stores,
prediction/SHAP outputs) follow this policy when they are built — the policy
is documented now; the modules are not built prematurely.

Kept in the **Git repository on C:** — source code; configuration; tests;
documentation; protocol amendments; and lightweight experiment definitions,
registry records, metrics, audit metadata, and compact final reports
(`experiments/EXP-nnnn/` per canonical §38, with its large
predictions/plots artifacts redirected to the data volume when Milestone 1+
implements the registry).

The root-anchored `/data/` rule in `.gitignore` is retained permanently even
though the active tree is on D: — it is a safety measure so a repo-local
`data/` directory (e.g. a stray copy) can never be committed.

**Mapping note vs the frozen spec:** canonical §45 draws `data/` inside the
repository layout and §7 writes `data/holdout/`. The frozen spec is unchanged;
this section records the operational mapping of that logical tree onto the
configured `<data_root>` volume (consistent with §59's NVMe-first processing
model). Logical structure, immutability, and QA rules are identical; only the
physical location is remapped via committed configuration.

Raw data is never edited, normalized in place, deleted, rewritten, or silently
repaired. Every derived artifact is reproducible from raw input + code version +
config + dependency versions. The entire `data/` tree is gitignored.

## 4. Processing model (§59)

Local workstation; NVMe > RAM > CPU > GPU priority. Stream/batch per session:
`read session → validate → derive → write partitioned Parquet → release memory`.
Never load multi-hundred-GB raw files into RAM; training uses derived sample datasets.
Storage target before the full MBP-1 purchase: ≥ 1 TB free NVMe, 2 TB preferred.

## 5. QA layer (§12, §13, §50, §51)

Every dataset needs a persistent machine-readable QA artifact (PASS/WARN/FAIL) before
research use; exclusions carry machine-readable reason codes from the allowed list
(§50); forbidden exclusions (bad P&L day, "unusual market", post-hoc outliers) are
never applied. Cross-source reconciliation (trades vs MBP-1-derived trades) stops the
pipeline above tolerance (§13). Missing data is never silently forward-filled across
contract switches, sessions, or long gaps (§51). Milestone 0 artifacts live in
`<data_root>/qa/m0/` (see [data-specification.md](data-specification.md)).

## 6. Feature/label registries (§48, §49)

Every feature family and label carries versioned YAML metadata (sources, lookback,
as-of policy, session/contract crossing, normalization; labels add horizon, latency_ms,
price source, volatility version, clip). No ad hoc notebook labels. The registry
supports automated leakage tests.

## 7. CLI (§58)

Reproducible CLI over notebooks. Implemented: `nqr data audit [--part mbp1|trades|mbo|reconcile|all]`.
Planned per canonical §58: `nqr data normalize`, `nqr samples build`, `nqr labels build`,
`nqr features build`, `nqr exp register/run/show`, `nqr falsify`, `nqr mbo validate/ladder`.

## 8. Milestones (§60–§72)

0. **Data audit** (in progress) — coverage, schema/semantics, session lists, block IDs,
   candidate partitions, one-week+ MBP-1 sample PASS before full purchase, storage check.
1. Foundation — configs, DuckDB registry, holdout fence, audit logging, base tests.
2. MBP-1 base dataset (one month first, then two years); 2b MBO reconstruction
   validation (vendor MBP-10 sample required).
3. Sample + label engine (volume clock, time clock, volatility, latency-aware labels).
4. Baselines (B0–B3, standard reporting).
5. First LightGBM research (registered; null result acceptable).
6. Discovery/hypothesis extraction (SHAP, shallow rules, BH-FDR).
7. MBO lab ladder (T0/T1/T2, permutation controls).
8. Historical depth purchase decision.
9. Freeze + `holdout_plan_01.md`.
10. Holdout opening #1 (frozen plan only).
11. Forward evaluation.

## 9. Edge-case obligations (§74)

The implementation must explicitly handle or test the full §74 checklist (empty
windows, zero-volatility floors, crossed/locked books, duplicate nanoseconds, sequence
gaps/resets, halts, shortened sessions, holidays, DST, session open/close, rolls,
partition-boundary label horizons, F_LAST partial packets, `R` reset semantics,
int64 price scaling, stale caches, fold overlaps, etc.). Tests accumulate against this
list as the relevant components are built.
