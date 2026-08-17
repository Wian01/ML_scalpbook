# Implementation Audit Log

**Append-only.** Every material implementation fix, audit/review finding, test
change, artifact regeneration, data-quality discovery, and protocol-relevant
decision gets an entry. Previous entries — including mistakes and superseded
conclusions — are never edited or erased; corrections are recorded as new
entries that reference the superseded ones. Each entry records affected files,
validation evidence, artifact hashes where applicable, unresolved risks, and
the Git commit SHA once one exists. Maintenance of this log is non-negotiable
rule 21 in [CLAUDE.md](../CLAUDE.md).

All entries below occurred on **2026-08-17** (project start) in a repository
with no commits yet; commit SHAs are recorded as `pending` and must be filled
in by the entry that creates the initial commit.

---

## AL-0001 — Original Milestone 0 implementation

- **Category:** implementation (initial)
- **Actor:** Claude (Claude Code)
- **What:** Preserved the frozen V1.0 spec verbatim (`docs/canonical-spec-v1.0.md`,
  copy hash-verified against the original `CLAUDE.md`); decomposed it into
  `CLAUDE.md`, `docs/research-protocol.md`, `docs/data-specification.md`,
  `docs/experiment-protocol.md`, `docs/holdout-policy.md`, `docs/architecture.md`.
  Built the uv/Python-3.12 foundation (`pyproject.toml`, `uv.lock`), package
  `src/nqresearch/` (sessions, symbols, flags, dbnio, CLI `nqr data audit`),
  QA modules (mbp1_audit, trades_audit, reconcile, mbo_inventory, status,
  report), and unit tests. Data inventoried read-only: two-week MBP-1 sample
  (11 files, 2026-08-03→08-14), 624 trades files (2024-08-09→2026-08-07),
  MBO job directories.
- **Evidence:** 51 unit tests passing at first run; later 56 after fixes below.
- **Unresolved at the time:** see subsequent entries.
- **Commit:** pending

## AL-0002 — Filename-date parsing bug (caught pre-artifact)

- **Category:** implementation fix
- **What:** The first filename-date parser concatenated all digits in a vendor
  filename; `glbx-mdp3-20260803...` contains the `3` of `mdp3`, so dates
  parsed as year 3202 and would have crashed/corrupted aggregation. Caught by
  self-review while the first audit ran; the run was stopped and no artifact
  was produced with the bug. Fix: regex-based `nqresearch/filenames.py`
  (`file_utc_date`) + tests.
- **Affected files:** `src/nqresearch/filenames.py`, `qa/mbp1_audit.py`,
  `qa/trades_audit.py`, `qa/mbo_inventory.py`, `qa/reconcile.py`,
  `tests/unit/test_filenames.py`.
- **Evidence:** `test_filenames.py::test_ignores_mdp3_digit`.
- **Commit:** pending

## AL-0003 — Memory-pressure failures; parallelism reduced; resumable caches

- **Category:** implementation fix
- **What:** First full audit launch ran 12 decode workers concurrently on a
  31.9 GB-RAM machine; both MBP-1 and trades audits died with
  `MemoryError`/`ArrayMemoryError`. Fixes: chunk size 5M→2M rows; workers
  MBP-1 2, trades 4, reconcile 2; per-file resumable JSON caches so
  interrupted runs resume; vectorized a per-row Python loop in the trades
  audit. (Cache keying at this stage was filename+size only — superseded by
  AL-0009.)
- **Evidence:** subsequent full runs completed; caches observed resuming.
- **Commit:** pending

## AL-0004 — First Milestone 0 results (superseded in parts)

- **Category:** artifact generation + data-quality discovery
- **What:** First complete artifacts: MBP-1 sample audit (115,583,040 records;
  WARNs for file-start initialization records with stale `ts_event` and for
  crossed books), trades audit (195,621,134 trades; `side=N` 0.0005%; only
  missing weekday 2025-04-18 = Good Friday), UTC-day reconciliation (5 days
  exact PASS), filename-based MBO inventory (80 files → "80 sessions,
  30 blocks" — **superseded by AL-0013/AL-0019**: filename-derived counts
  overcount sessions). Crossed-book counts were initially computed over all
  records including partial-packet states; re-run counting F_LAST-complete
  states separately (637 crossed F_LAST states, clustered at 15:15:00 CT
  close-halt, maintenance/pre-open windows, and one unexplained burst
  2026-08-10 11:31:58 CT). Storage measured ~272-285 GB free vs ≥1 TB
  required → purchase gate capped at WARN.
- **Evidence:** `data/qa/m0/*.json` (first generation); 56 tests passing.
- **Unresolved risks then:** holiday calendar; crossed-burst classification;
  roll rule under parent symbology; MBO acquisition reasons; storage.
- **Commit:** pending

## AL-0005 — Review #1 (Codex) findings

- **Category:** audit/review finding
- **What:** External review accepted the data-quality conclusion but required
  implementation corrections: (1) configurable data root; (2) repeatable
  storage-gate command; (3) vendor manifest size+SHA-256 validation; (4)
  versioned cache keys (relpath + vendor hash + code hash + params — not
  filename+size); (5) Git SHA must check the return code (unborn repo was
  recorded as `"HEAD"` — a real bug in the first artifacts); (6) MBO inventory
  provisional; decode actual NQ timestamps/RTH coverage/session IDs, detect
  extra products, document ES.FUT in the 2026-05-04→05-07 job; (7) add
  CME-session-level reconciliation; (8) session boundary/RTH into config;
  (9) tests for all; (10) regenerate artifacts.
- **Commit:** pending

## AL-0006 — Mid-review user guidance: ES.FUT is expected

- **Category:** protocol-relevant decision
- **What:** The presence of ES.FUT in some MBO files is expected, not an
  error. Mixed raw files are preserved unchanged; products are identified via
  instrument mappings; ES records and NQ calendar spreads are ignored in NQ
  research; the NQ MBO session inventory is computed from filtered NQ outright
  coverage; excluded products are recorded in QA metadata.
- **Commit:** pending

## AL-0007 — Configurable data root + repeatable storage gate

- **Category:** implementation
- **What:** `config/data/paths.yaml` (`data_root`, storage-gate thresholds),
  `NQR_DATA_ROOT` env override; `nqr data storage-gate` measures the volume of
  the configured data root (PASS ≥2000 GB preferred / WARN ≥1000 GB required /
  FAIL below). Session boundary/RTH moved to `config/data/sessions.yaml`
  (Pydantic-validated; both scalar and polars implementations config-driven).
- **Affected files:** `src/nqresearch/config.py`, `paths.py`, `sessions.py`,
  `qa/storage.py`, `cli.py`, `config/data/*.yaml`, tests.
- **Evidence:** `test_config_paths.py`, `test_storage_gate.py`,
  `test_sessions.py::TestConfigDriven`.
- **Commit:** pending

## AL-0008 — Vendor manifest validation; discovery of unverifiable MBO dirs

- **Category:** implementation + data-quality discovery
- **What:** `qa/manifest.py` validates presence, exact size, and SHA-256 of
  every manifested file. First run reported 31 job dirs / 763 files PASS —
  and review of the count exposed that the scan silently skipped data
  directories WITHOUT a manifest. Fix: flag them. Result: 3 MBO job dirs
  (`GLBX-20260811-7Y95BGBTK7`, `GLBX-20260811-BQSAJRE7SW`,
  `GLBX-20260811-SLYLKQQKVP`; then 14 data files visible) had no
  `manifest.json` and could not be hash-verified → WARN. **This finding led
  directly to the discovery (AL-0012) that those downloads were incomplete.**
- **Evidence:** `test_manifest.py` incl.
  `test_data_dir_without_manifest_warns`; `manifest_validation.json` (WARN
  generation).
- **Commit:** pending

## AL-0009 — Versioned cache keys; Git-SHA fix

- **Category:** implementation fix
- **What:** `qa/cache.py`: cache reuse now requires matching source-relpath
  (vs data root), vendor manifest SHA-256 plus size+mtime, SHA-256 of the
  whole package source tree, and audit params. Filename+size-only reuse
  (AL-0003) retired. `_git_sha` checks the return code: an unborn repository
  records `null` (previous artifacts had recorded the literal string "HEAD").
  Envelopes extended with `audit_code_hash` and `data_root`.
- **Evidence:** `test_cache.py`, `test_report_gitsha.py`.
- **Commit:** pending

## AL-0010 — MBO deep audit (NQ-only decoding); UTC+session reconciliation

- **Category:** implementation
- **What:** `qa/mbo_audit.py` decodes every MBO file: products identified via
  embedded instrument mappings; ES records and NQ calendar spreads excluded
  from NQ research with per-file excluded counts recorded; NQ-outright
  first/last `ts_event`, per-CME-session rows, RTH span coverage; provisional
  blocks from decoded coverage. `qa/reconcile.py` rewritten to produce, from
  one decode pass per file, both UTC-day and CME-session aggregates; session
  comparisons cover only sessions whose full window lies in the common file
  set of both sources. Filename-based `mbo_inventory` marked provisional.
- **Evidence:** `test_reconcile_units.py`, `test_symbols.py`
  (product roots / NQ classification); session reconciliation exact PASS
  (4 complete sessions 2026-08-04→07, 19 pairs, 1,653,678 trades per side).
- **Commit:** pending

## AL-0011 — Ghost-session classifier correction

- **Category:** implementation fix + data-quality discovery
- **What:** First deep-audit aggregation classified sessions by RTH span alone
  and reported "90 full sessions" — wrong: 20 of them had 37–2,000 rows.
  File-start initialization records with stale historical timestamps can span
  an earlier date's RTH window and fabricate "ghost sessions". Fix: row-count
  thresholds (trace <10k rows = initialization artifact; full requires ≥95%
  span AND ≥100k rows; else partial), recorded in the artifact as QA
  classification parameters. Corrected result (pre-repair data): **70 full +
  3 partial (2025-10-09 45% span; 2025-11-05 39% span; 2026-07-03 54% span
  half-day) + 104 initialization-artifact dates; 30 provisional blocks**;
  1,854,184,746 records decoded; ES exclusions 56,819,215 rows; NQ spread
  exclusions 4,584,189 rows. The strict code-hash cache keying forced a full
  re-decode for this aggregation-only change — accepted as the intended
  behavior of AL-0009.
- **Evidence:** `test_mbo_session_classification.py`; superseded artifact
  regenerated.
- **Commit:** pending

## AL-0012 — Review #2 acceptance; discovery of incomplete MBO downloads

- **Category:** audit/review finding + data-quality discovery
- **What:** Second review passed the implementation (122/122 tests) and the
  data-quality conclusion. The three unverifiable MBO directories (AL-0008)
  were investigated: recovered manifests showed the downloads were
  **incomplete — missing whole files, not just manifests**. The two
  "partial sessions" 2025-10-09 and 2025-11-05 (AL-0011) were artifacts of
  truncated downloads, not vendor coverage gaps (the earlier "vendor coverage
  starts mid-day" interpretation is superseded).
- **Commit:** pending

## AL-0013 — MBO re-download recovery and validation

- **Category:** data-quality recovery
- **What:** The three incomplete jobs were re-downloaded (by the user;
  raw files replaced by complete vendor downloads with manifests — recorded
  here as a vendor-data refresh, not an edit of raw data). Observed on disk
  afterwards: 85 MBO data files (was 80): `GLBX-20260811-SLYLKQQKVP` 1→4
  files (2025-10-09→10-13), `GLBX-20260811-7Y95BGBTK7` 6→8 files
  (2025-10-30→11-07 incl. 11-06/11-07 previously absent),
  `GLBX-20260811-BQSAJRE7SW` 7 files (2026-01-06→01-13) re-fetched.
  Independent manifest validation (user-side) and repository-side re-run:
  **34/34 job dirs with manifests, 788/788 files pass presence + exact size +
  SHA-256, zero failures, zero missing manifests, zero unmanifested DBN
  files.** The original failure (AL-0008/AL-0012) remains part of this
  record and is not erased.
- **Evidence:** `manifest_validation.json` (PASS generation, hash in
  AL-0015); repaired files invalidated their old caches (new vendor hash +
  mtime) per `test_cache.py::test_repaired_file_with_new_manifest_hash_invalidates`.
- **Commit:** pending

## AL-0014 — Review #3 corrections: gitignore anchor, config hash, audit log

- **Category:** implementation fix + process
- **What:** (1) `.gitignore` `data/` → `/data/`: the unanchored pattern
  incorrectly ignored `config/data/paths.yaml` and `config/data/sessions.yaml`
  (they were never committed only because no commit exists yet; the rule was
  still wrong). Test added asserting those files are not ignored and the data
  tree is. (2) `effective_config_hash()` (parsed `config/data/*.yaml` values +
  resolved data root) added to cache keys and artifact envelopes; tests prove
  a session-timezone/boundary/RTH or data-root change invalidates
  session-dependent cached results. (3) This audit log created with the
  reconstructed history above; CLAUDE.md non-negotiable rule 21 added
  requiring every future assistant to maintain it append-only. (4) Obsolete
  "three manifests missing" statements removed from current-state docs
  (history preserved here).
- **Affected files:** `.gitignore`, `src/nqresearch/config.py`,
  `qa/cache.py`, `qa/report.py`, `CLAUDE.md`,
  `docs/implementation-audit-log.md`, `docs/data-specification.md`,
  `docs/architecture.md`, `tests/unit/test_gitignore.py`,
  `tests/unit/test_config_hash.py`, `tests/unit/test_cache.py`.
- **Evidence:** test suite (count recorded in AL-0015).
- **Commit:** pending

## AL-0015 — Full Milestone 0 regeneration on repaired data (final for this stage)

- **Category:** artifact regeneration
- **What:** Complete audit re-run under one code hash and one effective config
  hash; repaired MBO files re-decoded from scratch (old caches invalidated by
  vendor hash + config hash). Results recorded below after completion.
- **Results:** *(appended upon completion — see AL-0016)*
- **Commit:** pending

## AL-0016 — Final Milestone 0 results (repaired data), hash-uniform artifacts

- **Category:** artifact regeneration + data-quality result
- **Actor:** Claude (Claude Code)
- **What:** Full regeneration completed. All seven artifacts share
  `audit_code_hash`
  `b4d7a27aabcaa4e3c7ad3bdf71f52cea27cb417bcd5f57867f457a6ef53caa40`,
  `config_hash`
  `1bfe19bb7698b24654aa8fc69800051bc831803de4d35f15e028120e30a6fddf`,
  and `data_root` `C:\Users\Wian\projects\trading\ML_scalpbook\data`;
  `git_sha` correctly `null` (unborn repository).
- **Manifest validation:** PASS — 34/34 job dirs, 788/788 files (presence,
  exact size, SHA-256), zero failures, zero missing manifests, zero
  unmanifested DBN files. Matches the user's independent validation.
- **MBO deep audit (repaired data):** 85 files, 2,005,045,979 records decoded.
  **Authoritative NQ session inventory: 76 full-RTH sessions, 1 partial
  (2026-07-03 Independence Day half-day; pending holiday-calendar
  reclassification as complete-shortened), 106 initialization-artifact dates,
  31 provisional blocks.** Change vs pre-repair (AL-0011: 70 full + 3
  partial, 30 blocks): 2025-10-09 and 2025-11-05 became full (their "partial
  vendor coverage" was truncated downloads); new sessions 2025-10-10,
  2025-10-13, 2025-11-06, 2025-11-07 from previously missing files; blocks
  2025-10-09→10-13 (3) and 2025-10-30→11-07 (7) now complete. ES exclusions
  56,819,215 rows (unchanged — ES job was never incomplete); NQ
  calendar-spread exclusions 4,952,807 rows (was 4,584,189; repaired files
  added ~369k).
- **Other artifacts:** MBP-1 sample audit WARN (unchanged findings — init
  records, halt/pre-open crossed states); trades audit WARN (holiday calendar
  pending; data clean); reconciliation PASS exact at UTC-day (5 days) and
  CME-session (4 sessions, 19 pairs, 1,653,678 trades/side) granularity;
  storage gate FAIL (263.2 GB free — dropped ~21 GB due to the re-downloads —
  vs 1000 GB required); provisional filename inventory WARN.
- **Artifact SHA-256:**
  - `storage_gate.json` `6ddd7a14b8637b1f96fe1bba588ba0175855829b67c6dd0345d1ad380b871374`
  - `manifest_validation.json` `3334b84b3d719e5c7be404ff80499ebb8dd3d9ec5f7ac3f434fdf5e3ca77f985`
  - `mbp1_sample_audit.json` `80f56ae3a01110ba37d3cec13da957f3d6802d1ab74c8a1b728f35e887b0090b`
  - `trades_audit.json` `b970bef38818827df1d8420260ff67138aab784898c5af18969e4e86177eed33`
  - `mbp1_trades_reconciliation.json` `48d987d83e57ca4ff16f28e8f1736477c14223b418432858e95cf0581d50df2a`
  - `mbo_inventory.json` `a3cdcf96a1efd9105ed8a7ec307e3d98eee958d81b8a759182869a67508051bb`
  - `mbo_deep_audit.json` `35045c6102aa9058bb823d57ef2bcb9d23edba8bd4fe3683a861392975a8e33e`
- **Tests:** 135/135 passing (final suite, including gitignore-anchoring,
  config-hash, config-driven cache invalidation, repaired-file invalidation,
  and MBO session-classification tests).
- **Unresolved risks/blockers:** storage FAIL blocks the two-year MBP-1
  purchase (add M.2, repoint `data_root`/`NQR_DATA_ROOT`, re-run
  `nqr data storage-gate`); CME holiday calendar not integrated (blocks WARN
  statuses, provisional block IDs, 2026-07-03 classification); crossed-book
  burst 2026-08-10 11:31:58 CT unclassified pending session-phase/`status`
  data; front/roll rule for parent symbology undefined until Milestone 2;
  MBO acquisition reasons undocumented (spec §30); partition/holdout dates
  unfrozen (correctly — require full history); AGENTS.md (Codex guide)
  appeared in the repo, authored outside this assistant.
- **Commit:** pending

## AL-0017 — Final review passed; pre-commit synchronization

- **Category:** audit/review finding + implementation (docs)
- **Actor:** Claude (Claude Code), corrections requested by final review
- **What:** Final review (Codex) passed the implementation, all seven
  artifacts, the repaired MBO inventory, manifest integrity, the shared
  code/config hashes, and 135/135 tests, and requested pre-commit
  synchronization: (1) `AGENTS.md` (the Codex operating guide, previously a
  stale snapshot of the first-pass guide) synchronized with final guidance —
  implementation-audit-log added to its document map, the append-only
  audit-log maintenance rule added as its rule 21, current status updated
  from the obsolete 80-file MBO result to 85 files / 76 full-RTH sessions /
  1 partial / 31 provisional blocks, storage blocker (263.2 GB free, gate
  WARN) and remaining unresolved items carried over, and its gitignore/data
  handling wording aligned with the anchored `/data/` rule and configurable
  data root. (2) Stale "272 GB free" sentence in
  `docs/data-specification.md` §5.5 updated to the current 263.2 GB result.
  (3) This entry appended. No code, raw-data, or artifact changes; test count
  unchanged.
- **Affected files:** `AGENTS.md`, `docs/data-specification.md`,
  `docs/implementation-audit-log.md`.
- **Evidence:** full test suite re-run after edits (result recorded in the
  completion report for this pass: 135/135); `git status` confirmed no
  `data/` paths visible to Git.
- **Next required operation (post-commit):** after the initial commit exists,
  rerun `nqr data audit --part all` so every artifact envelope records the
  real initial Git SHA, then append a new entry containing that SHA and the
  regenerated artifact hashes.
- **Commit:** pending (this entry precedes the initial commit by design)

## AL-0018 — Initial commit; artifacts re-stamped with real Git SHA

- **Category:** protocol-relevant decision + artifact regeneration
- **Actor:** Claude (Claude Code), commit explicitly approved by the user
- **What:** Initial commit created (approved, not pushed):
  **`88af53d6b8da794d1c91b623df004226f59492f4`** — 50 files, 8,609 insertions;
  no `data/` paths committed. `nqr data audit --part all` rerun afterwards so
  every artifact envelope records this SHA. All decode caches hit (code,
  config, and vendor identities unchanged); manifests were re-hashed in full.
  Verified: all seven envelopes carry `git_sha`
  `88af53d6b8da794d1c91b623df004226f59492f4`, `audit_code_hash`
  `b4d7a27aabcaa4e3c7ad3bdf71f52cea27cb417bcd5f57867f457a6ef53caa40`, and
  `config_hash`
  `1bfe19bb7698b24654aa8fc69800051bc831803de4d35f15e028120e30a6fddf`.
- **Gate statuses (explicitly distinguished):**
  - `storage_gate` artifact: **FAIL** — 267.5 GB free at rerun time
    (fluctuates a few GB with system activity; previously 263.2 GB), below
    the 1000 GB required minimum.
  - **Overall MBP-1 purchase gate: WARN — do not purchase** until the new
    M.2 is installed, the data root is repointed, and `nqr data storage-gate`
    passes. Data quality itself supports the purchase.
- **Artifact statuses and SHA-256 (post-SHA-stamp generation):**
  - `storage_gate.json` FAIL `b09dccf8903a3a638b592a33e9bef47de42eb3bd6fd8d918d07eafe8109e2332`
  - `manifest_validation.json` PASS `1e9107d8779d464439499ee3f62bdd6e9da389203b0b57668f5120ec9e3d2a21`
  - `mbp1_sample_audit.json` WARN `93ba083b894f672767f93348dfca20d8ffe9c305514871b8d3279a6fa6861e6d`
  - `trades_audit.json` WARN `2201a2ec003e16b0398db5e651353cf08d86923664b9970e3313011b33bd9fc3`
  - `mbp1_trades_reconciliation.json` PASS `d63b32f49c15f63988dcc17606f16b1661822be504b0120d9a1eebb661a7e1cb`
  - `mbo_inventory.json` WARN `281d944bc5e7660e9665d152550321eaa3afc003ec6160d30e08a494c9952bba`
  - `mbo_deep_audit.json` WARN `152a348ebeee6b461216373c9b517535b19a3f78dd174be5191311bbab07c692`
- **Evidence:** 135/135 tests passing after the rerun; `git show --stat` of
  the initial commit lists no `data/` paths; working tree clean apart from
  this log entry, which is committed separately (below) so the initial
  commit's SHA — already recorded inside the regenerated artifacts — is never
  amended.
- **Commit:** this entry is included in the second commit (SHA recorded in
  the commit itself; the next log entry to touch this file should cite it).
