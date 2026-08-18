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
  Friday — CME holiday)**. WARN status reflects only that the holiday calendar
  is not yet machine-integrated; effective coverage is complete.

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

- **Authoritative NQ MBO session inventory: 76 full-RTH sessions in 31
  provisional blocks**, plus **1 partial session**: 2026-07-03 (54% RTH span —
  Independence Day half-session; reclassifies as a complete *shortened*
  session once the holiday calendar exists). 106 additional dates observed in
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
- Block contiguity rule: sessions are contiguous when no Mon–Fri weekday lies
  strictly between them. **Open item:** the CME holiday calendar is not yet
  integrated; blocks spanning a holiday may be over-split. Block IDs are frozen
  only after the deep audit and holiday calendar (before any MBO_LAB research use).
- **Unresolved:** the reason each block was acquired is not documented in the data
  directories; per canonical §30 this must be supplied by the researcher, and the
  MBO_LAB selection-bias comparison (volatility/volume/event-day distribution vs the
  broad population) requires the full broad dataset, so it is deferred until the
  two-year MBP-1 history exists.

### 5.5 Storage check (§2.2, §59; Milestone 0 item 16) — **PASS** (on D:)

- Repeatable gate: `nqr data storage-gate` measures the volume holding the
  configured data root (artifact `storage_gate.json`). After migration to
  `D:/nq-research/data` (2026-08-17): **2,005.5 GB free — PASS** (≥ 1000 GB
  required minimum AND ≥ 2000 GB preferred headroom, the latter narrowly).
  History: earlier runs against the C: volume measured 263.2–284.6 GB free
  (FAIL) and correctly blocked the purchase until the D: volume existed.
- Two-year MBP-1 extrapolation from the sample (August weekday mean ≈ 243 MB
  compressed / 922 MB decoded DBN × 504 trading days): **≈122 GB compressed,
  ≈465 GB decoded** — consistent with the spec's ~361 GB raw planning figure,
  with wide seasonal uncertainty (August is a low-activity month).
- Canonical requirement before the full purchase: **≥1 TB free NVMe (2 TB
  preferred)** to hold raw MBP-1 + normalized Parquet + QA + features + existing
  MBO (~36 GB after the re-download) + experiment artifacts. The D: data volume
  meets both thresholds.

### 5.6 Post-purchase acquisition validation (2026-08-18; `<data_root>/qa/mbp1_full_history/`)

| Artifact | Status | Result |
|---|---|---|
| mbp1_source_inventory | WARN (understood) | All three jobs match registry + spec expectations (request IDs, placement, dataset/schema/symbology, encoding, splits, integer prices, ranges, manifest.json SHA-256 vs registry); WARN reflects the 11 vendor-degraded condition dates pending Milestone 2 session QA |
| mbp1_manifest_validation | PASS | 642/642 manifested files re-hashed (314 + 315 + 13 incl. QA-only sample job): exact sizes + SHA-256, zero missing/unmanifested/zero-size |
| mbp1_range_adjacency | PASS | [2024-08-17, 2025-08-17) + [2025-08-17, 2026-08-17): exactly adjacent, no gap, no overlap |
| mbp1_sample_overlap | WARN (explained) | File hashes differ 2–9 bytes/file (per-request DBN container metadata — cross-request file-hash identity is structurally unattainable); authoritative check is the record-level artifact |
| mbp1_sample_overlap_record_level | **PASS** | All 11 expected day-pairs (from the validated sample manifest) decoded and byte-compared: **115,583,040 records, all identical**; fail-safe (zero/missing/multiple counterparts, incomplete comparisons, dtype or byte mismatches all FAIL); binding embedded |
| mbp1_source_selection | PASS | 625 canonical research files, 2024-08-18 → 2026-08-16, every logical partition unique, ownership tracked, zero sample files in research input (resolved-path check) |
| storage_gate (post-purchase) | WARN | 1,847 GB free of 2,048 GB: **meets the 1,000 GB required minimum; below the 2,000 GB preferred headroom** — acceptable per policy since ≥1 TB remains free |
| **mbp1_acquisition_gate** | **PASS** | Cohesive gate: all 9 checks PASS — inventory/manifests/adjacency/selection/explained-overlap plus record-level identity **bound** to the current config hash, acquisition code hash, and on-disk manifest identities; `nqresearch.sources.require_provenance()` enforces it before any research preparation |

Envelopes record `data_root = D:\nq-research\data`, one code hash, one config
hash; generated from an uncommitted working tree (`git_sha = c74b825`), so a
**post-commit re-stamp** of these artifacts is required after the acquisition
commit.

## 6. Purchase gate for full two-year MBP-1 (§2.2, Milestone 0 item 14)

**Gate verdict: PASS — the purchase is unblocked** (as of the 2026-08-17
migration to the D: data volume). Remaining WARNs are documented
qualifications, not blockers. The two-year history is intentionally NOT yet
purchased; nothing in the audit treats its absence as missing data.

| Component | Status | Basis |
|---|---|---|
| Sample data quality (schema, mapping, timestamps, actions/sides/depth, flags, book sanity, coverage) | **PASS with understood WARNs** | §5.1 — no FAIL findings; WARNs are documented vendor semantics (file-start initialization records) and market-state semantics (halt/pre-open crossed states) that impose normalization obligations, not data defects |
| Cross-source trade reconciliation | **PASS (exact)** | §5.3 |
| Side/aggressor usability | **PASS** | §5.1, §5.2 — unsigned ≈0.0005% |
| Vendor manifest integrity (sizes + SHA-256) | **PASS** | manifest_validation.json — 34/34 job dirs, 788/788 files verified; zero failures/missing/unmanifested (after MBO re-download recovery, audit-log AL-0013) |
| Storage precondition (≥1 TB free NVMe) | **PASS** | §5.5 — 2,005.5 GB free on the D: data volume (also meets the 2 TB preferred headroom) |
| Sample representativeness | **WARN** | two August weeks; low-vol season; one Monday contains an unexplained mid-RTH crossed-book burst pending status-data classification |

All gate components now PASS (with documented WARN qualifications). The
purchase of the two-year MBP-1 history may proceed when the researcher decides;
per §59, monitor free space during the download and re-run
`nqr data storage-gate` before each large tranche.

## 7. Unresolved assumptions and open items

1. *(Resolved 2026-08-17.)* **Storage** — the D: data volume passes the gate
   (§5.5); re-run `nqr data storage-gate` before each large download tranche.
2. **CME holiday calendar** — not yet machine-integrated. Affects: trades-coverage
   WARN (Good Friday), MBO block contiguity (blocks may be over-split at
   holidays), and future session-completeness QA. Required before MBO block IDs
   are frozen and before partition dates are frozen.
3. **Crossed-book states** — presumed halt/auction/pre-open indicative states;
   classification needs session-phase logic and possibly the vendor `status`
   schema for halt windows (notably 2026-08-10 11:31:58 CT). Must be resolved in
   Milestone 2 normalization design.
4. **Front-contract/roll rule** — parent symbology means no vendor continuous
   selector exists; a volume-leading front/roll definition must be specified and
   verified when multi-month data exists (the two-week sample contains no roll;
   NQU6 led throughout).
5. **MBO acquisition reasons** (§30) — not documented in the data; must be
   supplied by the researcher. MBO_LAB selection-bias comparison deferred until
   the broad two-year dataset exists.
6. **Partition dates (DEV/SELECTION/HOLDOUT)** — cannot be frozen yet: they
   require the full two-year MBP-1 coverage plus the holiday calendar and MBO
   block placement (canonical §60 items 11–12). The holdout boundary remains
   TENTATIVE (~2026-04-01 discussed, not final).
7. **Sequence-number semantics** — treated as channel-level and diagnostic-only;
   initialization records carry stale sequence values. No mid-stream anomalies
   observed; semantics to be revisited only if future files disagree.
8. **Seasonality of storage estimate** — extrapolated from August; re-estimate
   after the first full-history download tranche.
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
