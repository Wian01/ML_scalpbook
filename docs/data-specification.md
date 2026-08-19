# Data Specification (V1)

Derived from [canonical-spec-v1.0.md](canonical-spec-v1.0.md) §2, §8–§13, §50–§52, §74
(authoritative) plus **observed Milestone 0 facts** from the local audit
(machine-readable artifacts: `<data_root>/qa/m0/*.json`).

## 1. Data assets (observed inventory, 2026-08-17)

All datasets are Databento `GLBX.MDP3` DBN v-encoded, zstd-compressed daily files,
purchased with **parent symbology** (`stype_in=parent`, `stype_out=instrument_id`).
Trades and MBP-1 queried `["NQ.FUT"]`; 30 of 31 MBO jobs queried `["NQ.FUT"]` and
one (`GLBX-20260508-RV5ECMAN6F`, 2026-05-04 → 05-07) queried
`["NQ.FUT","ES.FUT"]` — **the ES data in that job is expected and is not an
error**; mixed raw files are preserved unchanged, products are identified via
instrument mappings, and ES records plus NQ calendar spreads are excluded from
NQ research with exclusions recorded in QA metadata. Files contain **all
children of the queried parents: outright futures and calendar spreads**.
`pretty_px=false` (int64 1e-9 prices), `split_duration=day` (UTC-day file splits).

The data tree root is configurable: `config/data/paths.yaml` (`data_root`),
overridden by the `NQR_DATA_ROOT` environment variable. **Since 2026-08-17 the
canonical active data root is `D:/nq-research/data`** on the dedicated D: NVMe
volume (migration validated file-for-file and by full manifest SHA-256
re-verification; audit-log AL-0019). All paths below are relative to that
root. The free-space purchase gate is repeatable via `nqr data storage-gate`
and re-measures whatever volume the configured data root resides on.

| Dataset | Location (immutable) | Coverage (UTC file dates) | Files | Compressed |
|---|---|---|---|---|
| Trades (2 jobs) | `<data_root>/raw/trades/NQ_20240809-20250809`, `NQ_20250809-20260809` | 2024-08-09 → 2026-08-07 | 624 | ~3.03 GB |
| MBP-1 sample (1 job) — **MILESTONE0_QA_SAMPLE, research_eligible=false** | `<data_root>/raw/mbp1/2026-08-03_2026-08-15/GLBX-20260817-N8HD86YKNS` | 2026-08-03 → 2026-08-14 | 11 | ~2.26 GB |
| **MBP-1 annual (older) — FULL_HISTORY_CANONICAL** | `<data_root>/raw/mbp1/2024-08-17_2025-08-17/GLBX-20260817-P3KX4KXDQF` | query [2024-08-17, 2025-08-17); files 2024-08-18 → 2025-08-15 | 312 | ~44.69 GB |
| **MBP-1 annual (recent) — FULL_HISTORY_CANONICAL** | `<data_root>/raw/mbp1/2025-08-17_2026-08-17/GLBX-20260817-S9GCQWS6L8` | query [2025-08-17, 2026-08-17); files 2025-08-17 → 2026-08-16 | 313 | ~68.84 GB |
| MBO (31 jobs) | `<data_root>/raw/mbo/GLBX-*` | 85 files (post re-download), 2025-08-18 → 2026-08-07 | 85 | ~36.2 GB |

Every job directory carries vendor `metadata.json`, `condition.json` (all MBP-1
sample days: "available"), and `manifest.json` (SHA-256 per file). **Manifest
validation** (part of the audit; artifact `manifest_validation.json`) verifies
presence, exact size, and SHA-256 of every manifested file and flags data
directories lacking a manifest: **34/34 job directories, 788/788 files PASS,
zero failures, zero missing manifests, zero unmanifested DBN files.** (Three MBO
jobs were originally downloaded incomplete and were re-downloaded and
re-validated on 2026-08-17 — history in
[implementation-audit-log.md](implementation-audit-log.md) AL-0008/AL-0012/AL-0013.)
The MBP-1 sample is **two weeks**, a superset of the one-week gate sample
required by canonical §2.2.

Notes:

- The trades history is contiguous across the two jobs (batch 1 ends Fri 2026-08-08
  boundary at 2025-08-09 00:00 UTC — a Saturday; batch 2 resumes Sun 2025-08-10).
- MBP-1 sample has no 2026-08-08 file (Saturday) and a small 2026-08-09 file
  (Sunday: pre-open + 17:00 CT evening open only). This is expected, not a gap.
- MBP-1 ↔ trades reconciliation overlap: UTC dates 2026-08-03 → 2026-08-07.

## 1a. Full-history MBP-1 acquisition and source provenance (2026-08-18)

**The two-year MBP-1 purchase is complete.** The two annual jobs above are the
**canonical research corpus**: 625 daily DBN files covering exactly adjacent
query ranges [2024-08-17, 2025-08-17) + [2025-08-17, 2026-08-17) with no gap
and no overlap (~113.5 GB compressed). Vendor query parameters match the
sample and the frozen spec: `GLBX.MDP3`, `mbp-1`, `NQ.FUT` parent →
`instrument_id`, DBN + zstd, daily splits, `pretty_px/pretty_ts/map_symbols/
split_symbols = false`. Because acquisition is parent-symbology, the corpus
contains outright futures **and** calendar spreads plus contract expirations —
downstream outright/spread classification remains mandatory (§2).

**Source provenance is registry-driven** (`config/data/mbp1_sources.yaml`,
part of the effective configuration hash; selection code in
`nqresearch.sources`):

- Both annual jobs: `FULL_HISTORY_CANONICAL`, `research_eligible: true`.
- The two-week job: `MILESTONE0_QA_SAMPLE`, `research_eligible: false` —
  retained solely to reproduce the original Milestone 0 QA artifacts. Its 11
  daily files (2026-08-03 → 2026-08-14) are fully contained in the recent
  annual job and were verified **content-identical at the decoded-record
  level: all 115,583,040 records byte-compared across all 11 day-pairs,
  identical** (artifact `mbp1_sample_overlap_record_level`). An important
  observed fact: **file-level vendor SHA-256 CANNOT establish cross-request
  identity** — each Databento batch file embeds per-request container
  metadata, so the same market day differs by 2–9 bytes between jobs (both
  copies hash-match their own manifests; parsed DBN metadata and all records
  are equal). The file-hash comparison is therefore an explained WARN and the
  record-level comparison is the authoritative identity gate. The recent
  annual job is canonical for those dates. **The sample must never be
  combined with the annual corpus for training.**
- Enumeration rules: the Milestone 0 sample audit selects only the QA sample;
  research/normalization input enumerates only canonical sources; each logical
  daily partition may appear exactly once; an overlap between two
  research-eligible sources fails loudly. Deduplication is source-level only —
  row-level/heuristic dedup is forbidden (legitimate messages can be
  identical).

**Vendor condition flags: 11 "degraded" dates across the annual jobs.** The
older job marks 1 date degraded (2024-09-18, file present; 311 available).
The recent job marks 10 (2025-09-17, 2025-09-24, 2025-11-28, 2026-01-31*,
2026-03-15, 2026-03-16, 2026-03-21*, 2026-04-10, 2026-05-24, 2026-07-30;
* = Saturdays with no file). Files exist for all non-Saturday degraded dates;
the flags make the source inventory **WARN** (understood, non-blocking) and
are recorded for session-QA classification in Milestone 2, not silently
excluded. (An earlier summary wrongly reported the older job fully
"available" — corrected in audit-log AL-0021; AL-0020 preserved as written.)

**Acquisition QA artifacts** (never overwriting the historical
`<data_root>/qa/m0/` set): `<data_root>/qa/mbp1_full_history/` —
`mbp1_source_inventory`, `mbp1_manifest_validation`, `mbp1_range_adjacency`,
`mbp1_sample_overlap`, `mbp1_source_selection`, `storage_gate` (results: §5.6).

## 2. Symbology and instrument handling (§8; observed)

**Deviation from the planning assumption:** the spec discussed acquiring via a
continuous selector (`NQ.v.0`). The data as purchased instead uses **parent
symbology**, which is spec-acceptable (instrument_id is preserved; §8 requires joins
on `instrument_id`, never display symbol) but changes two things:

1. Milestone 0 item 15 ("verify `.v.0` switches exactly as expected") is **not
   applicable**; there is no vendor continuous selector in the data. The front/roll
   determination must be defined by us (e.g. volume-leading outright per session) and
   verified against observed per-contract volumes. This is recorded as an open
   protocol clarification for the partition/roll design in Milestone 2.
2. Every file contains outrights **and** calendar spreads. Spread instruments are
   identified from the raw symbol (legs joined by `-`, e.g. `NQM7-NQU7`) via
   `nqresearch.symbols.classify_symbol`. Spread and outright records must be
   explicitly separated in normalization; spread trades must never contaminate
   outright flow features.

Instrument-ID → raw-symbol mappings are embedded per file in DBN metadata (dated
intervals). The audit verifies every observed `instrument_id` maps to exactly one
symbol per file. Continuous research price series must never be back-adjusted;
features/labels never cross an instrument switch (§8).

## 3. Timestamp semantics (§9; observed)

- Canonical research chronology: `ts_event` (exchange event time), UTC nanoseconds.
  `ts_recv` retained for QA/latency diagnostics only.
- `session_id` = CME trading day (starts 17:00 America/Chicago). V1 RTH =
  08:30–15:00 America/Chicago, configured not hardcoded. Implemented in
  `nqresearch.sessions` with a scalar reference implementation and a vectorized
  polars implementation, cross-checked by tests including DST transitions.
- Vendor daily files split at **UTC midnight**, so one CME session spans two UTC
  files (Sunday evening opens live in the Sunday file, session dated Monday).
  Normalization (Milestone 2) must reassemble sessions across file boundaries.
- Prices are int64 at 1e-9 scale (NQ tick 0.25 = 250,000,000 units); undefined
  price sentinel is int64 max. Prices remain integer internally (§17).

## 4. QA layer rules (§12, §13, §50, §51)

- Persistent machine-readable QA artifact (PASS/WARN/FAIL) required before research
  use; only PASS or explicitly approved WARN sessions are usable.
- Exclusions only from the allowed list (vendor-corrupt session, unrecoverable gap,
  invalid reconstruction, missing coverage, contract-boundary crossings, predefined
  holiday/partial-session rules) with machine-readable reason codes. Forbidden:
  excluding on P&L, "unusual market", post-hoc outliers, or event days that hurt
  results.
- Cross-source reconciliation (standalone trades vs MBP-1-extracted trades) must stop
  the pipeline above tolerance. Both sources share one vendor/feed: reconciliation
  validates completeness/parsing/interpretation, not independent market truth.
- Never silently forward-fill across contract switches, sessions, or long gaps.
  Missingness indicators only when the missingness is a real-time observable.

## 5. Milestone 0 audit results (observed)

> Artifacts: `<data_root>/qa/m0/mbp1_sample_audit.json`, `trades_audit.json`,
> `mbo_inventory.json`, `mbp1_trades_reconciliation.json`. Summarized below.

### 5.1 MBP-1 two-week sample — status **WARN** (all findings understood or benign)

Scope: 11 daily files, 2026-08-03 → 2026-08-14 (no Saturday file; 2026-08-09 is the
small Sunday pre-open/evening file). **115,583,040 records**, 3,509,458 trade events,
4,824,654 contracts. Front outright throughout: NQU6.

**PASS findings**

- Schema `mbp-1`, `stype_out=instrument_id`, `rtype=1`, `publisher_id=1` uniformly.
- Every observed `instrument_id` maps to exactly one raw symbol via embedded DBN
  metadata; per file 5 outrights + 5 calendar spreads, no "other" symbols, no
  unmapped IDs. Spread records are a small minority but include trades
  (e.g. NQU6-NQZ6: 319 trades on 2026-08-06) — outright/spread separation is mandatory.
- Actions observed: only `A/C/M/T` (+ none unexpected); `depth=0` everywhere;
  sides only `A/B/N`. Trade-event side coverage: A=1,750,907, B=1,758,532,
  **N=19 of 3.5M (~0.0005%)** — matches the standalone trades dataset.
- `F_LAST` present on 96.96% of records (≈1.03 records/packet); flags contain no
  unknown bits; no `F_SNAPSHOT`/`F_BAD_TS_RECV`/`F_MAYBE_BAD_BOOK` seen in the sample.
- `ts_recv >= ts_event` on every row; `ts_in_delta` never negative.
- All outright spreads are exact multiples of the 0.25 tick.
- Front-outright RTH quote coverage is dense: max intra-RTH quote gap per session
  0.7–2.1 s across the two weeks.
- Sequence numbers advance monotonically apart from the initialization records below.

**WARN findings (explained, carried as normalization obligations)**

1. `ts_event` non-monotonic 5–7 times per weekday file, magnitudes up to ~52 h —
   **all located at file rows ~2–6**: Databento writes each instrument's last-known
   book state at file start, stamped with the original quote time (stale for
   back-month contracts). Sequence "backward moves" coincide with these rows.
   Obligation: normalization must recognize file-leading initialization records and
   exclude them from event chronology; genuine mid-stream disorder was **zero**.
2. Crossed outright books on **637 F_LAST-complete states** total (0–346/day;
   locked books ≤6/day). Timing diagnostic: bursts at 15:15:00 CT (equity-futures
   close/halt boundary), in 16:xx CT maintenance/pre-open windows, Sunday pre-open,
   and one 341-row burst at 11:31:58 CT on 2026-08-10 (consistent with a
   volatility-halt/auction indicative state; **cause not provable from MBP-1 alone**).
   Obligation: session-phase classification (plus, if needed, vendor `status` schema
   data) must flag halt/auction/pre-open states; crossed/locked states must be
   excluded from mid-price computation rather than deleted.

### 5.1.1 Two-year MBP-1 purchase considerations

The sample's UTC-day file splits mean one CME session spans two files; sessions must
be reassembled in normalization. August 2026 daily compressed sizes were 161–342 MB
(weekday mean ≈ 243 MB), i.e. seasonal/vol-regime dependence makes any two-year
extrapolation a wide-uncertainty estimate.

### 5.2 Trades dataset — status **WARN** (benign; see below)

- 624 daily files, 2024-08-09 → 2026-08-07; **195,621,134 trade records**,
  285,004,515 contracts total volume (all NQ children).
- **Aggressor side population is excellent:** `side=N` (unsigned) on 891 rows =
  **0.0005%** overall. By segment: RTH 60/145,036,369 (≈0%), ETH 831/50,584,765
  (0.0016%); outrights 789/194,371,903 (0.00041%), spreads/other 102/1,249,231
  (0.0082%). Worst single days are ~0.07% and are all tiny Sunday-evening
  sessions. Aggressor balance: A (sell) 97,955,833 vs B (buy) 97,664,410.
  Unsigned trades are retained as unsigned per §2.1 — never dropped silently.
  No correlation analysis with "unusual conditions" is warranted at this
  incidence; the residual unsigned rows cluster in illiquid ETH periods.
- `action == "T"` on every row of every file; `depth == 0` on every row;
  `ts_event` monotonic non-decreasing within every file; no backward sequence
  moves flagged.
- Coverage: the only missing weekday in two years is **2025-04-18 (Good
  Friday — CME holiday)**. *(Pre-closeout history: the WARN reflected the
  then-missing machine calendar; the effective calendar has since been
  integrated — §6a — and classifies Good Friday as a pre-RTH short session.)*
  Effective coverage is complete.

### 5.3 MBP-1 vs trades reconciliation — status **PASS (exact)**

Two granularities, both exact:

- **UTC-day (vendor file granularity):** all 5 overlap days (2026-08-03 →
  2026-08-07) reconcile exactly per instrument between trades extracted from
  MBP-1 (`action=T`) and the standalone trades files — trade count, total
  volume, side counts (A/B/N), min/max price, first/last `ts_event` all
  identical (376,215 / 437,601 / 416,702 / 410,027 / 382,522 trades per day;
  zero mismatches).
- **CME-session (sessions reassembled across UTC file boundaries):** the four
  sessions whose full 17:00→17:00 CT window lies inside the common file set of
  both sources (2026-08-04 → 2026-08-07) match exactly on all 19
  (session, instrument) pairs — 1,653,678 trades on each side. Session
  2026-08-03 is excluded as incomplete: its Sunday-evening portion predates the
  MBP-1 sample window. Session-level reconciliation will re-run over full
  coverage once sessions are reassembled in Milestone 2 normalization.

This validates download completeness, parsing, and trade-event interpretation
across schemas and across the UTC file split. Reminder: both sources share one
vendor/feed — this is not independent market evidence (§2.2/§13).

### 5.4 MBO inventory and blocks — **PROVISIONAL**

Two artifacts:

- `mbo_inventory.json` (**provisional, filename-derived**): 31 batch jobs, 80
  session files, 80 unique file dates, no duplicates, ~31.9 GB compressed,
  spanning 2025-08-18 → 2026-08-07; 30 provisional blocks `MBO-BLK-001` …
  `MBO-BLK-030`. Differences vs canonical §2.3's approximate ranges: the
  2026-05 block is 2026-05-04 → 2026-05-08 (5 sessions), larger than the
  spec's "2026-05-08"; nothing exists after 2026-08-07.
- `mbo_deep_audit.json` (**authoritative for NQ coverage**): decodes every MBO
  file; computes actual first/last `ts_event`, per-CME-session row counts, and
  RTH span coverage from **NQ outright records only** (products identified via
  instrument mappings). ES records — expected in the mixed 2026-05 job
  `GLBX-20260508-RV5ECMAN6F`, which queried `NQ.FUT+ES.FUT` — and NQ calendar
  spreads are excluded from NQ research coverage, with per-file excluded
  counts recorded under `excluded_from_nq_research`. The NQ session inventory
  and provisional blocks derive from sessions with ≥95% decoded NQ-outright
  RTH span coverage AND ≥100k NQ-outright RTH rows (thresholds are recorded QA
  classification parameters; ordinary sessions decode to millions of rows,
  while file-start initialization records with stale timestamps produce
  "ghost" dates of 37–2,000 rows that must not count as sessions).

**Deep-audit results (repaired data, 2026-08-17: decoded 2,005,045,979 records
across all 85 files):**

- **NQ MBO session inventory (pre-closeout): 76 full-RTH sessions in 31
  provisional blocks**, plus **1 partial session**: 2026-07-03 (54% RTH span —
  Independence Day half-session; *since reclassified COMPLETE_SHORTENED under
  the effective calendar — current inventory is 77 sessions / 30 blocks,
  §6a*). 106 additional dates observed in
  decoded timestamps are initialization artifacts, not sessions (listed in the
  artifact).
- **Change vs the pre-repair result (70 full + 3 partial, 30 blocks):** the
  earlier "partial vendor coverage" sessions 2025-10-09 (45% span) and
  2025-11-05 (39% span) were artifacts of **incomplete downloads** — after the
  re-download both are full sessions, and five previously missing files added
  sessions 2025-10-10, 2025-10-13, 2025-11-06, and 2025-11-07 (plus a Sunday
  file). Blocks `2025-10-09→10-13` (3 sessions) and `2025-10-30→11-07`
  (7 sessions) are now complete, shifting subsequent block IDs (31 total).
  History: [implementation-audit-log.md](implementation-audit-log.md)
  AL-0011/AL-0012/AL-0013/AL-0016.
- The 85 file dates ≠ 77 sessions because Sunday files contain only
  evening/pre-open data belonging to Monday sessions (no RTH of their own).
  The filename-derived inventory and canonical §2.3 ranges are superseded by
  this decoded inventory.
- **Products:** 4 files (job `GLBX-20260508-RV5ECMAN6F`, 2026-05-04 → 05-07)
  contain ES children — 56,819,215 ES rows excluded from NQ research, plus
  4,952,807 NQ calendar-spread rows across all files, all recorded per file in
  QA metadata. Every observed instrument maps to a symbol; every file has NQ
  outright data.
- *(Pre-closeout history, superseded by §6a:)* block contiguity originally
  used a weekday-only rule pending the calendar; the closeout recomputed
  blocks under the versioned effective calendar (2026-07-03 reclassified a
  COMPLETE shortened session → **77 sessions / 30 blocks**, state
  PROVISIONAL_DOCUMENT_VERIFICATION_PENDING). Current state: §6a and
  AL-0028.
- **Unresolved:** the reason each block was acquired is not documented in the data
  directories; per canonical §30 this must be supplied by the researcher.
  *(Pre-closeout history: the MBO_LAB selection-bias comparison
  (volatility/volume/event-day distribution vs the broad population) was
  deferred because the two-year MBP-1 history did not yet exist. The full
  canonical corpus now exists; the comparison remains pending for
  Milestone 2+ — §7 item 6.)*

### 5.5 Storage check (§2.2, §59; Milestone 0 item 16) — current: **WARN** (≥1 TB met)

- Repeatable gate: `nqr data storage-gate` measures the volume holding the
  configured data root (artifact `storage_gate.json`).
- **Current (2026-08-18, post-closeout re-measure): 1,720.9 GB free of
  2,048 GB — WARN**: the 1,000 GB required minimum is met; the 2,000 GB
  preferred headroom is not (acceptable per policy since ≥1 TB remains free;
  a separate non-project directory also occupies space on D:).
- History (preserved): C:-volume runs measured 263.2–284.6 GB (FAIL) and
  correctly blocked the purchase; after migration to `D:/nq-research/data`
  (2026-08-17) the pre-purchase gate read 2,005.5 GB (PASS); the two-year
  purchase (~113.5 GB compressed) then consumed the difference. The sample's
  ~122 GB compressed extrapolation was accurate (actual: 113.5 GB).

### 5.6 Post-purchase acquisition validation (2026-08-18; `<data_root>/qa/mbp1_full_history/`)

| Artifact | Status | Result |
|---|---|---|
| mbp1_source_inventory | WARN (understood) | All three jobs match registry + spec expectations (request IDs, placement, dataset/schema/symbology, encoding, splits, integer prices, ranges, manifest.json SHA-256 vs registry); WARN reflects the 11 vendor-degraded condition dates pending Milestone 2 session QA |
| mbp1_manifest_validation | PASS | 642/642 manifested files re-hashed (314 + 315 + 13 incl. QA-only sample job): exact sizes + SHA-256, zero missing/unmanifested/zero-size |
| mbp1_range_adjacency | PASS | [2024-08-17, 2025-08-17) + [2025-08-17, 2026-08-17): exactly adjacent, no gap, no overlap |
| mbp1_sample_overlap | WARN (explained) | File hashes differ 2–9 bytes/file (per-request DBN container metadata — cross-request file-hash identity is structurally unattainable); authoritative check is the record-level artifact |
| mbp1_sample_overlap_record_level | **PASS** | All 11 expected day-pairs (from the validated sample manifest) decoded and byte-compared: **115,583,040 records, all identical**; fail-safe (zero/missing/multiple counterparts, incomplete comparisons, dtype or byte mismatches all FAIL); binding embedded |
| mbp1_source_selection | PASS | 625 canonical research files, 2024-08-18 → 2026-08-16, every logical partition unique, ownership tracked, zero sample files in research input (resolved-path check) |
| storage_gate (post-purchase) | WARN | currently 1,720.9 GB free of 2,048 GB: **meets the 1,000 GB required minimum; below the 2,000 GB preferred headroom** — acceptable per policy since ≥1 TB remains free |
| **mbp1_acquisition_gate** | **PASS** | Cohesive gate: all 9 checks PASS — inventory/manifests/adjacency/selection/explained-overlap plus record-level identity **bound** to the current config hash, acquisition code hash, and on-disk manifest identities; `nqresearch.sources.require_provenance()` enforces it before any research preparation |

Provenance history of these eight artifacts: originally stamped to the
acquisition commit `6ba5d4d` (AL-0023), regenerated several times on
2026-08-18 as the calendar files joined the effective configuration hash
(interim stamps under `1c0a774`; AL-0026/AL-0027). **Current state: all
twelve QA artifacts (these eight plus the four closeout artifacts) are
stamped to the closeout commit `3c7aee5e0f240b69d136ff341b608644dafc7a52`
under one config hash and one code hash — AL-0028 records the final
hashes.**

## 6. Purchase gate for full two-year MBP-1 (§2.2, Milestone 0 item 14) — CLOSED

**The purchase is complete and validated** (§1a, §5.6): the two annual
canonical jobs are on disk, 642/642 manifest files hash-verified, the
acquisition/provenance gate is PASS (9/9 named checks), and all artifacts are
currently stamped to the closeout commit `3c7aee5e` (AL-0028; earlier stamps:
`6ba5d4d` per AL-0023). The gate below is preserved as the historical
pre-purchase record (its verdict authorized the purchase on 2026-08-17):

| Component | Status | Basis |
|---|---|---|
| Sample data quality (schema, mapping, timestamps, actions/sides/depth, flags, book sanity, coverage) | **PASS with understood WARNs** | §5.1 — no FAIL findings; WARNs are documented vendor semantics (file-start initialization records) and market-state semantics (halt/pre-open crossed states) that impose normalization obligations, not data defects |
| Cross-source trade reconciliation | **PASS (exact)** | §5.3 |
| Side/aggressor usability | **PASS** | §5.1, §5.2 — unsigned ≈0.0005% |
| Vendor manifest integrity (sizes + SHA-256) | **PASS** | manifest_validation.json — 34/34 job dirs, 788/788 files verified; zero failures/missing/unmanifested (after MBO re-download recovery, audit-log AL-0013) |
| Storage precondition (≥1 TB free NVMe) | **PASS** | §5.5 — 2,005.5 GB free on the D: data volume (also meets the 2 TB preferred headroom) |
| Sample representativeness | **WARN** | two August weeks; low-vol season; one Monday contains an unexplained mid-RTH crossed-book burst pending status-data classification |

*(Historical note: all gate components PASSed with documented WARN
qualifications; the purchase proceeded on 2026-08-18 and §5.6 records its
validation. Current storage status: §5.5.)*

## 6a. Milestone 0 closeout (2026-08-18; artifacts: `<data_root>/qa/m0_closeout/`)

- **CME calendar (baseline + official overrides)**: the versioned snapshot
  `config/data/cme_calendar.yaml` (pandas_market_calendars 5.4.0 "CME Globex
  Equity", pinned in uv.lock, content SHA-256 in the snapshot meta) is a
  **reproducible baseline, not authoritative by itself**; the attributable
  official-CME override file `config/data/cme_calendar_overrides.yaml` wins
  on conflict, and both files are in the effective config hash. Encoded
  override: **2025-01-09 National Day of Mourning — 08:30 CT close, zero
  expected RTH** (official CME schedule; source references in the override
  meta; observed data confirms 1.3M ETH rows, zero RTH). Baseline facts: 626
  trading days 2024-08-01 → 2026-12-31; Christmas/New Year full closures; 25
  early closes incl. **08:15 CT Good Friday short sessions** — all 25 early
  closes cross-checked observationally against decoded coverage (25/25
  consistent); document-level verification is governed by the **date-level
  evidence policy PA-0001** (§6c) after CME GCC confirmed no historical
  archive exists.
- **Front-contract/roll rule (PROPOSED, pending review)** — `nqresearch/rolls.py`:
  **strictly causal** — the front effective for session S is decided from the
  PREVIOUS completed eligible session's outright volumes (matching Databento's
  documented previous-day volume ranking for `.v.0`-style continuous
  contracts); session S's own completed volume never selects S's contract;
  the first corpus session is explicitly UNRESOLVED/ineligible (no look-ahead
  seed). Spreads excluded before volume calculation; switches only at session
  boundaries; **monotone-expiry** (never backward — deterministic, no tunable
  hysteresis); ties retain the incumbent; insufficient-volume sessions (e.g.
  Good Friday) retain the incumbent with `INSUFFICIENT_VOLUME`; prices never
  back-adjusted; switch records (with `decided_from_session`) are the
  authoritative boundaries for §8 window-crossing drops; roll-week = ±3
  sessions around a switch. Observed switch dates vs Databento v.0 semantics
  and CME customary roll timing: §6b.
- **MBO blocks — state `PROVISIONAL_DOCUMENT_VERIFICATION_PENDING`,
  `activation_ready=false`** (`mbo_blocks_frozen.json`): **77 NQ
  sessions in 30 blocks** — contiguity under the versioned effective calendar
  (artifact bound to baseline + overrides + merged calendar SHA-256);
  2026-07-03 reclassified `COMPLETE_SHORTENED_SESSION` (observed 3.5 h RTH ==
  calendar expectation), merging the 2026-06-29 → 2026-07-06 block.
  **Provisional until the document-level verification of the baseline
  calendar completes** (overrides meta `baseline_verification`); the same
  proviso applies to the partition proposal
  (`calendar_verification_state=PROVISIONAL_DOCUMENT_VERIFICATION_PENDING`,
  `activation_ready=false`). `activation_ready` may become true only when
  date-level calendar evidence is complete per PA-0001 (§6c: every
  exceptional date DOCUMENT_VERIFIED or
  TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE, no conflicts) AND all structural
  partition checks PASS AND explicit human partition approval binding the
  exact evidence hashes is recorded; artifact `status` expresses
  computational validity only, never activation readiness.
  Acquisition reasons: `UNKNOWN_NOT_RECORDED_PENDING_USER_INPUT`.
- **Partition proposal** (`partition_proposal.json`, **PROPOSED_NOT_ACTIVE** —
  requires explicit human approval; revised per review so **no MBO block
  spans a partition boundary**, enforced by a mandatory
  `no_partition_spanning_mbo_blocks` check that must refuse activation while
  non-empty): DEV 2024-08-19 → 2025-11-07; SELECTION 2025-11-10 →
  2026-03-31; HOLDOUT 2026-04-01 → 2026-08-14 (**tentative** per canonical
  §5.3); FORWARD from 2026-08-17 with the 2026-08-17 partial edge session
  explicitly ineligible. Every boundary validated as a CME trading day.
  Recalculated trading-day and MBO counts: §6b.
- **Full-history session-coverage audit** (`mbp1_full_history_coverage.json`,
  registry-scoped to canonical sources only, provenance-gated, resumable,
  disk-guarded): results in §6b below.

## 6b. Full-history coverage results (canonical corpus; final, corrected accounting)

**Evaluation range 2024-08-19 → 2026-08-14 (516 expected sessions): 507 PASS,
8 WARN, 1 expected Good Friday pre-RTH shortened/init-only session
(2025-04-18), zero unexpected missing, zero FAIL.** The 8 WARNs: 7 vendor-
degraded weekday dates (all with full expected RTH spans and normal activity)
plus 2025-01-09 `OFFICIAL_SPECIAL_CLOSURE_NO_RTH` (per the official CME
override). **2026-08-17 is reported separately as an out-of-window partial
edge session** (`EDGE_PARTIAL_QUERY_BOUNDARY`), excluded from the headline
counters and explicitly ineligible for FORWARD.

**Timestamp order:** zero within-file mid-stream disorder AND zero cross-file
order violations across the corpus (fresh records; a dedicated cross-file
monotonicity check backs the claim).

**Scope:** this artifact is the full-history *coverage* audit, NOT the
complete canonical §12 QA layer. Remaining §12 fields (sequence min/max,
duplicates, non-negative quantities, missing values, spread/tick sanity,
crossed/locked session-phase classification, roll-proximity joins, §13
per-session reconciliation) are a **mandatory Milestone 2 gate** before any
session becomes research-eligible (recorded in the artifact).

**Causal front-contract series** (strictly previous-session volumes): 8
switches, each recording its `decided_from_session`:
2024-09-17 NQU4→NQZ4, 2024-12-18 NQZ4→NQH5, 2025-03-19 NQH5→NQM5,
2025-06-17 NQM5→NQU5, 2025-09-17 NQU5→NQZ5, 2025-12-16 NQZ5→NQH6,
2026-03-17 NQH6→NQM6, 2026-06-16 NQM6→NQU6. Comparison note (recorded, not
forced): **CME's official equity-index roll date is the MONDAY before the
third Friday** (cmegroup.com/trading/equity-index/rolldates.html). The
causal volume-based switches lag those official Monday dates by **1–2
trading sessions** (Mondays 2024-09-16, 2024-12-16, 2025-03-17, 2025-06-16,
2025-09-15, 2025-12-15, 2026-03-16, 2026-06-15 → observed switches +1, +2,
+2, +1, +2, +1, +1, +1 sessions respectively) — the expected difference
between the official roll date and previous-day-volume `.v.0` semantics.
The first corpus session (2024-08-19) is UNRESOLVED/ineligible by rule, and
out-of-range sessions (2026-08-17 edge) are excluded from the series.

### Superseded first-pass results (history)

- **5,401,908,864 fresh records decoded across all 625 canonical files**
  (~432 GB decoded; 4,651 file-leading initialization records excluded from
  session statistics per their documented stale-timestamp semantics).
- **516 expected complete sessions (2024-08-19 → 2026-08-14): zero missing,
  507 PASS, 9 WARN, 0 FAIL.** 105 weekend/holiday pre-open remnant dates
  correctly classified as session-open mechanics, not sessions.
- After initialization-record filtering, **mid-stream `ts_event` disorder is
  ZERO across the entire corpus**; zero zero-size trades; zero unknown flag
  bits; 21,808 crossed F_LAST outright states corpus-wide (~35/session,
  consistent with halt/pre-open semantics; Milestone 2 session-phase item).
- **All 11 vendor-degraded dates explicitly assessed**: the 7 weekday dates
  with data have FULL expected RTH spans and normal activity (e.g.
  2026-03-16: 19.8M rows) — flags retained as WARN reason codes, no coverage
  impact; 2 are Saturdays without files; 2 (2026-01-31*, 2026-03-21*) —
  see artifact. WARN sessions: 7 degraded + 2025-01-09
  `NO_RTH_DATA_CALENDAR_MISMATCH` (1.3M ETH rows, zero RTH — consistent with
  the National Day of Mourning closure, not encoded by the calendar source;
  snapshot deliberately not hand-patched; review item) + 2026-08-17
  `EDGE_PARTIAL_QUERY_BOUNDARY`. Good Friday 2025-04-18: WARN
  (initialization-only file; session closes 08:15 CT before RTH).
- **Front-contract series** (`mbp1_front_contract_series.json`): exactly
  **8 switches** — the 8 quarterly rolls (Sep/Dec/Mar/Jun ×2 years) — under
  the proposed rule in §6a; per-session front + roll-week flags emitted.

## 6c. CME calendar evidence remediation (2026-08-19; protocol amendment PA-0001)

**Trigger.** CME GCC replied in writing (case 04700128, 2026-08-19, DKIM
`d=cmegroup.com` verified, email SHA-256
`67adfa61f089b3d99153d412843d3b20f1ecddae9b7541778fc7b0a6556004b0`, immutable
copy in `<data_root>/reference/cme_calendar/`): **CME does not maintain an
archive of previous years' holiday calendars** and refers only to the current
2026 holiday page. The blanket "official CME document per holiday group"
requirement is therefore impossible for 2024/2025 dates. This correspondence
proves archive unavailability only — never historical session times.

**Amended policy (PA-0001,
`docs/protocol-amendments/PA-0001-cme-calendar-evidence-policy.md`).**
Verification is now **per exceptional date** (never per recurring group
alone), recorded in the committed machine-readable matrix
`config/data/cme_calendar_evidence.yaml` and enforced by
`nqresearch/calendar_evidence.py` + the activation verifier in
`nqresearch/holdout.py`. States: `DOCUMENT_VERIFIED`,
`TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE` (verified GCC archive-
unavailability + observed canonical Databento behaviour + at least one
qualifying independent secondary source, no material conflict),
`PENDING_EVIDENCE`, `CONFLICT_REQUIRES_REVIEW`. Evidence hierarchy: official
CME artifact > GCC correspondence (availability facts only) > observed
canonical MBP-1 behaviour > strong/partial secondary (NinjaTrader 2026, AMP
GCC-attributed tables, dated ForexLive/Insignia statements) > lower-tier
(CrossTrade, corroboration only) > tertiary date-only (Kibot — never session
times). Mechanical fail-closed rules: sources support only their declared
dates (a 2026 document can never promote a 2024/2025 date); every evidence
file hash is verified against the immutable copies under
`<data_root>/reference/cme_calendar/`; observed blocks are cross-checked
against the live coverage artifact; groups roll up to their **weakest**
member date.

**Current state (26 exceptional dates: 21 early closes + 4 full holidays +
2025-01-09):**

- `DOCUMENT_VERIFIED` (8): **2025-01-09** (official CME mourning-schedule
  PDF, which explicitly displays 'JANUARY 9, 2025' and 'CME GROUP US
  EQUITIES — CLOSE at 8:30 AM CT'; corroborated by AMP's dated table and
  observed zero-RTH data; CME's URL-slug year token '2024' is a naming
  artifact — the printed date governs) and
  **all seven 2026 corpus dates** (2026-01-01, 01-19, 02-16, 04-03 Good
  Friday 08:15 CT, 05-25, 06-19, 07-03) via the seven researcher-downloaded
  CME trading-hours exports, each independently corroborated by
  NinjaTrader's 2026 schedule and observed data.
- `TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE` (8): 2024-11-28 (ForexLive
  direct 12:00 halt), 2024-12-24 + 2024-12-25 (Insignia direct 12:15 halt /
  full closure), 2025-09-01, 2025-11-27, 2025-11-28, 2025-12-24, 2025-12-25
  (AMP dated CME-Globex state tables, direct).
- `PENDING_EVIDENCE` (10): 2024-09-02, 2024-11-29 (the only secondary
  statement about the Friday sequence is excluded as ambiguous), 2025-01-01,
  2025-01-20, 2025-02-17, 2025-04-18 (also no usable vendor records),
  2025-05-26 (AMP content drift destroyed the expected 2025 evidence),
  2025-06-19 (no secondary at all), 2025-07-03, 2025-07-04 —
  lower-tier/date-only corroboration exists for most but never suffices
  under PA-0001.
- `CONFLICT_REQUIRES_REVIEW`: none. CrossTrade's broad "Closed" labels for
  pre-RTH/ETH sessions and ForexLive's Friday wording are recorded as source
  imprecision limitations, not material conflicts.

**Findings recorded.** (a) The 2025-07-03 12:15 CT vs 2026-07-03 12:00 CT
baseline question is **resolved**: 2025-07-03 (Thu) was the 12:15
pre-holiday close, 2025-07-04 (Fri) the 12:00 holiday session; 2026-07-03 IS
the observed holiday (12:00, officially documented). (b) **AMP content
drift confirmed**: the Memorial Day URL now serves 2026-only assets; claims
are bound to exact downloaded HTML/PNG hashes. (c) 2025-04-18 Good Friday
has no usable vendor records (expected-missing pre-RTH short session),
unlike 2026-04-03 (881,799 records ending exactly 08:15 CT).

**Activation consequences.** Partitions can become eligible only when every
date is `DOCUMENT_VERIFIED` or `TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE`
with no conflicts, all structural checks PASS, and the activation binds the
exact evidence-matrix, GCC-correspondence, effective-calendar and proposal
hashes, with an append-only audit-log entry recording explicit human
approval of those exact hashes. With 10 dates pending, the effective
calendar, MBO blocks and partitions remain
PROVISIONAL_DOCUMENT_VERIFICATION_PENDING and `activation_ready=false`.

## 6d. Research-eligibility quarantine (2026-08-19; protocol amendment PA-0002)

**Ten calendar dates are PROPOSED for research quarantine** — 2024-09-02,
2024-11-29, 2025-01-01, 2025-01-20, 2025-02-17, 2025-04-18, 2025-05-26,
2025-06-19, 2025-07-03, 2025-07-04 — i.e. exactly the §6c
`PENDING_EVIDENCE` set. **Their calendar-evidence states are UNCHANGED and
remain `PENDING_EVIDENCE`**: quarantine is a research-policy disposition,
never a claim that the calendar was verified, and the effective calendar
stays explicitly provisional.

**Only eight observed DEV sessions are lost.** 2025-01-01 is not a CME
trading day (no session exists) and 2025-04-18 closes 08:15 CT before the
08:30 RTH open and additionally has no usable vendor records — neither could
produce an RTH sample under any decision. Observed DEV sessions therefore go
**317 → 309 eligible**, out of 318 DEV trading days.

**Basis:** canonical §50's allowed *"predefined holiday/partial-session
rule"* exclusion, with the machine-readable reason code
`PREDEFINED_HOLIDAY_PARTIAL_SESSION_RULE`, defined in advance of any
feature, label, model or result. **Rationale:** with no obtainable official
schedule, the observed data agrees only with *our own* calendar; a baseline
error would propagate self-consistently through session assignment, RTH
windowing, labels and evaluation and never surface. Quarantine costs 2.5% of
DEV and leaves PA-0001's evidence threshold intact rather than opening it
with an exception.

**What is retained:** raw data is untouched and immutable; the dates remain
in the effective calendar and in coverage accounting (**516 expected
sessions unchanged** — eligibility is a separate mask, never a deletion);
normalization and QA may still process them for session reconstruction.
**What is forbidden:** research input, and any feature window, label
horizon, sample window or evaluation window that touches or crosses them;
rolling state must reset at the next eligible session (for the consecutive
2025-07-03/04 pair that is **2025-07-07**).

**Nothing structural changes.** No quarantined date is a partition boundary,
an MBO session, inside any MBO block span, or a causal-roll
`decided_from_session`. Partition ranges stay contiguous (DEV 318 /
SELECTION 100 / HOLDOUT 98 trading days), the **MBO inventory stays 77
sessions in 30 blocks with zero spanning blocks — no MBO block is
quarantined** — and the **eight causal roll switches are unchanged**;
2025-06-19 remains recorded as roll-week adjacent in the data-level series,
which never consumes the eligibility mask. HOLDOUT is untouched and sealed.

Machinery: `config/data/research_eligibility.yaml` (strict schema, bound to
the evidence-matrix SHA-256) enforced by `nqresearch/eligibility.py`; the
activation disposition is computed by a separate check
(`resolve_activation_disposition`) that leaves evidence states alone, always
blocks on `CONFLICT_REQUIRES_REVIEW`, and requires the policy to cover the
pending set exactly. **Partitions remain PROPOSED_NOT_ACTIVE with
`activation_ready=false`**; the artifact-level calendar state under this
disposition is the explicitly provisional
`PROVISIONAL_PENDING_DATES_QUARANTINED`.

**Preferred first Milestone 2 pilot month: October 2025** — no quarantined
date, fully inside DEV, away from SELECTION/HOLDOUT, and containing MBO lab
sessions useful for reconstruction validation. Note that **MBO-BLK-008 spans
2025-10-30 → 2025-11-07** and is therefore *not* an October-only block: the
later pilot plan must either exclude it from block-level validation or
extend the QA-only validation window to 2025-11-07 without changing the
defined research month.

## 7. Unresolved assumptions and open items (current, post-closeout)

Current state reference: §6a/§6b/§6c and audit-log AL-0028/AL-0039.

1. **Date-level calendar evidence completion (PA-0001, §6c)** — 10 of 26
   exceptional dates remain PENDING_EVIDENCE (no qualifying independent
   secondary evidence; CME archive officially unavailable). Resolution
   requires either newly surfaced qualifying evidence per date or an
   explicit reviewed decision on the pending dates. Until then: effective
   calendar, MBO blocks, and partition dates stay
   PROVISIONAL_DOCUMENT_VERIFICATION_PENDING.
2. **Partition activation** — the proposal is structurally valid (all gates
   PASS) but PROPOSED_NOT_ACTIVE with activation_ready=false; requires
   document verification (item 1) plus explicit human approval. The holdout
   boundary 2026-04-01 remains TENTATIVE until that approval.
3. **Crossed-book states** — presumed halt/auction/pre-open indicative states;
   classification needs session-phase logic and possibly the vendor `status`
   schema for halt windows (notably 2026-08-10 11:31:58 CT). Milestone 2.
4. **Remaining canonical §12 QA fields** (sequence min/max, duplicates,
   non-negative quantities, missing values, spread/tick sanity, crossed/locked
   phase classification, roll-proximity joins, §13 per-session
   reconciliation) — mandatory Milestone 2 gate before research eligibility.
5. **Front/roll rule** — defined and computed (strictly causal, §6a/§6b) but
   still PROPOSED pending review sign-off recorded with partition approval.
6. **MBO acquisition reasons** (§30) — UNKNOWN_NOT_RECORDED; MBO_LAB
   selection-bias comparison now unblocked by the full corpus but not yet
   performed (Milestone 2+).
7. **2025-01-09** — official special closure encoded via override; session
   retained as WARN pending an explicit eligibility decision.
8. **Storage** — 1,720.9 GB free (WARN, ≥1 TB met); re-run the gate before
   Milestone 2's large writes.

Historical (superseded) open-item lists are preserved in this document's
earlier sections and in audit-log entries AL-0004…AL-0027-A; the items about
a missing calendar, undefined roll rule, and unpurchasable/absent full
history are **resolved by the closeout** and retained above only as history.

9. *(Resolved 2026-08-17 — retained pointer only.)* Items previously listed
   here — two MBO sessions with apparently partial vendor coverage and three
   MBO job directories without manifests — were both symptoms of **incomplete
   MBO downloads**, discovered via recovered manifests, re-downloaded, and
   fully SHA-256-validated. History: audit log AL-0008, AL-0012, AL-0013.

## 8. Edge-case obligations carried into Milestone 2 (§74)

File-level observations already establish these obligations for normalization:
sessions span UTC file boundaries; Sunday files contain pre-open states; crossed
books occur in pre-open/no-cancel periods and must be handled by session-phase
classification rather than deleted; `R` (clear/reset) actions may appear at book
initialization; unsigned trades (`side=N`) exist and stay unsigned (§2.1); volume
accumulators must reset on contract switch and session boundary (§15.1).
