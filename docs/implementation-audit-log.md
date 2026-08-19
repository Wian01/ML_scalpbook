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

## AL-0019 — Data-root migration to the dedicated D: volume

- **Category:** protocol-relevant decision + implementation + artifact regeneration
- **Actor:** Claude (Claude Code), migration copy performed by the user;
  prior commits AL-0018 = `d4b3fe3`, initial = `88af53d`
- **What:** `D:\nq-research\data` (2 TB NVMe) made the canonical active data
  root. The C: tree (`C:\Users\Wian\projects\trading\ML_scalpbook\data`)
  remains untouched as the protected source pending independently reviewed
  deletion approval. No raw file on either volume was modified, renamed,
  moved, or deleted.
- **Pre-change verification:** full metadata comparison of both trees —
  **1,564 files and 42,662,762,806 bytes on each side; zero C-only, zero
  D-only, zero size mismatches**. `NQR_DATA_ROOT` confirmed unset in Process,
  User, and Machine scopes (no silent override).
- **Independent D: content validation:** manifest validation re-run against
  D: — **34/34 job directories, 788/788 files, exact sizes, exact SHA-256,
  zero missing / failed / unmanifested DBN files.**
- **Changes:** `config/data/paths.yaml` `data_root: D:/nq-research/data`;
  current-guidance docs updated to `<data_root>/...` with the D: root named
  where operational (CLAUDE.md incl. rule-5 mapping note, AGENTS.md,
  architecture.md incl. new §3a physical storage policy, data-specification.md,
  holdout-policy.md). Canonical spec untouched (verified unmodified in git;
  file present in the initial commit). Root-anchored `/data/` gitignore rule
  retained deliberately as a permanent safety net. Physical storage policy
  documented: large/regenerable artifacts (raw, normalized, QA + caches,
  samples, features, labels, datasets, holdout, model binaries, predictions,
  SHAP caches, temp files) on D: under `<data_root>`; code/config/tests/docs/
  protocol amendments/lightweight experiment metadata in the C: Git repo.
  Mapping-vs-spec note recorded in architecture §3a (canonical §45/§7 draw
  `data/` inside the repo; operational mapping only, spec unchanged). Tests:
  `test_config_paths.py` updated — repo-relative-default assumption replaced
  with configured-yaml assertions plus a guard that the committed root is
  `D:/nq-research/data`; suite now **136 passing**.
- **Full audit regeneration against D::** the data-root change altered the
  effective config hash (now
  `f27de73d2e23f3aaf6ead90721d17688c58c632d3f7620ff84b39cc9cec6ad96`),
  correctly invalidating every decode cache; all parts recomputed from the D:
  raw tree (protection not bypassed). All seven envelopes verified:
  `data_root = D:\nq-research\data`, one config hash (above), one
  `audit_code_hash`
  `b4d7a27aabcaa4e3c7ad3bdf71f52cea27cb417bcd5f57867f457a6ef53caa40`
  (unchanged — no package code changed), `git_sha = d4b3fe3...` (HEAD at
  generation; note the migration's config/doc changes were intentionally not
  yet committed, so a post-commit re-stamp run will be needed if the reviewer
  wants the migration commit's SHA inside the envelopes).
- **Results (identical to pre-migration where expected):**
  - `storage_gate` **PASS** — 2,005.5 GB free on D: (≥1,000 GB required AND
    ≥2,000 GB preferred, the latter narrowly). C: history (263.2–284.6 GB,
    FAIL) preserved in AL-0016/AL-0018.
  - `manifest_validation` PASS (34/788/0/0/0);
  - `mbp1_sample_audit` WARN, `trades_audit` WARN (unchanged findings);
  - `mbp1_trades_reconciliation` **PASS exact** — 5/5 UTC days PASS,
    session-level PASS, 19 pairs;
  - `mbo_inventory` WARN (provisional by design);
  - `mbo_deep_audit` WARN — **identical NQ results: 76 full-RTH sessions,
    1 partial, 106 initialization-artifact dates, 31 provisional blocks,
    2,005,045,979 rows, ES exclusions 56,819,215, NQ-spread exclusions
    4,952,807** — bitwise-equal aggregates across volumes confirm decode
    determinism and copy integrity.
  - **MBP-1 purchase gate: PASS — purchase unblocked.** The two-year history
    remains intentionally unpurchased; the audit treats only present data and
    nothing classifies its absence as missing (verified: coverage checks span
    observed ranges only).
- **Artifact SHA-256 (D: generation):**
  - `storage_gate.json` `c7bb5520b4484e31467686d0ac0c5f20fba20aeacaeda1befa6584e793bb722f`
  - `manifest_validation.json` `17d3692e7ca64ac0f1def92b9c079ab3bc7bdc341082dacdabc44e034d0eac3a`
  - `mbp1_sample_audit.json` `91ae06677719766c99f8ad05d10db8e0d0269c26f4a0ea4c5ad34a8965d4ff6c`
  - `trades_audit.json` `e77053a74152a9adaec87d1067bcb008c77af7fef3ec90bca098ebb7078f018e`
  - `mbp1_trades_reconciliation.json` `d5510d40fb06c04ed0681dd2043954ea16c5eb5c9f0c3bfcb983d4a3443c9936`
  - `mbo_inventory.json` `6c45bb484e791e2bdb2408209fc064fc6951c046f3b2b805e62c88147f6c5e14`
  - `mbo_deep_audit.json` `9738e04f470b40ce599da59f6b75c51fa57f18322043ad41a4394f8db05c5fdf`
- **Unresolved risks:** C: source tree deletion awaits independent review and
  explicit user action (assistants never delete it); envelope `git_sha`
  predates the migration commit (re-stamp optional post-commit); CME holiday
  calendar, crossed-burst classification, front/roll rule, MBO acquisition
  reasons, partition/holdout freezing — all unchanged from AL-0016.
- **Commit:** pending (migration changes not yet committed by instruction).

## AL-0020 — Two-year MBP-1 acquisition: provenance validation and source registry

- **Category:** data acquisition + implementation + data-quality discovery
- **Actor:** Claude (Claude Code); annual purchases made by the user;
  prior commit c74b825 (AL-0019 = pre-purchase checkpoint, unchanged)
- **What:** Read-only acquisition validation of the purchased two-year MBP-1
  corpus and construction of the source-provenance layer. No raw file was
  modified/renamed/moved/deleted; the old C: tree and the download ZIP were
  untouched; the historical qa/m0 artifacts were not overwritten.
- **Annual jobs validated** (metadata + condition + manifest re-hash):
  - `GLBX-20260817-P3KX4KXDQF` [2024-08-17, 2025-08-17): 312 DBN + 3 JSON,
    ~44.69 GB, files 2024-08-18 → 2025-08-15, all 312 condition entries
    "available"; manifest 314/314 PASS.
  - `GLBX-20260817-S9GCQWS6L8` [2025-08-17, 2026-08-17): 313 DBN + 3 JSON,
    ~68.84 GB, files 2025-08-17 → 2026-08-16; manifest 315/315 PASS;
    **10 vendor-"degraded" dates recorded** (2025-09-17, 2025-09-24,
    2025-11-28, 2026-01-31*, 2026-03-15, 2026-03-16, 2026-03-21*,
    2026-04-10, 2026-05-24, 2026-07-30; * Saturdays without files) — kept for
    session-QA classification, not excluded here.
  - Query params match the sample and frozen spec exactly (GLBX.MDP3, mbp-1,
    NQ.FUT parent → instrument_id, DBN+zstd, daily splits, pretty/map flags
    false). **Adjacency exact:** older.end == recent.start ==
    1755388800000000000; no gap, no overlap.
  - Sample job re-verified too: manifest 13/13 PASS. Total 642/642 files.
- **KEY DISCOVERY — cross-request file hashes cannot prove identity:** every
  one of the 11 overlapping sample files differs from its annual counterpart
  by 2–9 bytes (annual smaller) with different SHA-256, although both copies
  hash-match their own vendor manifests. Diagnosis: Databento batch files
  embed per-request container metadata. Proof on the Sunday pair: parsed DBN
  metadata equal, all 295,250 records byte-identical, 3-byte file diff.
  **Authoritative identity check added (record-level):** all 11 day-pairs
  decoded and byte-compared — **115,583,040 records, 100% identical**
  (artifact `mbp1_sample_overlap_record_level`, PASS). Per rule 7 the
  file-hash overlap check's requirement was changed (documented here, tests
  updated): hash mismatch now WARNs with the explanation and defers to the
  record-level gate; a sample file missing from the corpus still FAILs. The
  original FAIL run is preserved in this history; the recent annual job is
  designated canonical for the overlapping dates, subject to the independent
  review of this phase.
- **Source registry + safe selection implemented:**
  `config/data/mbp1_sources.yaml` (in the effective config hash) records
  request IDs, roles, eligibility, dataset/schema/symbology, authoritative
  start/end ns, manifest identity, overlap policy, and the sample-retention
  reason. `nqresearch/sources.py`: QA-sample-only selection for the Milestone
  0 audit (CLI `mbp1` and `reconcile` parts now registry-scoped — they no
  longer glob raw/mbp1 recursively, which would have decoded the annual
  corpus); research enumeration uses only FULL_HISTORY_CANONICAL sources;
  one file per logical daily partition; overlap between research-eligible
  sources raises ResearchOverlapError; dedup is source-level only. Result:
  **625 canonical research files, 2024-08-18 → 2026-08-16, zero sample
  leakage.** No normalization/model pipeline was built.
- **Artifacts** (`<data_root>/qa/mbp1_full_history/`; envelopes share
  code hash `9f830642090c5d025903cccaa7074baeb33e2586f2411bb098b63c41be7a95d2`,
  config hash `15c1e286ebd20ed780a2f3357b2136e06a76aa302547f6d868cb948cf2228210`,
  data_root D:\nq-research\data, git_sha c74b825 — **post-commit re-stamp
  required**):
  - `mbp1_source_inventory.json` PASS `6d49ed4690c7c204eb0bb9d622f5c8c2ca8ac460e3f5df881a4038f594cebaf3`
  - `mbp1_manifest_validation.json` PASS `88bed9667d2dc7f8fb5274a971a7ac45f0766f45fff69ce354b823a0afb11af5`
  - `mbp1_range_adjacency.json` PASS `a4635fcb49f7b35ea970ba1563851ed888671b1d5a0f88c44af263460cbfa2fd`
  - `mbp1_sample_overlap.json` WARN `28a626e60459f91348941227908a4265684bdeec92b208b82ab240b52c605960`
  - `mbp1_sample_overlap_record_level.json` PASS `66fe6305a4b82f266f0f7e77479c83c005815e7a9aef34d27218ee30a5c30871`
  - `mbp1_source_selection.json` PASS `82daf97715abf110538ecbff32d5862d454b08ba8b8022038a24a4fbb5e71d0a`
  - `storage_gate.json` WARN `eff30f4501d5801bd6752d31971e4c4c0164f861a66f00540b2d1ae522cfa302`
    (post-purchase: 1,847.3 GB free / 2,048.4 GB total — ≥1,000 GB required
    met; <2,000 GB preferred; acceptable per stated policy)
- **Tests:** 153/153 passing (18 new: registry/config-hash, adjacency,
  research-input uniqueness and loud-overlap failure, QA-only sample scoping,
  overlap comparison semantics incl. the documented WARN change).
- **Unresolved risks:** independent review of this phase pending (canonical
  designation of the overlap + the rule-7 requirement change explicitly
  flagged for that review); acquisition artifacts need post-commit re-stamp;
  vendor-"degraded" dates need session-QA classification in Milestone 2;
  storage below preferred headroom (plan normalized-data footprint before
  Milestone 2); no record-level decode/QA of the 614 non-overlap annual days
  yet (deliberately out of scope — requires separate authorization);
  holiday calendar and other AL-0016 items unchanged.
- **Commit:** pending (this phase not yet committed by instruction).

## AL-0021 — Acquisition review corrections: degraded-count fix, hardened identity gate, cohesive acquisition gate

- **Category:** audit/review finding + implementation fix + data-quality correction
- **Actor:** Claude (Claude Code); corrections requested by the independent
  acquisition review, which accepted the overall result in principle
  (record-level identity sufficient; sample stays excluded from research).
- **Correction of AL-0020 (AL-0020 preserved unchanged, append-only):**
  AL-0020 and the docs wrongly stated the older annual job's 312 condition
  entries were all "available". The saved `mbp1_source_inventory.json` shows
  **311 available + 1 degraded (2024-09-18, file present)**. Correct totals:
  **11 degraded vendor-condition dates across the annual jobs** (1 older +
  10 recent, incl. two Saturday entries without files). Root cause of the
  reporting error: a PowerShell 5.1 `.Count`-on-single-object pitfall in the
  ad-hoc summary command; the Python artifact was always correct. Docs
  updated; the source-inventory artifact now reports **WARN** (not PASS)
  when degraded condition entries exist — understood, non-blocking, pending
  Milestone 2 session QA.
- **Stale vendor-hash wording removed** from CLAUDE.md, the registry overlap
  policy, and mbp1_acquisition docstrings; accurate wording everywhere: each
  copy matches its own vendor manifest; cross-request file hashes/sizes
  differ via request/container metadata; decoded-record equality is the
  authoritative cross-request identity check. Repository-wide grep confirmed
  no remaining contradictory current-status wording (historical audit-log
  entries intentionally preserved).
- **Record-level identity check made fail-safe:** expected pairs now come
  from the validated sample manifest (never disk globs); zero expected pairs
  FAILs; missing sample/canonical files, missing or multiple canonical
  counterparts, pair-count shortfalls, record-count/dtype/byte mismatches,
  and incomplete comparisons all FAIL. Comparator injectable for tests.
- **Cohesive acquisition gate added** (`mbp1_acquisition_gate.json`): PASSes
  only when inventory (PASS/WARN) covers the registry sources, manifests
  verified, ranges adjacent, selection valid, file-level overlap is the
  explained WARN (or PASS), and record-level identity PASSes for every
  expected pair with binding to the current effective config hash, the
  acquisition code hash (mbp1_acquisition/sources/dbnio/config/filenames
  modules), and the current on-disk manifest.json SHA-256 identities.
  Observed working as intended during regeneration: the gate FAILed while
  the record-level evidence was stale and PASSed after fresh evidence.
  `nqresearch.sources.require_provenance()` gives research preparation a
  cheap mandatory check that refuses to proceed without a valid bound gate.
- **Registry strengthened:** per-source `manifest_sha256` recorded (verified
  during validation); validators enforce relative/escape-free unique paths,
  unique request IDs, role↔eligibility consistency both directions,
  start<end, and agreement with the expected specification
  (dataset/schema/symbology/stype); all included in the effective config hash.
- **Sample-leak verification repaired:** ownership now tracked explicitly per
  logical partition and leak detection compares resolved normalized paths
  (the old check compared a forward-slash registry string against a Windows
  path string and could never match). Windows-safe regression test added
  (case-insensitive path collision scenario).
- **Regenerated artifacts** (`<data_root>/qa/mbp1_full_history/`; all eight
  share code hash
  `23b29cabff1470863896611e410754031cdd92ae8b6f4b305321f97ef08dfc55`
  (audit_code_hash), config hash
  `9b077200340925bfb5da9876f34cd6350ed496038ef714f14f0f76d588ba32d6`,
  data_root D:\nq-research\data, git_sha c74b825 — post-commit re-stamp
  still required; historical qa/m0 untouched; no non-overlap decode):
  - `mbp1_source_inventory.json` **WARN** (degraded dates) `2cf649aa6410f024f63c21b751500785d934c1bc50aa55fcffa74871c42ac15c`
  - `mbp1_manifest_validation.json` PASS (642/642) `84af13625c5159e6724396c4137f4ba9d8b86ee43847cee3e8a0bca5dd50e2f7`
  - `mbp1_range_adjacency.json` PASS `bddefb0bcdaa5b2928144172cb1d1361642ad52e16b0626fee2b2a32c6032f78`
  - `mbp1_sample_overlap.json` WARN (explained) `f230355fa0afd7c732077acf3b10302c89792f634520cab45356485a0c7fe750`
  - `mbp1_sample_overlap_record_level.json` PASS (11/11 pairs, 115,583,040 records identical) `b2e6ce4ccdc869170417de94ecba14f2b32e3b90e2b64f3d34bbd411a2899469`
  - `mbp1_source_selection.json` PASS (625 files, unique partitions, zero leaks) `cd9da642d92aa77e6fe3f804f8e3b54511b54b68068bf12943045c145b1f6b05`
  - `storage_gate.json` WARN (1,847 GB free ≥1,000 required, <2,000 preferred) `778f1be3748b1f91962027d50105b7322df7ba23dbb22f8757c5dee3b1ff7d94`
  - `mbp1_acquisition_gate.json` **PASS** (all 9 checks) `464a36f7e746fa1df0a9dc80fa50ee530f9a7ca6a9836ee0ccf409fb8d14477a`
- **Tests:** 173/173 passing (20 new for registry validators, fail-safe
  record-level gate, leak regression, degraded-WARN semantics).
- **Unresolved risks:** post-commit re-stamp of qa/mbp1_full_history (will be
  AL-0022); 11 degraded dates pending Milestone 2 session QA; storage below
  preferred headroom; carried AL-0016 items.
- **Commit:** pending (awaiting commit approval).

## AL-0022 — Final review finding: provenance check must bind to current code

- **Category:** audit/review finding + implementation fix
- **Actor:** Claude (Claude Code); blocking omission identified by the final
  independent review (which otherwise confirmed the revised evidence,
  artifacts, and 173/173 tests).
- **Finding:** `require_provenance()` verified gate status, effective config
  hash, and manifest identities but NOT
  `gate["acquisition_code_hash"] == acquisition_code_hash()` — so after a
  future change to selection/comparison/provenance code, an old PASS gate
  could still authorize research preparation, contradicting the stated
  guarantee.
- **Fix:** `require_provenance()` now recomputes the current acquisition code
  hash and rejects stale-code gates; it also verifies the nine named gate
  checks (`EXPECTED_GATE_CHECKS`) are present and PASS instead of trusting
  only the top-level status, and rejects malformed gates.
  `acquisition_code_hash()` coverage broadened to all modules that materially
  define gate semantics: mbp1_acquisition, sources, dbnio, config, filenames,
  **qa.manifest, qa.status** (seven modules).
- **Evidence regeneration:** the broadened code hash invalidated the prior
  record-level binding by design; the gate FAILed until fresh evidence was
  produced (observed again live), then PASSed. Re-hash + 11 overlap pairs
  re-decoded read-only (115,583,040 records, all identical; 614 non-overlap
  days untouched; qa/m0, raw data, old C: tree, Downloads ZIP untouched).
- **Final artifacts** (all eight share envelope audit_code_hash
  `47836770...` (full value in envelopes), config hash
  `9b077200340925bfb5da9876f34cd6350ed496038ef714f14f0f76d588ba32d6`,
  data_root D:\nq-research\data, git_sha c74b825 — post-commit re-stamp
  pending as AL-0023; gate binding acquisition_code_hash
  `d50713673771ce8886f18a7cc47b6c01eac6a5a04293ffaf4395554a94ad6b76`):
  - `mbp1_source_inventory.json` WARN `15f26d16673762bc64888be2711ab8aafe880e2d67292ea62eeb3925047a0904`
  - `mbp1_manifest_validation.json` PASS `6a0c154dc8e4e0e88e0688100e4142daa3a68c27c2e6e85d0de0937a2e74d10c`
  - `mbp1_range_adjacency.json` PASS `c97f9056fe56732b3c3960eb21a7ee5af8179b9bcb27154f36f62df9e2ea0744`
  - `mbp1_sample_overlap.json` WARN `7a140b69c4aaac28158bb571dadb546d79ff81edcd4bc70e8006ff4a182f47ca`
  - `mbp1_sample_overlap_record_level.json` PASS `153ccf25d453938d6951de2a8bdf4d06374043fe0c923887ef5db4529ce2a00f`
  - `mbp1_source_selection.json` PASS `b8a0fcf49edd858bf46c7044de08852d66b1327a757e100728f5d036c5f25f18`
  - `storage_gate.json` WARN `5f585e9b1e7f27dbb3b3fdae8ecddea207ec676e7fa34533343dfe34e6c53d1c`
  - `mbp1_acquisition_gate.json` **PASS, 9/9 named checks**
    `14cec4d625da23fce3c5ba8579294af18fb549e87bececdb286df71c34e45979`
- **Tests:** **184/184 passing** (11 new require_provenance tests: valid gate
  accepted; missing gate, FAIL status, stale config hash, changed manifest
  identity, stale code hash, missing/malformed/non-PASS named checks all
  rejected). `require_provenance()` exercised against the live gate: OK.
- **Unresolved risks:** post-commit re-stamp (AL-0023); 11 degraded dates
  pending Milestone 2 session QA; storage below preferred headroom; carried
  AL-0016 items.
- **Commit:** pending (awaiting commit approval).

## AL-0023 — Acquisition commit; artifacts re-stamped with its SHA

- **Category:** protocol-relevant decision + artifact regeneration
- **Actor:** Claude (Claude Code); commit and stamping sequence explicitly
  approved by the user.
- **Commit 1:** **`6ba5d4db4f0b8a69c49c76ebff07083eb468420f`** — "Two-year
  MBP-1 acquisition: provenance registry, code-bound identity gate, safe
  source selection" (exactly the 12 reviewed files; 1,945 insertions,
  18 deletions; no data/ paths).
- **Re-stamp:** `--part mbp1-acquisition` then `--part mbp1-overlap-records`
  re-run after the commit. All eight artifact envelopes verified to record
  `git_sha = 6ba5d4db4f0b8a69c49c76ebff07083eb468420f`, shared
  `audit_code_hash 47836770ce095dc7422761d210d106ecb3f3d4dd6b5658340ebf54e1b8dce018`,
  shared `config_hash 9b077200340925bfb5da9876f34cd6350ed496038ef714f14f0f76d588ba32d6`,
  `data_root D:\nq-research\data`. The gate remained PASS throughout the
  re-stamp (its evidence binding — config, acquisition code, manifest
  identities — was unchanged; only the envelope SHA refreshed).
- **Verified after stamping:** acquisition gate **PASS with 9/9 named
  checks**; `require_provenance()` accepts the freshly stamped gate;
  record-level identity unchanged — **11/11 overlap pairs, 115,583,040
  records byte-identical**; **184/184 tests pass**.
- **Final artifact statuses and SHA-256 (stamped generation):**
  - `mbp1_source_inventory.json` WARN `64ef45658e5957d53e2a47f0aa07108227a5978994580ae9a53ee2a64016f87d`
  - `mbp1_manifest_validation.json` PASS `fa2de0fadfadb5ae3e3114ba180c98bb9be0cfa844a0e9b10611f10bdacf7170`
  - `mbp1_range_adjacency.json` PASS `74c8ad8b56f5033831d611405e17adf3e934dcca9af1eb902410b86d6d753eb3`
  - `mbp1_sample_overlap.json` WARN `85647992326e565488f3ffc8c36037dc7745f6fc055c3ce4851a5c1f70658fb2`
  - `mbp1_sample_overlap_record_level.json` PASS `13a0c40deeded87392d58d0180f1e317df76e356ff9010f470d2a698eaa6e0a1`
  - `mbp1_source_selection.json` PASS `f1e1fd042cef158398977bfb63e884dd9b62bbc7fee9b7d9dd03b7e1be4cf15d`
  - `storage_gate.json` WARN `bb47a53a9211b3523f035675d0ecde10892a4cdf686b83217cd58d7214beaaf1`
  - `mbp1_acquisition_gate.json` **PASS** `aa56b4c8fc219d2880e8cf8872ad5c5c8d89a878ebd92257c41f2fc833c78f08`
- **Untouched:** historical `qa/m0` artifacts, all raw vendor data on both
  volumes, the old C: data tree, and the D:\Downloads ZIP. Nothing pushed.
- **Commit:** this entry is Commit 2 (separate by design; Commit 1 is never
  amended so the SHA recorded inside the artifacts stays valid).

## AL-0024 — Milestone 0 closeout: cleanup, calendar, full-history coverage, roll rule, frozen MBO blocks, partition proposal

- **Category:** implementation + data-quality discovery + protocol-relevant proposals
- **Actor:** Claude (Claude Code); phase directed by user instruction from
  pushed HEAD `1c0a774e25b8c9aef157261d7d1a9d0df3c6118f`.
- **Operational cleanup verified (read-only):** the obsolete, previously
  validated C: duplicate `C:\Users\Wian\projects\trading\ML_scalpbook\data`
  no longer exists (deleted by the user after AL-0019's SAFE verdict and
  review); configured data root remains `D:\nq-research\data`;
  `require_provenance()` PASS; 3 MBP-1 + 2 trades + 31 MBO raw job dirs and
  all 7 m0 + 8 acquisition artifacts present; git clean at pushed HEAD.
  Nothing under the active D: raw tree was modified.
- **Stale current-status docs corrected:** data-spec §5.5 (storage now
  post-purchase 1,847 GB WARN, history preserved), §5.6 (re-stamp complete,
  git_sha 6ba5d4d), §6 (purchase-gate CLOSED; historical record preserved);
  architecture module/CLI inventory extended (sources, acquisition, calendar,
  rolls, coverage, closeout).
- **Authoritative CME calendar integrated:** committed snapshot
  `config/data/cme_calendar.yaml` generated by
  `scripts/generate_cme_calendar.py` from pandas_market_calendars 5.4.0
  ("CME Globex Equity"; pinned in uv.lock; content SHA-256
  `92896b7a87ade27209e477506bb91804a59a6deba5ad1bdb4c6630fca0f70afa` in the
  snapshot meta; snapshot file included in the effective config hash).
  626 trading days 2024-08-01→2026-12-31; 5 full weekday holidays
  (Christmas/New Year); 25 early closes incl. Good Friday 08:15 CT short
  sessions — validated against observed vendor data (quote-only 2025-04-18
  file; active 16 MB jobs-report 2026-04-03 file; 2026-07-03 12:00 CT close
  matching the decoded MBO span). Runtime module `nqresearch/calendar.py`;
  14 calendar tests (Good Friday, July-3 shortened, DST days, contiguity).
- **Full-history session-coverage audit built and run**
  (`qa/full_history_audit.py`, CLI `--part mbp1-coverage`, artifacts in NEW
  `<data_root>/qa/m0_closeout/`): registry-scoped to FULL_HISTORY_CANONICAL
  only, provenance-gated (require_provenance at start), streamed/chunked,
  resumable versioned caches, 100 GB disk guard. Decoded
  **5,401,913,515 records across all 625 canonical files (~432 GB decoded)**.
  **Two audit-design defects found and fixed via intermediate runs (recorded,
  not erased):** (1) first run reported 20 FAIL sessions from fabricated
  "RTH feed gaps" — file-leading initialization records with stale ts_event
  (AL-0004 semantics) landed inside neighboring sessions' RTH windows, and
  expected post-early-close halts on shortened sessions were measured as
  gaps; fixed by excluding records with ts_event < the file's query start
  (4,651 records corpus-wide) and bounding RTH statistics at each session's
  calendar close. (2) second run left 2025-01-09 as FAIL and warned on
  holiday-evening pre-open remnants; fixed by classifying essentially-zero
  RTH on calendar-normal days as NO_RTH_DATA_CALENDAR_MISMATCH (WARN,
  review item — observed: 1.3M ETH rows, no RTH, consistent with the
  2025-01-09 National Day of Mourning closure which the snapshot source does
  not encode; the snapshot was NOT hand-patched) and holiday-dated sub-100k
  row entries as pre-open remnants. Missing Good Friday 2025-04-18 classified
  WARN (session closes 08:15 CT before RTH; vendor file is
  initialization-only). Final coverage numbers: appended below on run
  completion (AL-0025 will record the final artifact set + hashes).
- **Front-contract/roll rule PROPOSED** (`nqresearch/rolls.py`; awaiting
  review): spreads excluded; per-session volume-leading outright; switches
  only at session boundaries; monotone expiry (never backward); ties retain
  incumbent; INSUFFICIENT_VOLUME persistence; no back-adjustment; switch
  records = authoritative §8 window-crossing boundaries; roll-week ±3
  sessions. Observed on real data: exactly **8 switches** (the 8 quarterly
  rolls in two years). 7 unit tests.
- **MBO blocks FROZEN** (`qa/closeout.py`; artifact `mbo_blocks_frozen.json`):
  **77 NQ sessions in 30 blocks** under calendar-aware contiguity;
  2026-07-03 reclassified COMPLETE_SHORTENED_SESSION (observed 3.5 h RTH ==
  calendar expectation), merging 2026-06-29→2026-07-06 into one block.
  MBO acquisition reasons: `UNKNOWN_NOT_RECORDED_PENDING_USER_INPUT` (user
  asked; never invented).
- **Partition proposal** (`partition_proposal.json`, **PROPOSED_NOT_ACTIVE**;
  explicitly requires human approval): DEV 2024-08-19→2025-10-31 (313
  trading days; 18 MBO sessions / 7 blocks), SELECTION 2025-11-03→2026-03-31
  (105 td; 28 / 11), HOLDOUT 2026-04-01→2026-08-14 (98 td ≈ 4.5 months,
  TENTATIVE per canonical §5.3; 31 / 11), FORWARD from 2026-08-17. Open
  review point: block 2025-10-30→11-07 spans the DEV/SELECTION boundary.
- **Known cost accepted:** the strict whole-package cache keying forced two
  full ~55-minute re-decodes for aggregation-only changes; recorded as an
  optimization candidate (scoped code-hash per cache namespace) for review —
  not changed unilaterally.
- **Tests:** 210/210 passing at this entry (calendar, rolls, closeout,
  coverage helpers added).
- **Commit:** pending (phase ends with independent review + partition
  approval before any commit).

## AL-0025 — Closeout final results and artifacts

- **Category:** artifact generation (final for the closeout phase)
- **Final coverage (third run, corrected audit):** 5,401,908,864 fresh
  records / 625 files; 516 expected sessions, **zero missing, 507 PASS /
  9 WARN / 0 FAIL**; 4,651 init records excluded; **zero mid-stream ts_event
  disorder corpus-wide**; zero zero-size trades; zero unknown flag bits;
  21,808 crossed F_LAST outright states (~35/session). All 11 degraded dates
  assessed: 7 weekday dates fully covered with normal activity; WARNs:
  7 degraded + 2025-01-09 NO_RTH_DATA_CALENDAR_MISMATCH + 2026-08-17 edge.
  Good Friday 2025-04-18 = initialization-only file (WARN). Front series:
  8 quarterly switches.
- **Artifacts** (`<data_root>/qa/m0_closeout/`; envelopes: git_sha
  `1c0a774e` (pushed HEAD; working tree carries uncommitted closeout code —
  post-commit re-stamp required), config hash `ded8fee9...` (includes the
  calendar snapshot), one code hash):
  - `mbp1_full_history_coverage.json` WARN `72112b3cc31a5f63...`
  - `mbp1_front_contract_series.json` PASS `32714e878b56ef5c...`
  - `mbo_blocks_frozen.json` PASS `a73349dac9754ab8...`
  - `partition_proposal.json` PASS (PROPOSED_NOT_ACTIVE) `471dc80558efae67...`
- **Storage forecast before Milestone 2:** free 1,847 GB. Normalized L1
  Parquet estimate for 5.4B records ≈ 160–260 GB; samples/features/labels/
  registry ≈ tens of GB; projected ≥ ~1,500 GB free after Milestone 2 —
  comfortable; re-run the storage gate before large writes.
- **Unresolved (for review):** partition approval (incl. the DEV/SELECTION-
  spanning MBO block 2025-10-30→11-07); roll-rule approval; 2025-01-09
  calendar mismatch resolution; MBO acquisition reasons
  (UNKNOWN_NOT_RECORDED pending user); crossed-state session-phase
  classification (Milestone 2); cache-scope optimization proposal;
  holdout mechanical fence (Milestone 1).
- **Commit:** pending independent review and partition approval.

## AL-0026 — Independent-review corrections to the closeout (supersedes parts of AL-0024/AL-0025)

- **Category:** audit/review finding + implementation fix + provenance correction
- **1. Roll rule made strictly causal:** front for session S now decided from
  the PREVIOUS completed eligible session's outright volumes (Databento
  previous-day-volume semantics); first corpus session UNRESOLVED/ineligible
  (no look-ahead seed); monotone expiry/ties/insufficient-volume/no
  back-adjustment preserved. Recomputed: still 8 switches, each one session
  later than the superseded same-session rule, with `decided_from_session`
  recorded (2024-09-17, 2024-12-18, 2025-03-19, 2025-06-17, 2025-09-17,
  2025-12-16, 2026-03-17, 2026-06-16). Comparison recorded (not forced):
  Tue/Wed of expiry weeks per volume-based semantics; CME customary Thursday
  roll ~8 days pre-expiry is earlier by ~3–5 sessions — expected structural
  difference.
- **2. Calendar authority corrected:** pandas_market_calendars snapshot is a
  reproducible BASELINE; new attributable official-CME override file
  `config/data/cme_calendar_overrides.yaml` (in the effective config hash)
  wins on conflict. Encoded: 2025-01-09 National Day of Mourning 08:30 CT
  close → zero expected RTH (official source references in override meta;
  observed data confirms). Other 25 early closes cross-checked
  observationally 25/25; document-level PDF verification remains open.
- **3. Coverage accounting corrected:** headline counters restricted to the
  declared range 2024-08-19→2026-08-14 (516 expected): **507 PASS, 8 WARN
  (7 degraded + 2025-01-09 OFFICIAL_SPECIAL_CLOSURE_NO_RTH), 1 expected
  Good-Friday init-only session (2025-04-18), zero unexpected missing, zero
  FAIL**; 2026-08-17 reported separately as out-of-window partial edge.
  AL-0025's "507/9 incl. edge" framing superseded.
- **4. Order-claim hardened + scope stated:** dedicated cross-file
  monotonicity check added — **0 violations**; artifact now self-describes
  as the coverage audit (NOT the full §12 QA layer) and records the
  remaining §12 fields as a mandatory Milestone 2 eligibility gate.
- **5. Provenance history corrected:** the eight qa/mbp1_full_history
  artifacts were NOT untouched during the closeout — they were regenerated
  2026-08-18 (twice) because the calendar files joined the config hash and
  the gate must re-bind; AL-0023's 6ba5d4d-stamped hashes remain the
  historical record; all eight join the post-commit re-stamp sequence.
  Also corrected: AL-0024/report implied CLAUDE.md/AGENTS.md edits in this
  phase — the git diff shows neither file changed (they were already
  current); only architecture.md and data-specification.md changed.
- **6. Partitions revised (spanning resolved):** DEV 2024-08-19→2025-11-07,
  SELECTION 2025-11-10→2026-03-31, HOLDOUT 2026-04-01→2026-08-14
  (tentative), FORWARD 2026-08-17+ (edge session ineligible). Recalculated:
  **DEV 318 td / 23 MBO sessions / 8 whole blocks; SELECTION 100 / 23 / 11;
  HOLDOUT 98 / 31 / 11; SPANNING = 0** — matching the review's expected
  counts. Mandatory `no_partition_spanning_mbo_blocks` check added (FAILs
  the proposal if non-empty; activation must be refused). All six boundaries
  validated as trading days. Still PROPOSED_NOT_ACTIVE.
- **7. Storage re-measured at report time:** **1,720.9 GB free** (WARN;
  ≥1 TB minimum met; the earlier 1,847 GB figure was stale — another D:
  directory occupies substantial space and was not touched). Milestone 2
  forecast: minus ~160–260 GB normalized Parquet + tens of GB derived →
  ~1,400–1,500 GB free projected; 1 TB minimum unchanged.
- **8. MBO acquisition reasons remain UNKNOWN_NOT_RECORDED.**
- **Artifacts** (all twelve regenerated under one config hash `0d2b2400...`,
  git_sha 1c0a774, one code hash; SHA-256 prefixes):
  m0_closeout: coverage WARN `858561ac...`, front_series PASS `4cad24b7...`,
  blocks PASS `df7bddc5...` (77 sessions / 30 blocks unchanged), partitions
  PASS `6b21584c...`; mbp1_full_history: gate PASS 9/9 `364be17d...`,
  manifest PASS `75e57aeb...`, adjacency PASS `885f78b8...`, overlap WARN
  `27e0a7dc...`, record-level PASS `af42e374...`, inventory WARN
  `dd2752c5...`, selection PASS `27cf05a0...`, storage WARN `5c3bc1c2...`.
- **Tests:** 211/211 passing (causal-roll tests rewritten incl.
  no-look-ahead proof; calendar-override test added).
- **Commit:** pending independent review; do not commit/push/activate.

## AL-0027 — Final audit corrections to the closeout (supplements AL-0026; history unchanged)

- **Category:** audit/review finding + implementation fix
- **1. Roll-timing statements corrected:** CME's OFFICIAL equity-index roll
  date is the **Monday before the third Friday**
  (cmegroup.com/trading/equity-index/rolldates.html; cited in the overrides
  meta and data-spec). Recalculated: the causal volume switches lag those
  official Mondays by **+1/+2/+2/+1/+2/+1/+1/+1 sessions** (1–2, not the
  "~3–5 vs a Thursday convention" previously stated — that Thursday claim
  had no source and is withdrawn).
- **2. Override provenance strengthened:** exact official PDF URL recorded
  (…/day-of-mourning-january-9-2024.pdf) with description corrected to
  former President Jimmy Carter; automated retrieval returned HTTP 403 on
  2026-08-18, so document identity is recorded by exact URL + title with
  `document_sha256: PENDING_MANUAL_RETRIEVAL`; obsolete holiday-calendar URL
  replaced with cmegroup.com/trading-hours.html.
- **3. Baseline document-level verification:** grouped source mapping added
  to the overrides meta (9 recurring holiday groups covering every
  exceptional session in the corpus range), all currently
  OBSERVATIONALLY_CONSISTENT_DOCUMENT_PENDING. **Because document-level
  verification is incomplete, the effective calendar, MBO blocks, and
  partition dates are explicitly FINAL-PROVISIONAL — not fully
  authoritative/frozen** (recorded in the blocks artifact and data-spec).
- **4. Calendar binding:** `calendar_identity()` added;
  `mbo_blocks_frozen.json` now binds to baseline file SHA + overrides file
  SHA + deterministic merged effective-calendar SHA
  (`ca2edfe6c2d0…`); "authoritative calendar snapshot" wording replaced by
  "versioned effective calendar assembled from baseline plus official
  overrides".
- **5. New gates + regression tests:** `partition_ranges_contiguous` check
  (DEV→SELECTION→HOLDOUT→FORWARD consecutive trading days, no gap/overlap)
  added alongside `no_partition_spanning_mbo_blocks`; tests added proving a
  synthetic spanning block FAILs the proposal, overrides changes alter the
  effective config hash, ranges are contiguous, and the real-corpus counts
  recompute to DEV 318/23/8, SELECTION 100/23/11, HOLDOUT 98/31/11,
  SPANNING 0.
- **6. Edge-session protection:** out-of-range sessions (2026-08-17) are now
  EXCLUDED from the front-contract series input; the front artifact records
  `out_of_range_excluded: [2026-08-17]` plus an eligibility note. Causal
  rule preserved.
- **7. Preserved:** 516-session accounting (507 PASS / 8 WARN / 0 FAIL /
  1 expected GF init-only / zero unexpected missing), zero cross-file
  violations, mandatory §12 Milestone 2 gate, non-spanning partitions,
  UNKNOWN_NOT_RECORDED MBO reasons.
- **All 12 artifacts regenerated** under one config hash `72013ca1…`, one
  code hash, git_sha 1c0a774 (post-commit re-stamp still pending). SHA-256
  prefixes — mbp1_full_history: gate PASS `148906df`, manifest PASS
  `e10b2c0d`, adjacency PASS `26eb858e`, overlap WARN `191aba8b`,
  record-level PASS `c9de6ffa`, inventory WARN `4713b442`, selection PASS
  `423965f8`, storage WARN `691dc972`; m0_closeout: blocks PASS `96bea022`,
  front PASS `7bb5b082`, coverage WARN `294c2ad2`, partitions PASS
  `c913c2c5` (all three gates PASS).
- **Tests:** 216/216 passing.
- **Commit:** pending independent review; do not commit/push/activate.

## AL-0027-A — Metadata and activation-safety corrections (addendum to AL-0027)

- **Category:** audit/review finding + implementation fix (metadata only; the
  12 expensive artifacts deliberately NOT regenerated — they will be
  regenerated exactly once during the agreed post-closeout-commit re-stamp,
  since these changes alter the code/config hashes)
- **Corrections:** (1) overrides yaml: `document_sha256: null` +
  `document_sha256_status: PENDING_MANUAL_RETRIEVAL` (no prose inside the
  hash field); exact official CME PDF URL and observed confirmation
  preserved. (2) Ambiguous "FINAL-PROVISIONAL" replaced everywhere with
  `PROVISIONAL_DOCUMENT_VERIFICATION_PENDING`. (3) Machine-readable
  activation state added: blocks artifact gains
  `state=PROVISIONAL_DOCUMENT_VERIFICATION_PENDING` +
  `activation_ready=false`; partition proposal gains
  `calendar_verification_state=...PENDING` + `activation_ready=false`; both
  record the three activation conditions (document verification complete;
  all structural checks PASS; explicit human approval recorded); artifact
  `status` documented as computational validity only. (4) Stale wording
  fixed: calendar.py docstring (runtime = merged baseline + overrides),
  test_calendar.py header (baseline not authoritative),
  `holiday_calendar_applied` detail ("versioned effective calendar
  (baseline + official overrides)"). (5) Tests added: activation_ready
  false while verification pending (both artifacts); deliberately
  non-contiguous partition configuration makes `partition_ranges_contiguous`
  FAIL (not just the happy path).
- **Tests:** 218/218 passing.
- **Commit:** pending independent review; artifacts on disk still carry the
  pre-addendum hashes by design until the post-commit re-stamp.

## AL-0028 — Milestone 0 closeout commit; all 12 artifacts re-stamped

- **Category:** protocol-relevant decision + artifact regeneration
- **Actor:** Claude (Claude Code); commit and re-stamp sequence explicitly
  approved by the user.
- **Closeout commit (immutable, never amended):**
  **`3c7aee5e0f240b69d136ff341b608644dafc7a52`** — "Milestone 0 closeout:
  calendar, coverage, causal rolls, MBO blocks, partition proposal"
  (17 files, 2,078 insertions, 29 deletions; no data/ paths).
- **Re-stamp:** all 12 artifacts regenerated exactly once, in dependency
  order (acquisition validation → record-level overlap → coverage + causal
  front series → MBO blocks + partition finalization). The acquisition gate
  FAILed while its evidence was stale and finished **PASS with 9/9 named
  checks** after the record-level evidence regenerated — as designed.
- **Verified invariants:** all 12 envelopes share config hash
  `95a9dd78ae8beca9f128af2aa49256fdf103d7b300c568331b7eb7af6874163d`, code
  hash `92ae81c5d85ff82cbf3141e7af3da158b0e803110124d7a780f7c56b9d06f74f`,
  and git_sha `3c7aee5e0f240b69d136ff341b608644dafc7a52`. Manifest
  validation 642/642 PASS, zero failures. Overlap 11/11 pairs,
  115,583,040 records identical. Coverage: 516 expected, **507 PASS /
  8 WARN / 0 FAIL**, zero unexpected missing, one expected pre-RTH Good
  Friday init-only session (2025-04-18). Front series strictly causal,
  8 switches, 2026-08-17 absent/excluded. MBO 77 sessions / 30 blocks.
  Partitions DEV 318/23/8, SELECTION 100/23/11, HOLDOUT 98/31/11,
  SPANNING 0; all three structural gates PASS. State
  PROVISIONAL_DOCUMENT_VERIFICATION_PENDING with activation_ready=false on
  both closeout artifacts. Storage 1,720.9 GB free (WARN — ≥1 TB minimum
  met).
- **Artifact SHA-256 (final, post-stamp):**
  - `mbp1_acquisition_gate.json` PASS `05ffeab8b48dc4e6b8f4774f1bc5e446cbc2c59d64adfaac2f7bcb45475a1541`
  - `mbp1_manifest_validation.json` PASS `878db80d43d3d74ea03cfa4aafc5a0b2b6bfafa60df32678c5e87b3e11fee60f`
  - `mbp1_range_adjacency.json` PASS `f98888f1b51c85973662aa9f0098370b6e669ca0b28ceaff3c69746b19a2b1c5`
  - `mbp1_sample_overlap.json` WARN `e1e23eebd55fd17b125c013b7fd6386568efed6361cfbcc240b902c7ccf79a9e`
  - `mbp1_sample_overlap_record_level.json` PASS `f3c0d63af760490ba36ad0e90c2e158f867c099014f0ef10bf210b441078543f`
  - `mbp1_source_inventory.json` WARN `189137a5b18ef8da576d9b901e50644e1b78d31dfdcc1f58b0040b54c1e6f2b6`
  - `mbp1_source_selection.json` PASS `2e969249a76adc7effe7d0aa18c807da8fcca101afd33727faa414142479cbfb`
  - `storage_gate.json` WARN `442d9e5d2570edc2a240b7420a4adeba0bbeda72ccf166c734f92410a67690ee`
  - `mbo_blocks_frozen.json` PASS `a1e2849f78ff6592eee989493d06b46e5123ae1a1ce71b104888036a05dcb3f3`
  - `mbp1_front_contract_series.json` PASS `4b6095e94de66e9825c80be1e9dd3491d1d23476fb5c77d2dcac3267b428136a`
  - `mbp1_full_history_coverage.json` WARN `03545b61595bf3375ab6880d4b7ce3e5d88fa61522291911e43dc3f6b9ea6687`
  - `partition_proposal.json` PASS `8c0d62b2330ec4afed6a5ada0ed53b0c91c9d968eb99e3646d48a95ce993e8ba`
- **Tests:** 218/218 passing after regeneration.
- **Unresolved:** official-CME document-level verification of the baseline
  holiday groups (all OBSERVATIONALLY_CONSISTENT_DOCUMENT_PENDING) and the
  Jan-9 PDF SHA-256 (manual retrieval; CME returns 403 to scripts).
  **Partitions remain PROPOSED_NOT_ACTIVE and unactivated**; activation
  requires document verification + structural PASS + explicit human
  approval. Raw vendor data untouched; nothing pushed.
- **Commit:** this entry is the audit-log-only second commit (two-commit
  stamping pattern; the closeout commit is never amended).

## AL-0029 — Post-closeout documentation synchronization; gitignore-test hardening

- **Category:** audit/review finding + documentation correction + test fix
- **Stale current-status material corrected** (history preserved and labeled
  pre-closeout/superseded, pointing to §6a/§6b and AL-0028): AGENTS.md
  (76+1/31 inventory and pending-calendar/roll/partition items → closeout
  state: 77/30, calendar integrated, causal roll defined, partitions
  PROPOSED_NOT_ACTIVE with activation_ready=false); CLAUDE.md ("not yet
  frozen (holiday calendar pending)" → closeout state); data-spec (§5.2
  Good-Friday WARN note, §5.4 pre-closeout inventory labels, §5.5/§5.6
  storage 1,847 → current 1,720.9 GB, artifact stamps 6ba5d4d/1c0a774 →
  current 3c7aee5e with prior stamps as history, §6 stamp reference, §7
  unresolved list rewritten to the accurate post-closeout set);
  holdout-policy.md (HOLDOUT dates now exist as a structurally valid
  proposal that remains PROPOSED_NOT_ACTIVE /
  PROVISIONAL_DOCUMENT_VERIFICATION_PENDING / activation_ready=false — no
  longer described as absent).
- **Test hardening (review finding from a read-only reviewer account where
  Git reported dubious ownership):** `test_gitignore._is_ignored()` treated
  every nonzero return code as "not ignored", letting negative assertions
  pass vacuously on Git execution failure. Now rc 0 = ignored, rc 1 = not
  ignored, anything else raises loudly with Git's stderr.
- **No semantic changes:** code/config/calendar semantics, artifacts, raw
  data, partition activation, and holdout access untouched; the 12 artifacts
  deliberately NOT regenerated. Verified after the edits: effective config
  hash and audit code hash **unchanged**
  (`95a9dd78…6874163d` / package hash stable for the artifact-relevant
  modules — docs and tests are outside both), and `require_provenance()`
  still PASSes against the live gate.
- **Tests:** full suite passing (count in the correction-commit report).
- **Commit:** this synchronization + AL-0029 as one correction commit.

## AL-0030 — Residual wording cleanup (documentation-only)

- **Category:** documentation correction (no semantic changes)
- **Corrections:** (1) AGENTS.md/CLAUDE.md closing status line now states
  that no features, labels, sampling, models, experiments, activated holdout
  partition, protected holdout dataset, or holdout opening exists yet — only
  the unactivated tentative HOLDOUT proposal. (2) data-spec §5.4: the
  "selection-bias comparison deferred until the two-year history exists"
  sentence labeled pre-closeout history; the corpus now exists and the
  comparison remains pending for Milestone 2+ (§7 item 6). (3)
  holdout-policy §1: the historical paragraph no longer implies the dates
  await coverage — coverage is established and a structurally valid proposal
  exists at the 2026-04-01 boundary, tentative/unactivated pending official
  document verification and explicit human approval. (4) "MBO blocks final"
  wording in both guides clarified to "computational closeout inventory
  (77 sessions / 30 blocks)" with activation state
  PROVISIONAL_DOCUMENT_VERIFICATION_PENDING.
- **Invariants:** documentation-only — no tests/source/config/calendar/
  artifact/raw-data/partition/holdout changes; no regeneration; canonical
  spec untouched. Verified post-edit: config hash
  `95a9dd78ae8beca9f128af2aa49256fdf103d7b300c568331b7eb7af6874163d` and
  artifact code hash
  `92ae81c5d85ff82cbf3141e7af3da158b0e803110124d7a780f7c56b9d06f74f`
  unchanged; `require_provenance()` PASS; partitions unactivated.
- **Tests:** 218/218 passing.
- **Commit:** documentation + this entry as one follow-up commit.

## AL-0031 — Milestone 1 Foundation implemented (builder work; PENDING_INDEPENDENT_AUDIT)

- **Category:** implementation (canonical §61) + protocol-relevant design
- **Gap analysis** vs §61: repo/uv/layout/Pydantic-configs/docs/protocol
  files/base tests already existed from Milestone 0 phases (reused, not
  rebuilt). Genuinely missing and now implemented: DuckDB experiment
  registry + immutable lifecycle, mechanical holdout fence, enforced
  raw-write protection, structured experiment lifecycle audit. No frozen
  protocol value, partition date, label/sample/feature/evaluation/cost
  semantics changed; configuration identities remain deterministic (config
  hash verified unchanged: `95a9dd78…6874163d`).
- **Registry** (`experiments/registry.py`, DuckDB at
  `<data_root>/registry/experiments.duckdb` + one committed lightweight
  directory per experiment): deterministic sequential IDs (EXP-0001… = §39
  trial counter); complete §37 pre-registration model (all fields required,
  extra fields forbidden); §47 reproducibility snapshot at registration
  (git SHA, python, platform, uv.lock SHA-256, config hash, code hash,
  seeds, experiment ID); spec content-hash stored at registration and
  re-verified on every transition (edited prereg.yaml ⇒ ImmutableSpecError:
  "a new hypothesis/configuration requires a NEW experiment"); lifecycle
  PLANNED→RUNNING→{PASSED,FAILED,INCONCLUSIVE,SUSPECT_AUDIT_REQUIRED} with
  all other transitions refused loudly and terminal states never rewritten;
  refusals themselves audit-recorded; append-only lifecycle audit in DB and
  per-experiment audit.json; no delete API (failed/null retained, always
  listed); no ID reuse/overwrite (existing directory or row refuses);
  transactional writes; schema_version=1 with unknown-version refusal.
  CLI: `nqr exp register|show|list|transition`. No real market experiment
  registered; tests use synthetic metadata only.
- **Holdout fence** (`holdout.py`; SENSITIVE — builder only,
  `PENDING_INDEPENDENT_AUDIT`): research range access gated on
  `config/data/partitions_active.yaml`, which DOES NOT exist — every
  request currently FAILS CLOSED; the PROPOSED_NOT_ACTIVE proposal is never
  read/inferred; with an active config, holdout overlap (inclusive
  boundaries) and any range outside DEV∪SELECTION are refused; activation
  schema requires activated=true + recorded human approver + chronological
  ranges (malformed ⇒ fail closed); NO override parameter exists anywhere;
  `holdout_opening()` always refuses pending the §7 opening workflow.
  Verified against the live repo: fail-closed today.
- **Raw-write guard** (`rawguard.py`): `assert_write_outside_raw` resolves
  the deepest existing ancestor (defeats symlink/junction aliases and `..`)
  with Windows case-folding, refusing destinations inside `<data_root>/raw`;
  enforced in `qa.report.write_artifact` and `qa.cache.run_cached`; no CLI
  command writes into raw. Real raw corpus untouched (no re-hash needed).
- **Verification:** 267/267 tests (49 new: registry schema/persistence/
  migration refusal, required fields, duplicate-ID refusal, immutability,
  full valid/invalid transition matrix, trial counting, failed-run
  retention, reproducibility identities, holdout fail-closed + boundary +
  no-override cases, raw path-escape/alias/case cases, CLI refusal paths).
  Live `require_provenance()` PASS (none of the seven gate-hash modules
  changed); config hash unchanged; the 12 Milestone 0 artifacts untouched
  (timestamps verified); raw data untouched.
- **Status:** Milestone 1 is **PENDING_INDEPENDENT_AUDIT** — not
  self-certified. Adversarial-audit handoff recorded in the phase report
  (boundary dates, missing/malformed config, path aliases, direct loader
  calls, CLI bypasses, override attempts).
- **Commit:** pending review (proposed plan in the phase report; not executed).

## AL-0032 — Independent Milestone 1 audit: CHANGES_REQUIRED (reproduced bypasses)

- **Category:** audit/review finding (independent adversarial audit of AL-0031)
- **Verdict:** CHANGES_REQUIRED despite a fully passing test suite. Reproduced
  proofs: (1) `sources.research_input_files()` returned all 625 canonical
  files while partitions were inactive — the holdout fence was advisory, not
  enforced at the research-input layer; the fence also accepted an arbitrary
  `repo_root`, a production bypass parameter. (2) ExperimentRegistry accepted
  DB/experiment-dir destinations under a synthetic `raw/` tree (env overrides
  bypassed the raw guard); `write_artifact` validated only the parent
  directory, so a path-bearing artifact name could escape. (3) Deleting
  `prereg.yaml` after registration still allowed `begin_run()` — missing
  records did not fail closed like altered records. (4) `audit.json` was
  load-extend-rewrite (not append-only as claimed) and DuckDB rollback cannot
  undo created directories; `COUNT(*)+1`/`MAX(seq)+1` allocation was not
  concurrency-safe. (5) §38 source dataset hashes and outputs were missing
  from pre-registration/storage. (6) Reporting errors: 8+8=16 files (not
  6+6), and the package source hash had changed
  (audit-measured `931b160fc08a52a9a46a91f47b55e6aa1f655dbf0b467639b3324b13da43ba1a`)
  while only the config hash was unchanged.
- **Commit:** none (working tree only).

## AL-0033 — Milestone 1 remediation of AL-0032 (still PENDING_INDEPENDENT_AUDIT)

- **Category:** implementation fix (builder); every reproduced proof is now an
  automated regression test.
- **(1) Fence enforced at the research layer:** new `nqresearch/research.py`
  is the ONLY research-loading API — explicit mandatory date range,
  mechanical fence invocation BEFORE any enumeration, fail-closed while
  `partitions_active.yaml` is absent (live integration test proves the
  default research API cannot return the 625 files). New
  `nqresearch/qa_corpus.py` gives QA/audit code explicitly named QA-only
  full-corpus enumeration; `qa/full_history_audit.py` switched to it; an
  executable call-site allowlist test fails if any non-QA module references
  the corpus enumerators. Public fence API no longer accepts any
  `repo_root`/config parameter (tests inject via private `_load_active_
  partitions_from`/`_check_range` only). Active-partition schema hardened:
  `extra=forbid` on every nested model; timezone-aware UTC
  `approved_at_utc`; durable approval identity (`approved_by` +
  `approval_reference`); mandatory binding SHAs
  (`partition_proposal_sha256`, `effective_calendar_sha256`). No active
  configuration was created. **Deliberate constraint (flagged for
  re-audit):** `sources.py` and `qa/mbp1_acquisition.py` are two of the
  seven acquisition-gate-bound modules; renaming
  `sources.research_input_*` in place would invalidate the Milestone 0
  provenance binding, so those bytes are UNCHANGED and the in-place rename
  is deferred to the next legitimate gate re-bind window — interim
  protection is the fenced research API + executable allowlist.
- **(2) Raw guard completed:** registry DB, experiment directories, and every
  record file pass the guard (env overrides included — regression test);
  `write_artifact` and cache writers validate the COMPLETED final path and
  write to the guard's resolved result (final-name traversal test); guard
  handles drive-relative `D:file` via abspath; tests added for prefix
  collisions (`rawx`), UNC prefix logic, nested junction chains, case
  aliases.
- **(3) Immutability fail-closed:** missing `prereg.yaml` refuses exactly
  like altered records; verification now also runs in `show()` and before
  execution entry; tests cover missing file, invalid YAML, changed types,
  extra fields, substituted directories.
- **(4) Honest audit trail + crash safety:** the hash-chained DuckDB
  `lifecycle_audit` table (sequence-allocated via `CREATE SEQUENCE` —
  concurrency-safe, never reused; `verify_audit_chain()` with tamper test)
  is the single authoritative append-only store; the per-experiment file is
  renamed `audit_projection.json` and self-describes as a MATERIALIZED
  PROJECTION. Registration stages files with a `.pending` marker inside the
  DB transaction; failures roll back and remove staged files (fault-injection
  test: no orphan dir, no row, sequence gap not reuse); crash-window recovery
  on open re-materializes committed rows (audited `RECOVERED_PROJECTION`),
  while a missing record WITHOUT the marker is tampering and is never
  restored. Refusals are durably recorded in their own transaction.
- **(5) §38 completed:** `source_dataset_hashes` is a required
  pre-registration field; terminal transitions accept an outputs manifest
  (stored, shown; refused pre-terminal); parent experiment references are
  validated; prereg/outputs are JSON documents so metrics/predictions can be
  added without redesign. Schema version bumped to 2 (v1 refusal test
  retained). Synthetic registrations only.
- **(6) Corrected reporting:** working tree is 9 modified tracked + 9 new
  untracked files (18 total, incl. this log and the two new loader modules).
  Config hash unchanged (`95a9dd78…6874163d`); current package source hash
  after remediation `b0f7285c896a964e998cf6b86f8188eca5dc6c9ef4247ebca5a084f51408afb8`
  (the audit-time value `931b160f…` was the pre-remediation tree). The 12
  Milestone 0 artifacts correctly retain their historical closeout code-hash
  and commit binding and were NOT regenerated; live `require_provenance()`
  PASSes because the seven acquisition-semantics modules are byte-untouched
  (verified via git status).
- **Verification:** 299/299 tests; live research API fail-closed; no active
  partition configuration exists; QA-only enumeration available solely to
  the allowlisted audit modules; raw data and all existing QA artifacts
  untouched.
- **Status:** remains **PENDING_INDEPENDENT_AUDIT** pending a fresh re-audit.
- **Commit:** pending re-audit; not executed.

## AL-0034 — Second re-audit CHANGES_REQUIRED; remediation of the seven findings

- **Category:** audit/review finding + implementation fix (builder)
- **Verdict recorded:** re-audit reproduced that
  `sources.research_input_files()` still returned all 625 files (the
  allowlist only constrained internal static call sites), that raw UTC-day
  paths are unsafe research data at session boundaries (UTC file 2026-03-31
  carries both the last SELECTION and the first HOLDOUT session), that
  activation only format-checked hashes, that provenance was not enforced in
  the research path, that chain verification/`show(verify=False)` and the
  audit.json rewrite left fail-open paths, that recovery could reconstruct
  tampered records, and that §38 identities/outputs were under-validated.
- **(1) Legacy API removed from the gate-bound module (as directed):**
  `sources.research_input_entries/files` DELETED; enumeration is now the
  private `sources._canonical_corpus_entries`, exposed only through the
  QA-named `qa_corpus` wrappers; QA callers updated
  (`qa/mbp1_acquisition.py`, `qa/full_history_audit.py`); tests prove the
  public legacy attributes are ABSENT (not merely unreferenced).
  **Consequence: the acquisition-gate code binding is now STALE by design**
  (`require_provenance()` currently refuses with "generated by different
  acquisition/provenance code") — the 12 Milestone 0 artifacts were NOT
  regenerated in this pass; the re-bind belongs to the later reviewed
  commit-and-restamp sequence.
- **(2) No raw paths as research data:** `research.py` now gates (fence,
  then `require_provenance()`) and then REFUSES with
  `ResearchLoaderNotImplementedError` — raw UTC-day paths are never returned
  to research consumers. The Milestone 2 reader contract is recorded in the
  module (internal UTC-day halo load, session_id assignment before release,
  discard of out-of-approval events, no raw-path exposure). Regression tests
  pin the real SELECTION/HOLDOUT boundary overlap and the refusal even with
  gates monkeypatched open.
- **(3) Activation bound to actual evidence:**
  `holdout._verify_activation_evidence` verifies the real SHA-256 of the
  approved `partition_proposal.json`, exact DEV/SELECTION/HOLDOUT range
  equality with it, its structural checks all PASS, artifact type, and the
  CURRENT `calendar_identity()` effective-calendar SHA. Fabricated 64-hex
  values fail (tested). The public loader applies schema + evidence; no
  injection parameters. A separate `active_partitions_sha256` research-
  configuration identity is captured in experiment reproducibility metadata
  (None while inactive) without touching acquisition semantics.
- **(4) Provenance enforced in the research path:** the single research
  entry point invokes `require_provenance()` after the fence and before
  anything else (source-inspection test).
- **(5) Chain fail-closed + single-writer:** `verify_audit_chain()` runs on
  open (before recovery) and before every registration, inspection, and
  transition; a corrupted chain blocks reopen/show/register/transition
  (tests). `show(verify=False)` removed — private `_show_unverified`
  diagnostic only. Single-writer is now EXPLICITLY enforced via an exclusive
  lock file (DuckDB shares its in-process instance, so its own lock was
  insufficient — the earlier "concurrency-safe" wording is withdrawn);
  second-open refusal tested; locks are never stolen.
- **(6) Durable crash/tamper states:** experiments carry
  `record_state` (PENDING_PROJECTION → FINALIZED) in the DB; recovery
  re-materializes ONLY committed PENDING rows (audited RECOVERED_PROJECTION
  + finalize); a FINALIZED record later deleted is tampering — never
  reconstructed, fails closed on show/use; pre-commit orphan pending
  directories are deterministically quarantined (`*.orphaned`, audited)
  and never treated as experiments. Regression tests cover each crash point.
- **(7) §38 identities validated:** `source_dataset_hashes` must be
  normalized `sha256:<64-hex>` (bare hex normalized; arbitrary strings
  fail); terminal outputs use a structured `OutputsManifest`
  (name/type/location/size/sha256 per output; explicitly empty allowed for
  synthetic/null runs; arbitrary dicts rejected). Registry schema v3.
- **Verification:** 316/316 tests. Live: legacy sources research API absent;
  research API fail-closed; no active partition configuration; config hash
  unchanged `95a9dd78…6874163d`; package hash now
  `ac1ad8cfb02cd4b29adf7ef4ef23d176b0dde935a2d538b4153c14f20affb6ad`;
  provenance STALE-BY-DESIGN as documented above; raw data and existing QA
  artifacts untouched. Working tree: 12 modified tracked + 9 new untracked.
- **Status:** **PENDING_INDEPENDENT_AUDIT**.
- **Commit:** pending re-audit; not executed.

## AL-0035 — Third re-audit CHANGES_REQUIRED (four functional + hygiene); remediation

- **Category:** audit/review finding + implementation fix (builder)
- **(1) Activation evidence rejects the live provisional proposal:**
  `_verify_activation_evidence` now additionally requires top-level
  status==PASS; the structural-check set to EXACTLY equal
  {boundaries_on_trading_days, partition_ranges_contiguous,
  no_partition_spanning_mbo_blocks} with every check PASS;
  `activation_ready == true`;
  `calendar_verification_state == DOCUMENT_VERIFIED`; and the
  official-calendar baseline verification to be ACTUALLY complete
  (overrides meta.baseline_verification.status and every holiday group
  DOCUMENT_VERIFIED) — plus the existing real-SHA/range/calendar bindings
  and the immutable approval record (partitions_active.yaml ApprovalRecord
  with approval_reference). The historical provisional proposal was NOT
  altered; regression tests prove both a synthetic proposal with the exact
  current provisional states AND the real on-disk provisional artifact are
  rejected, and that today's PENDING baseline verification fails closed.
- **(2) FINALIZED is now the LAST durable step:** registration commits the
  row as PENDING_PROJECTION, then writes the projection, verifies it exists,
  clears and verifies the pending marker, and only then commits
  record_state=FINALIZED. Failures at any point leave the row PENDING;
  reopening completes it idempotently (audited RECOVERED_PROJECTION +
  identical finalize path). A FINALIZED row with a pending marker or missing
  projection is an INCONSISTENCY that fails the registry open. Injected-
  failure regression tests: marker-removal failure, projection-write
  failure, crash-after-projection-before-FINALIZED — each reopen yields
  exactly one valid experiment, complete projection, no marker, intact
  chain; plus both inconsistency cases.
- **(3) Chain verification covers every public inspection:** `list()` and
  `trial_count()` (and therefore the CLI list/show/transition paths, since a
  corrupted chain also fails registry open) verify the chain first; tests
  prove corrupted evidence blocks list, trial_count, and the CLI operations.
- **(4) Terminal output manifests genuinely mandatory:** every
  RUNNING→terminal transition REQUIRES an explicit validated
  OutputsManifest — omission is refused, never treated as empty; synthetic
  runs pass an explicitly empty manifest. Pre-terminal `outputs` is stored
  and shown as JSON null. CLI gains `nqr exp transition --outputs
  MANIFEST_YAML`; missing/invalid terminal manifests are refused through
  the CLI (tested).
- **(5) Hygiene:** test_sources.py whitespace/EOL normalized (an
  intermediate PowerShell rewrite had introduced CRLF/BOM and mojibake in a
  registry test file — both repaired); `git diff --check` exits 0.
- **Verification:** 328/328 tests; config hash unchanged
  `95a9dd78…6874163d`; package hash
  `92d219a47d816cc310d7728e0ee234d32ed3fb401891888bc32bdc0afc695d2d`;
  provenance STALE-BY-DESIGN (unchanged from AL-0034; re-bind reserved for
  the reviewed commit-and-restamp); the 12 QA artifacts and raw data
  untouched; no active partitions; nothing committed/pushed.
- **Status:** **PENDING_INDEPENDENT_AUDIT**.

## AL-0036 — Fourth re-audit CHANGES_REQUIRED (two consistency defects); remediation

- **Category:** audit/review finding + implementation fix (builder)
- **(1) Activation evidence made internally coherent and plan-bound:**
  `_verify_activation_evidence` now requires the proposal `state ==
  APPROVED_FOR_ACTIVATION` (the reproduced PROPOSED_NOT_ACTIVE +
  activation_ready=true combination fails on state; approved+ready=false and
  approved+pending-calendar fail as contradictions). The baseline verifier
  binds the COMPLETE frozen nine-group verification plan
  (`EXPECTED_BASELINE_GROUPS`, byte-identical to the committed overrides):
  missing, renamed, duplicated, or unexpected groups fail; every
  DOCUMENT_VERIFIED group must carry attributable official-document evidence
  (source_reference + document_sha256); any declared-but-pending document
  identity in the overrides references (the real Jan-9 PDF, sha null) blocks
  activation. Human approval is now REAL, mechanically validated against the
  append-only audit log: approval_reference must name an AL-nnnn entry whose
  text cites the exact approved proposal SHA-256 — absent or unbound
  evidence fails. No activation artifact/configuration created; overrides
  yaml unchanged (config hash preserved). Tests cover every refusal listed
  by the re-audit.
- **(2) Projections made crash-consistent for ALL audit-producing
  operations:** projections now carry `event_count` + `head_hash` and are
  written by atomic temp-write-and-replace; open, recovery, and every
  verified inspection compare projection head/count/events against the
  verified DuckDB chain and rebuild atomically on any mismatch
  (missing/stale/truncated/partial = recoverable materialized-view
  condition — this supersedes AL-0035's open-blocking behavior for the
  missing-projection case; the FINALIZED+pending-marker registration
  inconsistency remains open-blocking, and missing experiment DIRECTORIES
  remain tampering, never recreated). A projection-write failure after a
  COMMITTED transition now raises the distinct
  `ProjectionRecoveryRequiredError` stating explicitly that lifecycle state
  changed — never an ambiguous failure; after an audited refusal the
  original refusal surfaces and the projection reconciles later.
  Injected-failure tests: post-terminal-commit projection failure (status
  committed; reopen reconciles; committed transition appears exactly once),
  post-refusal projection failure, stale projection on reopen, truncated
  JSON, mismatched head/count — each ends with projection == verified chain.
- **Verification:** 342/342 tests; `git diff --check` clean; config hash
  unchanged `95a9dd78…6874163d`; package hash
  `2237f8b7ae9cdf3f5f882e852c9b0633709ed5d70d9f54bcc761447e54bda59a`;
  provenance STALE-BY-DESIGN (unchanged posture); no activation config; raw
  data and QA artifacts untouched; nothing committed/pushed.
- **Status:** **PENDING_INDEPENDENT_AUDIT**.

## AL-0037 — Milestone 1 PASS; immutable commit; acquisition evidence re-bound

- **Category:** protocol-relevant decision + artifact regeneration
- **Independent audit verdict: PASS** (after four adversarial rounds,
  AL-0032/AL-0034/AL-0035/AL-0036).
- **Immutable Milestone 1 commit (never amended):**
  **`6c44ade81214bdb53dc5febbad6ad6be5525809d`** — "Milestone 1 foundation:
  immutable experiment registry and mechanical data fences" (23 files, 3,391
  insertions, 32 deletions). Pre-commit checks confirmed: no data/ path, raw
  vendor file, QA artifact, experiment database, or real experiment
  directory staged; no partitions_active.yaml exists.
- **Acquisition evidence re-bound** (eight artifacts under
  `<data_root>/qa/mbp1_full_history/`, dependency order; the gate FAILed
  while the record-level evidence carried the old code binding, then
  finished **PASS with 9/9 named checks** — as expected). All eight
  envelopes record git_sha `6c44ade81214bdb53dc5febbad6ad6be5525809d`,
  config hash
  `95a9dd78ae8beca9f128af2aa49256fdf103d7b300c568331b7eb7af6874163d`,
  package/audit code hash
  `2237f8b7ae9cdf3f5f882e852c9b0633709ed5d70d9f54bcc761447e54bda59a`,
  acquisition-code binding `d1ffb9031d48…`, data_root
  `D:\nq-research\data`.
- **Substantive results (unchanged):** manifest validation 642/642 PASS,
  zero failures; range adjacency PASS; source selection PASS; sample
  overlap explained WARN; record-level overlap **11/11 pairs,
  115,583,040 records identical**; storage 1,720.8 GB free (WARN — ≥1 TB
  minimum met). Live `require_provenance()`: **PASS**.
- **Artifact SHA-256 (final):**
  - `mbp1_acquisition_gate.json` PASS `5a5e140912e0d079dc7127cc600c36975e2497e491506e16d74dca3489e06984`
  - `mbp1_manifest_validation.json` PASS `1b8d58618ea30dcad24232ef1477a23b4b2d8bc806f4c32f11b5b98f22f48f65`
  - `mbp1_range_adjacency.json` PASS `ce20b4e6ebcf27116f72bfdf7b0f890e98aaccee394d2a22de984b295a318ce5`
  - `mbp1_sample_overlap.json` WARN `1ff7342f8322ea59133998a3559b9725325220fc52cd1b125e57a7c701f00605`
  - `mbp1_sample_overlap_record_level.json` PASS `363b4e9091d45b28220337ebb319ef74a3582be45233f00aadbc089bc272fcbd`
  - `mbp1_source_inventory.json` WARN `0dcdf591281f4aded80885157d0c209ab57688cbb23480ec8b4f4d61c2b6ba93`
  - `mbp1_source_selection.json` PASS `e507524a87bdec8f0b4d59fda24ff9bffa37fbd81c758f4c8aaf48561152cce4`
  - `storage_gate.json` WARN `a635276742a8f1b2e9f45cde11aa68cb5ee3529680ab9fa64b4d3145381f7b92`
- **Post-re-bind verification:** 342/342 tests; research access still
  refuses with PartitionsNotActiveError; legacy public
  `sources.research_input_entries/files` remain absent; no
  partitions_active.yaml exists; `git diff --check` clean.
- **Deliberately preserved:** the four historical Milestone 0 closeout
  artifacts (`qa/m0_closeout/`) were intentionally NOT regenerated — they
  remain historical closeout evidence under their original binding.
  **Partitions remain unactivated.** No raw vendor data was modified.
- **Commit:** this entry is the audit-log-only second commit (two-commit
  stamping pattern; the Milestone 1 commit is never amended).

## AL-0038 — CME calendar-document verification attempt: retrieval blocked; ALL items remain PENDING

- **Category:** data-quality/process finding (no configuration or evidence
  changes were justified; none were made)
- **Objective attempted:** retrieve official CME schedule documents for the
  nine declared holiday groups (corpus 2024-08-19 → 2026-08-14) and the
  2025-01-09 National Day of Mourning schedule, to upgrade
  PROVISIONAL_DOCUMENT_VERIFICATION_PENDING → DOCUMENT_VERIFIED with
  hash-recorded evidence under `<data_root>/reference/cme_calendar/`.
- **Result: BLOCKED.** cmegroup.com returns HTTP 403 for both the
  trading-hours page and the known Jan-9 PDF URL, with an explicit body:
  this IP is blocked for suspected scraping and CME's website Data Terms of
  Use prohibit scripted/automated retrieval (contact gcc@cmegroup.com for
  data delivery). Attempts made: Invoke-WebRequest and curl with
  browser-class headers. Per instruction and in respect of CME's stated
  terms, no further disguised automated attempts were made; no interactive
  browser is available to this environment. **No hash was inferred, no
  third-party copy substituted, and no status changed** — all nine groups
  and the Jan-9 reference remain PENDING; `activation_ready` remains false;
  the strengthened AL-0036 activation validation continues to fail closed.
- **Evidence location prepared:** `<data_root>/reference/cme_calendar/`
  created (empty; probe files containing 403 bodies were deleted — they are
  not evidence). No raw data or QA artifacts touched; artifact-generation
  code untouched (the stale restamp_note wording correction remains queued
  for the next natural touch of that code, per the push-phase note).
- **Manual action required from the researcher** (exact list in the phase
  report): interactively download the 18 per-holiday CME trading-schedule
  documents covering the nine groups (both years each, excluding post-corpus
  holidays) plus the Jan-9 2025 mourning-day schedule PDF into the evidence
  directory; verification, hashing, comparison, and status upgrades will
  then proceed in a follow-up pass.
- **Verification:** 342/342 tests (no code changes); working tree clean
  apart from this entry; nothing committed/pushed; partitions unactivated.

## AL-0039 — CME calendar evidence remediation: PA-0001 date-level policy, evidence intake, mechanical enforcement (UNCOMMITTED, PENDING_INDEPENDENT_REVIEW)

- **Category:** protocol-relevant decision (evidence-policy amendment) +
  implementation + data-quality findings + test additions/changes.
- **Trigger (officially documented):** CME GCC reply, case 04700128,
  2026-08-19 03:02:46 UTC, DKIM pass `d=cmegroup.com`, original `.eml`
  preserved at `<data_root>/reference/cme_calendar/`
  `2026-08-19_cme-gcc_no-historical-holiday-archive.eml`, SHA-256
  `67adfa61f089b3d99153d412843d3b20f1ecddae9b7541778fc7b0a6556004b0`:
  "Unfortunately we do not have an archive for previous years holidays
  calendar" (referral to the current 2026 holiday page only). This proves
  ARCHIVE UNAVAILABILITY ONLY — the blanket per-group official-document
  requirement (AL-0026/27/36) is impossible for 2024/2025 dates. **This
  amendment is a justified evidence-policy change caused by officially
  confirmed archive unavailability — NOT a claim that the missing CME
  documents were obtained.**
- **Amendment:** `docs/protocol-amendments/PA-0001-cme-calendar-evidence-policy.md`
  (first protocol amendment). Date-level states: DOCUMENT_VERIFIED /
  TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE / PENDING_EVIDENCE /
  CONFLICT_REQUIRES_REVIEW over the fixed evidence hierarchy (official CME >
  GCC correspondence [availability facts only] > observed canonical MBP-1 >
  strong/partial secondary > lower-tier corroboration > tertiary date-only).
- **Evidence intake (immutable, hash-recorded in
  `config/data/cme_calendar_evidence.yaml`):** researcher-dropped official
  evidence (GCC `.eml`; seven CME trading-hours 2026 holiday xlsx exports —
  content extracted and verified to prove the seven 2026 corpus dates'
  Equities schedules; the official Jan-9 mourning PDF, embedded Title/Author
  "CME Group", ModDate 2024-12-30, proving "US EQUITIES CLOSE at 8:30 AM
  CT" — the body does NOT print the calendar date; the 2025-01-09 binding
  is recorded as a documented inference). Scripted snapshots (36 files
  total incl. exact PNG/webp assets) of: NinjaTrader 2026 holiday hours
  (server-rendered variant; the default page is a JS shell), six AMP pages
  + their CME-Globex-attributed schedule tables, TradingView/ForexLive
  Thanksgiving-2024, Insignia Christmas-2024, CrossTrade 2025, Kibot.
  Retrieval timestamps 2026-08-19 04:03–04:06 UTC.
- **Data-quality findings:** (1) **AMP content drift CONFIRMED** — the
  Memorial Day URL now serves 2026-only assets; the expected 2025 content
  (26 May 2025 12:00 halt) is gone, so 2025-05-26 lost its strong secondary
  source (drift risk recorded on every AMP source; claims bound to exact
  downloaded hashes). (2) The 2025-07-03 12:15 vs 2026-07-03 12:00 baseline
  question is RESOLVED (2025: Thu 7/3 12:15 pre-holiday close + Fri 7/4
  12:00 holiday session, both observed exactly; 2026: Fri 7/3 IS the
  holiday, 12:00, officially documented). (3) 2025-04-18 Good Friday has NO
  usable vendor records (expected-missing pre-RTH short session) — observed
  evidence unavailable for that date, unlike 2026-04-03 (881,799 records
  ending exactly 08:15 CT). (4) ForexLive's Friday-Nov-29 wording and
  CrossTrade's broad "Closed" labels recorded as source-imprecision
  limitations (excluded/limited use), not material conflicts.
- **Resulting states (26 exceptional dates):** 8 DOCUMENT_VERIFIED
  (2025-01-09 + seven 2026 dates), 8 TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE
  (2024-11-28, 2024-12-24, 2024-12-25, 2025-09-01, 2025-11-27, 2025-11-28,
  2025-12-24, 2025-12-25), **10 PENDING_EVIDENCE** (2024-09-02, 2024-11-29,
  2025-01-01, 2025-01-20, 2025-02-17, 2025-04-18, 2025-05-26, 2025-06-19,
  2025-07-03, 2025-07-04), 0 conflicts. All nine group roll-ups
  PENDING_EVIDENCE (weakest member). **Not forced to completion.**
- **Mechanical enforcement (new/changed code):**
  `src/nqresearch/calendar_evidence.py` (NEW: matrix schema, tier gating,
  file-hash verification, observed-vs-coverage cross-check, conservative
  roll-ups, completeness, fail-safe verification state);
  `src/nqresearch/holdout.py` (activation now requires: matrix validates
  incl. evidence-file hashes + coverage cross-check; every date resolved;
  exact matrix + GCC-email hashes bound in `partitions_active.yaml` (two new
  mandatory schema fields) AND cited verbatim in the approving append-only
  audit-log entry; overrides group summaries must equal matrix roll-ups;
  Jan-9 reference hash must match the verified PDF);
  `src/nqresearch/qa/closeout.py` (activation_ready_conditions text per
  PA-0001; calendar_verification_state stamped dynamically — completeness
  never claimed on any validation failure). `config/data/`:
  `cme_calendar_evidence.yaml` NEW (matrix file SHA-256
  `b09ddae32cf46a6a6c03ba928d710237a300766959c7ff7881163a5573ebd095`);
  `cme_calendar_overrides.yaml` restructured to date-level group summaries +
  real Jan-9 PDF SHA-256
  `f169d709420a24ebe7f0ab4466ecd8961ea677cb56e9a8fc60fc43dcc9a70ac2`
  (calendar CONTENT unchanged: `effective_calendar_sha256` unchanged).
- **Tests (rule 7 note — deliberate behavioural changes justified by
  PA-0001):** NEW `tests/unit/test_calendar_evidence.py` + shared builders
  in `tests/unit/conftest.py`; `tests/unit/test_holdout_fence.py` fixtures
  rebuilt on the date-level model. Adversarial coverage: missing/changed
  email fails; email can never prove times nor support DOCUMENT_VERIFIED;
  Kibot-only and CrossTrade-only can never triangulate; missing observed
  data fails; discrepancy forces CONFLICT and blocks completeness; a source
  cited outside its declared dates fails (2026 can never verify 2024/25);
  one verified year never promotes a group (roll-up + overrides-mismatch
  tests); partial evidence stays pending and blocks activation; fabricated
  hashes/states fail; activation requires the approval entry to cite the
  exact proposal + matrix + email hashes (each omission fails); tampered
  evidence bytes fail; missing coverage artifact fails; wrong Jan-9 hash
  fails. Superseded old tests: group-level `source_reference`/
  `document_sha256` requirement replaced by per-date matrix evidence
  (test_verified_group_without_document_identity_fails →
  matrix/roll-up variants); `baseline_status` fixtures → `overrides_status`.
  The REAL committed matrix is itself under test: validates against the
  real evidence directory + coverage artifact, is incomplete with exactly
  the 10 pending dates, real overrides agree with roll-ups, real activation
  remains impossible. **Suite: 382/382 pass** (was 342).
- **Provenance consequence (reported, not repaired):** the overrides edit
  changes the effective config hash `95a9dd78…6874163d` →
  `552fbb49db2d4ae68d4246a3e41477b3deea89a9dba20e9fd0639e4e2f2a7a31`;
  `require_provenance()` now refuses (acquisition gate stale BY DESIGN).
  No QA artifact was regenerated or overwritten; the formal
  commit-and-restamp sequence is reserved for after independent approval.
  Decision recorded: the new evidence matrix is NOT added to the effective
  config hash (it gates activation via its own bound file hash; adding it
  would touch `config.py` inside the acquisition code hash) — flagged for
  reviewer confirmation.
- **Docs:** data-spec §6c NEW + §6a/§7 updates; holdout-policy activation
  preconditions; architecture (module + `<data_root>/reference/` layout);
  CLAUDE.md/AGENTS.md status. AL-0038 and all history preserved unchanged.
- **Untouched:** raw vendor data; all QA artifacts on disk; partitions
  (**no `partitions_active.yaml`**, activation_ready=false everywhere);
  HOLDOUT/FORWARD; normalization/features/labels/models; `cli.py` (the
  stale restamp_note wording fix remains queued — that code was not
  naturally touched). Evidence files were only added, never deleted/moved.
- **Unresolved risks:** 10 pending dates (listed above) have no qualifying
  independent secondary evidence; the Jan-9 PDF date binding and the xlsx
  exports' authenticity rest on documented inference/researcher attestation
  (recorded per-source); AMP URLs may drift further (claims are hash-bound);
  observed facts in the matrix are transcribed from the coverage artifact
  (mechanically re-checked at activation, but a coverage regeneration must
  reproduce identical spans).
- **Commit:** none yet (phase rule: stop for independent review before any
  commit). The commit SHA will be recorded by the entry that creates it.

## AL-0040 — Independent-review corrections to the PA-0001 evidence remediation (supersedes parts of AL-0039; AL-0038/AL-0039 text unchanged)

- **Category:** review finding + implementation fix + test additions.
  Independent read-only review reproduced AL-0039's inventory, state counts
  and tests, and required four corrections, all applied here. Append-only:
  AL-0039's superseded statements are corrected by THIS entry, never edited.
- **(1) Jan-9 PDF finding CORRECTED:** the official PDF **explicitly
  displays 'JANUARY 9, 2025'** together with 'CME GROUP US EQUITIES — CLOSE
  at 8:30 AM CT'. AL-0039's claim that the body does not print the date was
  an extraction artifact: the original pass read only the PDF's Type1 text
  operators and missed the CID-encoded header; independent visual
  inspection established the printed date, and it was then confirmed here
  byte-level by decoding the CID text through the PDF's embedded ToUnicode
  CMaps. 2025-01-09 remains DOCUMENT_VERIFIED — now on direct printed-date
  evidence, with the URL slug's '2024' year token recorded as a CME naming
  artifact. Inference wording removed from
  `config/data/cme_calendar_evidence.yaml` (source `cme-mourning-2025-pdf`
  claims `printed-date`/`eq-0830-close`), `cme_calendar_overrides.yaml`,
  and data-spec §6c. AL-0039's text stands unedited as history.
- **(2) Substantive fail-closed .eml verification:**
  `_verify_archive_unavailability()` now PARSES the actual `.eml` bytes
  (stdlib email parser) and requires: exactly one `.eml` evidence file;
  parsed From mailbox `gcc@cmegroup.com` and domain `cmegroup.com`;
  normalized Subject, UTC Date instant, and Message-ID each matching the
  matrix; a DKIM-Signature with `d=cmegroup.com`; recipient-recorded
  Authentication-Results showing DKIM pass for CME, DMARC pass for
  cmegroup.com, and SPF pass; the exact archive-unavailability sentence
  (new mandatory matrix field `body_statement`) in the normalized plain
  body; and the declared trading-hours referral URL present in the message.
  Scope stated honestly in code and matrix: this verifies the immutable
  received message plus the receiving mail system's stored authentication
  verdicts — NOT a fresh cryptographic DKIM verification. New adversarial
  tests mutate From/Subject/Date/Message-ID/DKIM/Authentication-Results
  (dkim/dmarc/spf individually)/body and **recompute the file hash**, so
  each failure is proven to come from parsed-content inconsistency, plus
  non-`.eml`-suffix and multiple-file rejections. All checks pass against
  the real GCC message (dmarc=pass header.from=cmegroup.com confirmed
  present in the real Authentication-Results).
- **(3) Coverage-artifact identity enforced:**
  `verify_observed_against_coverage()` now requires
  `meta.observed_reference.artifact_sha256` to be a valid SHA-256 AND the
  live artifact bytes to match it BEFORE any per-date observed comparison;
  missing/invalid/mismatching identities fail closed. Regression test:
  a structurally usable but byte-rewritten artifact fails on identity.
  The real artifact continues to validate with SHA-256
  `03545b61595bf3375ab6880d4b7ce3e5d88fa61522291911e43dc3f6b9ea6687`.
- **(4) Stable claim-id binding:** every source claim now carries a unique
  stable id (`SourceClaim{id,text}`); every date-level evidence reference
  binds `source + claim_id + kind`; validation rejects unknown/renamed/
  invented claim ids, duplicate ids within a source, and (as before)
  citations outside a source's `applicable_dates`. The committed matrix was
  restructured accordingly (all 20 sources, all 26 dates); adversarial
  tests cover an invented claim id on a valid source, a renamed source
  claim breaking references, and duplicate claim ids.
- **(5) `effective_config_hash()` docstring corrected:** it now accurately
  enumerates its inputs (paths + sessions + mbp1_sources parsed values,
  resolved data root, and the two calendar file hashes) instead of claiming
  "config/data/*.yaml", and documents that `cme_calendar_evidence.yaml` is
  deliberately NOT included — it gates partition activation via its own
  SHA-256 binding in `partitions_active.yaml` + the approving audit entry,
  so acquisition provenance is not coupled to evidence bookkeeping. NOTE:
  `config.py` is one of the seven acquisition-code-hash modules, so this
  docstring change moves `acquisition_code_hash` (provenance was already
  stale from the config change; re-binding remains reserved).
- **Identities after correction:** matrix file SHA-256
  `89cc29fda3bf079cfc4c853e5cacc6f10480665f6dbc247265f21ff9a8570aad`
  (supersedes AL-0039's `b09ddae3…`); effective config hash
  `2dccccbd76daeb90f021faf3ddcc65efddc1067788892ac661635b675ac0e347`
  (supersedes `552fbb49…`; still ≠ the gate's `95a9dd78…` — provenance
  stale by design); `effective_calendar_sha256` still unchanged
  (`ca2edfe6…`); GCC email SHA-256 unchanged (`67adfa61…`).
- **Verification:** full suite **401/401 pass** (was 382); all 45 evidence
  files re-verified byte-identical; states unchanged — 8 DOCUMENT_VERIFIED
  (incl. 2025-01-09), 8 TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE, 10
  PENDING_EVIDENCE, 0 conflicts; all nine recurring groups remain
  conservatively PENDING_EVIDENCE;
  PROVISIONAL_DOCUMENT_VERIFICATION_PENDING remains in force; no
  `partitions_active.yaml`; no raw data or existing QA artifact changed
  (coverage artifact hash verified unchanged); `git diff --check` clean.
- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0041 — Second-round review corrections: strict path containment + exact authentication-domain tokens (AL-0038..AL-0040 unchanged)

- **Category:** review finding + implementation fix + test additions.
  Independent review confirmed the AL-0040 corrections and reproduced two
  remaining defects, both fixed here.
- **(1) Path-containment defect (reproduced by the reviewer):** an evidence
  source declaring `../outside.bin` passed `validate_matrix()` when the
  external file's hash matched — the previous guard was a string-based `..`
  check applied only to two meta fields, not to per-file paths. Fix: shared
  Windows-safe containment resolver in `nqresearch/rawguard.py`
  (`resolve_strictly_contained` + public `is_contained`, reusing the
  existing deepest-existing-ancestor resolution and casefolded segment-wise
  comparison). It rejects `..` traversal, absolute paths, drive-qualified
  and drive-relative forms (`C:\x`, `D:file`), root-relative (`\x`, `/x`)
  and UNC paths, symlink/junction escapes, and prefix-collision directories;
  the RESOLVED path is returned and used for the actual read, so validation
  and reading can never diverge. Applied to: `meta.evidence_root` (must
  resolve to an existing directory inside the data root), every
  `EvidenceFile.file` (inside the resolved evidence root), the `.eml` path
  in `_verify_archive_unavailability()`, and
  `meta.observed_reference.artifact` (inside the data root AND specifically
  under `<data_root>/qa/`). Regression tests: `../outside.bin` WITH a
  matching SHA-256 (proving a correct hash can never legitimize an
  out-of-root file), explicit absolute path (also hash-matching),
  drive-relative, drive-qualified, root-relative (both separators), UNC,
  alias escape via symlink with junction (`mklink /J`) fallback so the test
  executes on unprivileged Windows, pure prefix-collision semantics
  (`…/root2` never inside `…/root`), a legitimate nested
  `secondary/file.html` (must keep working), an escaped `evidence_root`,
  an escaped coverage-artifact path, and a coverage artifact inside the
  data root but outside `qa/`.
- **(2) Authentication-token weakness:** the Authentication-Results checks
  used a general `cmegroup.com` substring inside the pass clauses, which a
  crafted header like `header.i=@evilcmegroup.com` or
  `header.from=cmegroup.com.evil.example` would satisfy. Fix: the DKIM pass
  clause must carry the exact boundary-anchored token
  `header.i=@cmegroup.com` and the DMARC pass clause the exact token
  `header.from=cmegroup.com` (clause-scoped, `;`-delimited; suffix/prefix
  look-alike domains can no longer match); SPF pass clause still required.
  The exact real GCC header (`dkim=pass header.i=@cmegroup.com
  header.s=CMEGDKIM1 …; dmarc=pass (p=REJECT sp=REJECT dis=NONE)
  header.from=cmegroup.com`) verifies unchanged. Four new adversarial tests
  substitute `@evilcmegroup.com` / `@cmegroup.com.evil.example` /
  `header.from=evilcmegroup.com` / `header.from=cmegroup.com.evil.example`,
  each RECOMPUTING the evidence-file hash so the failure is proven to be
  parsed-authentication inconsistency, not a stale hash.
- **Files changed:** `src/nqresearch/rawguard.py` (shared resolver +
  `PathContainmentError`), `src/nqresearch/calendar_evidence.py`
  (containment wiring + exact-token auth matching),
  `tests/unit/test_calendar_evidence.py` (TestPathContainment, 4 auth
  params). No config, matrix, overrides, or docs content changed —
  matrix SHA-256 remains `89cc29fd…a8570aad`, effective config hash remains
  `2dccccbd…5ac0e347`, GCC email `67adfa61…`, coverage `03545b61…`.
- **Verification:** full suite **418/418 pass** (was 401; +13 containment
  and +4 authentication-token tests); the real live
  matrix validates through the new containment/auth paths; all 45 evidence
  file hashes unchanged; states 8 DOCUMENT_VERIFIED / 8 TRIANGULATED / 10
  PENDING_EVIDENCE / 0 conflicts; 2025-01-09 DOCUMENT_VERIFIED; all nine
  recurring groups PENDING_EVIDENCE;
  PROVISIONAL_DOCUMENT_VERIFICATION_PENDING in force; no
  `partitions_active.yaml`; provenance stale by design; no raw data or QA
  artifact changed; `git diff --check` clean.
- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0042 — Calendar-evidence implementation committed (immutable); identities bound

- **Category:** protocol-relevant decision (approved commit) + record of
  the exact identities the review approved.
- **Independent review APPROVED** the PA-0001 calendar-evidence
  implementation (four adversarial correction rounds, AL-0038..AL-0041 all
  closed). The complete reviewed tree — 17 files including
  `docs/protocol-amendments/PA-0001-cme-calendar-evidence-policy.md`,
  `config/data/cme_calendar_evidence.yaml`,
  `src/nqresearch/calendar_evidence.py`, the holdout/closeout/rawguard/
  config changes, the rebuilt tests, and audit entries AL-0038..AL-0041 —
  is committed as the **immutable implementation commit
  `58136099d97d0d042acdeb7dbb5442b6a6d48170`** ("Calendar evidence:
  date-level verification and fail-closed activation safeguards"). This
  commit is never amended; this entry is the separate audit-log-only
  second commit (two-commit stamping pattern).
- **Pre-commit verifications:** full suite **418/418 pass**;
  `docs/canonical-spec-v1.0.md` unchanged; no data-tree path, external
  evidence file, QA artifact, experiment database, or generated experiment
  directory staged; no `partitions_active.yaml` exists; no raw vendor data
  staged or modified; `git diff --check` clean.
- **Bound identities at commit time:**
  - evidence matrix (`config/data/cme_calendar_evidence.yaml`) SHA-256
    `89cc29fda3bf079cfc4c853e5cacc6f10480665f6dbc247265f21ff9a8570aad`;
  - GCC archive-unavailability email SHA-256
    `67adfa61f089b3d99153d412843d3b20f1ecddae9b7541778fc7b0a6556004b0`;
  - coverage artifact SHA-256
    `03545b61595bf3375ab6880d4b7ce3e5d88fa61522291911e43dc3f6b9ea6687`;
  - effective config hash
    `2dccccbd76daeb90f021faf3ddcc65efddc1067788892ac661635b675ac0e347`;
  - effective calendar identity UNCHANGED
    `ca2edfe6c2d05007c35837341ac73de955d8df6fd7821410307bf7fc18a3d010`.
- **State at commit:** 8 DOCUMENT_VERIFIED / 8
  TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE / 10 PENDING_EVIDENCE / 0
  conflicts; all nine recurring groups conservatively PENDING_EVIDENCE;
  calendar verification PROVISIONAL_DOCUMENT_VERIFICATION_PENDING;
  **partitions remain inactive** (no `partitions_active.yaml`,
  activation_ready=false). **Acquisition provenance remains stale by
  design** (gate bound to config hash `95a9dd78…`): the formal
  commit-and-restamp sequence — which will also apply the queued `cli.py`
  restamp-note wording correction — is reserved for a separate review. No
  raw data or QA artifact changed. Nothing pushed.

## AL-0043 — Provenance-envelope hardening: generation cleanliness stamped centrally; reserved envelope fields protected; dirty-generation evidence rejected (UNCOMMITTED, PENDING_INDEPENDENT_REVIEW)

- **Category:** review finding + implementation fix + test additions
  (provenance-restamp PREPARATION; no artifact regenerated).
- **Findings addressed:**
  1. **Stale hard-coded note:** `cli.py` unconditionally stamped
     "Generated from an uncommitted working tree…" into acquisition
     artifacts regardless of the actual tree state — the queued
     restamp-note issue was a symptom of the envelope layer not knowing
     the Git state at all.
  2. **Dirty-tree acceptance risk (newly identified):** nothing bound
     acquisition evidence to a CLEAN COMMITTED tree — artifacts generated
     from a dirty/unborn tree carried a plausible `git_sha` (or None) and
     `require_provenance()` would accept them if code/config/manifest
     hashes matched.
  3. **Reserved-envelope overwrite risk:** `write_artifact()` merged
     `**payload` after the envelope, letting any payload silently replace
     `git_sha`, `config_hash`, `audit_code_hash`, `data_root`,
     `generated_at_utc` — the exact fields provenance trusts.
- **Remediation:**
  - `qa/report.py` is now the single authority for generation provenance:
    it determines HEAD (`_git_sha`, unborn-safe) and complete cleanliness
    (`_git_clean`: tracked + staged + untracked via `git status
    --porcelain`; any git failure = False, never a silent pass) and stamps
    machine-readable `generation_git_clean: true|false` plus a dynamically
    accurate `restamp_note` (clean: "Generated from a clean committed tree
    at the recorded git_sha."; dirty/unborn: "…NOT eligible for provenance
    acceptance…"). NO override or allow-dirty parameter exists; dirty-tree
    generation remains available for pre-commit inspection but is stamped
    ineligible.
  - `RESERVED_ENVELOPE_KEYS` defined centrally (generated_at_utc,
    nqresearch_version, git_sha, generation_git_clean, restamp_note,
    audit_code_hash, config_hash, data_root); a payload supplying any of
    them raises `ReservedEnvelopeKeyError` (explicit collision refusal —
    exposes caller bugs rather than silently preferring trusted values).
    Payloads can therefore never supply or forge the cleanliness field.
  - `cli.py`: both hard-coded restamp_note statements REMOVED (they would
    now be refused as reserved-key collisions).
  - `qa/storage.py`: payload field `data_root` renamed
    `measured_data_root` (it is the measured argument, and `data_root` is
    now reserved for the envelope).
  - `sources.require_provenance()` now additionally refuses when
    `generation_git_clean` is missing or not exactly boolean `true`
    (False/"true"/1/anything else rejected) or when the gate lacks a valid
    40-hex committed `git_sha`. The gate SHA is deliberately NOT required
    to equal current HEAD (the audit-log-only second commit legitimately
    follows generation); semantic validity continues to ride on the
    acquisition-code hash, config hash and manifest identities.
- **Tests (synthetic temporary Git repositories only; no live artifact
  touched):** clean committed repo → true + clean note; unstaged tracked
  change / staged change / untracked file / unborn repo / non-Git dir →
  false (+ ineligibility note; unborn also records git_sha null); every
  reserved key individually refused when supplied by a payload; ordinary
  payload fields still pass through; `require_provenance()` rejects
  missing cleanliness, False, "true", "True", 1, 0, None, [] and malformed
  git_sha values (None/""/"HEAD"/short/non-hex/uppercase/int); a valid
  clean-generation gate with a DIFFERENT committed SHA remains accepted
  (audit-only-commit pattern) while code/config/manifests are unchanged;
  no override/allow/dirty parameter exists on `write_artifact()` or
  `require_provenance()`.
- **Provenance consequence (intended):** live `require_provenance()` now
  refuses for an ADDITIONAL independent reason — the existing on-disk
  acquisition artifacts predate the envelope hardening and carry no
  `generation_git_clean` binding. Provenance remains intentionally stale
  until the later separately reviewed commit-and-restamp sequence, which
  must regenerate the acquisition evidence from a clean committed tree.
- **Files changed:** `src/nqresearch/qa/report.py`, `src/nqresearch/cli.py`,
  `src/nqresearch/sources.py`, `src/nqresearch/qa/storage.py`,
  `tests/unit/test_artifact_envelope.py` (NEW),
  `tests/unit/test_require_provenance.py`,
  `tests/unit/test_storage_gate.py`. `sources.py` is inside the
  acquisition-code-hash module set: `acquisition_code_hash()` moves, which
  is correct — the restamp must regenerate under the new code identity.
  No raw data, evidence file, or QA artifact changed.
- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0044 — Gate git_sha must be a REAL ancestral commit, not merely 40 hex characters (supplements AL-0043; prior entries unchanged)

- **Category:** review finding + implementation fix + test replacement.
- **Finding (format-only SHA defect):** AL-0043's `require_provenance()`
  validated `git_sha` only as 40 lowercase hex characters. A fabricated
  value such as `"b" * 40` therefore passed — it satisfies the format while
  referencing NO commit anywhere, so it proved nothing about a committed
  generation state. Worse, the AL-0043 "audit-log-only commit accepted"
  test itself used exactly such a fabricated SHA, so it demonstrated only
  that format checking ignores the value, not the claimed
  ancestor-tolerance behaviour.
- **Remediation:** new PRIVATE fail-closed helper
  `sources._verify_committed_ancestor(sha, repo_root)` using non-mutating
  Git operations: `git cat-file -e <sha>^{commit}` (object must exist AND
  peel to a commit — blobs/trees fail) and `git merge-base --is-ancestor
  <sha> HEAD` (must be an ancestor of current HEAD). Any Git execution
  failure, missing repository, unborn HEAD, nonexistent object, non-commit
  object, or non-ancestor commit raises ProvenanceError. HEAD equality is
  deliberately NOT required — an audit-log-only commit after generation
  keeps the generation commit a valid ancestor while code/config/manifest
  bindings carry semantic validity. `require_provenance()` calls the helper
  against the ACTUAL project repository (`paths.ROOT`) and gained no
  public repository-root override (exact-signature test: `data_root` +
  `registry` only); the helper root parameter exists solely for synthetic
  test repositories.
- **Tests replaced/added:** the fabricated-SHA "accepted" test is REPLACED
  by (a) a rejection test proving `"b" * 40` now refuses ("commit
  object"), and (b) a REAL-history acceptance test at the
  require_provenance level using the project's actual `HEAD~1` (a genuine
  ancestor — precisely the implementation-commit/audit-commit pattern).
  New `TestCommittedAncestorBinding` builds temporary Git repositories:
  implementation commit A → audit-only commit B → A verified to exist, be
  B's ancestor, and be accepted by the helper while HEAD is B; rejections
  for a fabricated well-formed SHA, an existing commit on a non-ancestor
  branch, blob and tree SHAs, a non-Git directory, an unborn repository,
  and a Git execution failure (subprocess monkeypatched to raise). The
  default gate fixture now records the REAL project HEAD instead of
  `"a" * 40`. Malformed-SHA format tests and the no-override signature
  test retained.
- **Verification:** full suite **460/460 pass** (was 452); live
  `require_provenance()` still refuses — first on the on-disk gate's
  missing `generation_git_clean` (legacy envelope), as intended until the
  reviewed restamp; no raw data, evidence file, or QA artifact changed; no
  `partitions_active.yaml`; `git diff --check` clean.
- **Files changed:** `src/nqresearch/sources.py`,
  `tests/unit/test_require_provenance.py`.
- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0045 — Annotated-tag object accepted as git_sha: exact object-type proof (supplements AL-0044; prior entries unchanged)

- **Category:** review finding + implementation fix + regression test.
- **Finding (commit-identity defect):** AL-0044's helper proved object type
  with `git cat-file -e <sha>^{commit}`. That form *peels* an annotated
  tag to its target commit, so an ANNOTATED TAG OBJECT's own SHA passed
  both checks and was accepted as `git_sha`, contradicting the required
  guarantee that the recorded SHA itself identifies a commit object.
- **Reproduction (this session, synthetic repo):** commit A
  `a1b50b114510bbc4418480b81462e4d434e69bf9`; annotated tag object
  `8242928e15ef2b71c877f71b0725cafeac9441b0` with
  `git cat-file -t` → `tag`; `git cat-file -e <tag-sha>^{commit}` → rc 0
  (peeled); `git merge-base --is-ancestor <tag-sha> HEAD` → rc 0. The
  pre-fix helper therefore accepted a non-commit object.
- **Remediation:** the object-type proof is now non-peeling —
  `git cat-file -t <sha>` must execute successfully AND print exactly
  `commit`. Annotated-tag objects, blobs, trees, missing objects,
  malformed output, and Git failures all refuse (the refusal message now
  reports the observed object type). The ancestry check
  (`git merge-base --is-ancestor <sha> HEAD`) runs only AFTER the exact
  type proof passes, still failing closed on any nonzero result or
  execution failure. A LIGHTWEIGHT tag remains acceptable because its SHA
  *is* the commit object's SHA — covered by its own test.
- **Tests added:** annotated-tag regression (creates commit A + annotated
  tag, asserts `cat-file -t` returns `tag`, asserts the peeling form
  `<tag-sha>^{commit}` still succeeds — pinning the defect that made this
  necessary — then asserts the helper REJECTS the tag SHA while still
  accepting commit A); lightweight-tag acceptance test. All AL-0044 tests
  preserved unchanged: genuine implementation commit accepted from a later
  audit-log-only commit, fabricated SHA, non-ancestor branch commit, blob,
  tree, non-Git directory, unborn repository, Git execution failure, and
  the public `require_provenance()` signature test (no repository
  override).
- **Verification:** full suite **462/462 pass** (was 460); live
  `require_provenance()` still refuses on the on-disk gate's missing
  `generation_git_clean` (legacy envelope), as intended until the reviewed
  restamp; acquisition-gate and coverage artifacts byte-unchanged; all 45
  evidence files unchanged; no `partitions_active.yaml`; `git diff
  --check` clean.
- **Files changed:** `src/nqresearch/sources.py`,
  `tests/unit/test_require_provenance.py`.
- **Commit:** none (stop-for-review rule); nothing pushed.
