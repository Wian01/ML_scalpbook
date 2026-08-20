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
  sources.py    # MBP-1 source-provenance selection (registry-driven; QA-sample
                # vs canonical enumeration; require_provenance gate check)
  filenames.py  # vendor filename date parsing
  flags.py      # DBN flag bits (F_LAST etc.), UNDEF_PRICE sentinel
  dbnio.py      # read-only chunked DBN reading
  cli.py        # `nqr data audit` (parts incl. mbp1-acquisition,
                # mbp1-overlap-records), `nqr data storage-gate`
  calendar.py   # CME trading calendar (versioned committed snapshot,
                # config/data/cme_calendar.yaml; generator in scripts/)
  calendar_evidence.py  # PA-0001 date-level calendar evidence model:
                # committed matrix config/data/cme_calendar_evidence.yaml,
                # tier gating, hash-verified immutable evidence files,
                # observed cross-check vs coverage artifact (fail-closed);
                # plus the PA-0002 activation-resolution check, which
                # dispositions pending dates WITHOUT altering evidence
  eligibility.py  # PA-0002 research-eligibility quarantine mask:
                # config/data/research_eligibility.yaml (strict schema,
                # bound to the evidence-matrix SHA), session masking, no
                # window may cross a quarantined session, state reset at the
                # next eligible session, structural invariants (no boundary /
                # MBO session / block span / roll decision source). Session
                # IDs only — never raw paths; never consumed by rolls.py
  rolls.py      # front-contract/roll rule (volume-leading, monotone expiry)
  holdout.py    # fail-closed mechanical holdout fence (PENDING_INDEPENDENT_AUDIT)
  research.py   # THE research-loading API: mandatory date range + fence first
  qa_corpus.py  # explicitly QA-ONLY full-corpus enumeration (never research)
  rawguard.py   # raw-tree write refusal (path/alias/case/drive-relative resistant)
  experiments/  # models.py (§37 prereg + lifecycle states), registry.py
                # (DuckDB registry; hash-chained append-only audit; crash-safe
                # registration; immutable specs fail closed; §47 capture)
  qa/
    status.py cache.py storage.py manifest.py report.py
    mbp1_audit.py trades_audit.py reconcile.py mbo_inventory.py mbo_audit.py
    mbp1_acquisition.py  # acquisition validation, record-level overlap
                         # identity, cohesive acquisition/provenance gate
    full_history_audit.py  # closeout session-coverage audit (canonical corpus)
    closeout.py            # calendar-aware MBO block freeze + partition proposal
tests/unit/     # sessions (incl. DST + config), symbols/products, flags, MBO
                # blocks, status, filenames, config/paths, cache keys, storage
                # gate, manifest validation, git-sha, reconcile units
```

Audit caches (`<data_root>/qa/m0/cache/`) key on: source path relative to the
data root, vendor manifest SHA-256 plus size/mtime, a hash of the package
source tree, the effective configuration hash, and the audit parameters —
never filename+size alone.

**QA-vs-research loading:** QA/audit operations (acquisition validation,
coverage audits) enumerate the full canonical corpus through the explicitly
named QA-only API (`nqresearch.qa_corpus`); ordinary research/normalization
input MUST use `nqresearch.research` (explicit date range, mechanical holdout
fence invoked before enumeration, fail-closed while no active partition
configuration exists). An executable call-site allowlist test enforces that
no non-QA module touches the corpus enumerators.

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
<data_root>/reference/cme_calendar/ # immutable calendar evidence files (GCC
                                    # email, official CME exports/PDF, secondary
                                    # snapshots) — hash-bound by the committed
                                    # evidence matrix (PA-0001); never edited
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

0. **Data audit — COMPLETE** (closeout commit `3c7aee5e`, audit-log
   AL-0028): full-history coverage, provisional effective calendar, MBO
   blocks, causal roll rule, partition proposal (still PROPOSED_NOT_ACTIVE
   as the neutral source artifact). **Partitions were subsequently ACTIVATED
   for DEV/SELECTION only on 2026-08-20 (AL-0067) via
   `config/data/partitions_active.yaml`, published create-once from approved
   candidate `5d9fc036…` under human approval AL-0064; HOLDOUT and FORWARD
   remain mechanically sealed and no normalization has begun.**
1. **Foundation — implemented, `PENDING_INDEPENDENT_AUDIT`**: DuckDB
   experiment registry with immutable §37 lifecycle (`nqr exp
   register/show/list/transition`; per-experiment committed record dirs;
   append-only lifecycle audit; §47 reproducibility capture); fail-closed
   mechanical holdout fence (`nqresearch/holdout.py` — DEV/SELECTION active
   since AL-0067, every HOLDOUT-touching or out-of-range request refused; no
   override path exists);
   raw-write guard (`nqresearch/rawguard.py`, enforced in artifact/cache
   writers). The holdout fence is builder work only and must pass a
   fresh-session adversarial audit before Milestone 1 is certified.
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
