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

## AL-0046 — Provenance restamp: acquisition evidence regenerated from a clean committed tree; require_provenance() PASSES

- **Category:** artifact regeneration + provenance re-binding (the reviewed
  commit-and-restamp sequence). All earlier entries, including AL-0038
  through AL-0045, are unchanged.
- **Immutable implementation commit:**
  `a88d51d2796fc874c2ca675aced57c3e97d29a6f` — "Provenance: clean committed
  artifact envelopes and ancestral Git binding" (8 files, +655/-13,
  containing AL-0043, AL-0044 and AL-0045). Never amended; this entry is
  the separate audit-log-only second commit.
- **Pre-regeneration state:** full suite 462/462 pass; `git diff --check`
  clean; exactly the eight reviewed paths committed; working tree verified
  COMPLETELY clean before any artifact was written, so the new envelope
  layer could legitimately stamp `generation_git_clean: true`.
- **Regeneration sequence (reviewed dependency order):**
  `nqr data audit --part mbp1-acquisition` (gate transiently FAIL while the
  record-level evidence was still bound to the previous code/config — the
  expected intermediate state), then
  `nqr data audit --part mbp1-overlap-records`, which re-decoded both
  copies of every overlap pair (the cache key includes the acquisition-code
  and config hashes, both of which had changed) and finished with the gate
  PASS.
- **Final acquisition artifacts (8), SHA-256 and status:**
  - `544d2a8b693f89262d741e0de212dde9ac4bcedd9693bf7eddc0b98920603794`
    PASS  mbp1_acquisition_gate.json
  - `c5d65d8d666ed9600fadd1203fc63e7cd53daf952697e6775ba96042c4cd5a2d`
    PASS  mbp1_manifest_validation.json
  - `92cb6062bca7c9302cc1c81624130ce932bcb97ec7069de2df4b25d35d3dc9d6`
    PASS  mbp1_range_adjacency.json
  - `6c29921ced19d5a8c6cc31f393c9569cdeae6711718c3adafa8d52d36eeaa069`
    WARN  mbp1_sample_overlap.json (file-level; explained)
  - `8d63f08d2027d1de20b30acd6741b1a6195e66ef2216fb5e7f55ef5cb63d01dc`
    PASS  mbp1_sample_overlap_record_level.json
  - `e263cf85f54caa9793aafdd048f18552c9c8a416eeff35843196520c08c503e9`
    WARN  mbp1_source_inventory.json (vendor-degraded dates)
  - `9ff5f80eb0be0f01392633b787ec20a3cb9015721550c9c11dfe09ec5adf6141`
    PASS  mbp1_source_selection.json
  - `bef7fb04b26fd2b8df365a16bfa8fc4e4cebe78713d641e6f37fdf6fd0774cd3`
    WARN  storage_gate.json (below preferred headroom, above required)
- **Shared envelope bindings — identical across all eight artifacts:**
  - `git_sha` = `a88d51d2796fc874c2ca675aced57c3e97d29a6f` (exactly the
    immutable implementation commit);
  - `generation_git_clean` = boolean `true` (not a string);
  - `restamp_note` = "Generated from a clean committed tree at the recorded
    git_sha." — dynamically produced by the envelope layer and accurate;
    the previous hard-coded "uncommitted working tree" text is gone;
  - `config_hash` =
    `2dccccbd76daeb90f021faf3ddcc65efddc1067788892ac661635b675ac0e347`;
  - `audit_code_hash` (package source) =
    `69dbf5e6b7cfa01ad30447ec6d35cf7d7e8a90a928e24cf0f63b0f096e9e589b`;
  - `data_root` = `D:\nq-research\data`; `nqresearch_version` = 0.1.0.
  The gate's `acquisition_code_hash` binding =
  `3c023be573a48195fdbf6fa0800e3248c1052fb98c4adda6a5362effc430a33c`,
  equal to the current `acquisition_code_hash()`.
- **Acquisition gate: PASS with all 9 named checks PASS** —
  inventory_completed, manifests_verified, ranges_adjacent, selection_valid,
  overlap_file_level_explained, record_level_identity,
  record_evidence_bound_to_current_config,
  record_evidence_bound_to_current_code,
  record_evidence_bound_to_current_manifests.
- **Substantive results reproduced exactly:**
  - manifest validation **642/642 files checked, zero failures**, zero
    unmanifested and zero zero-size files across all three jobs
    (P3KX4KXDQF 314/314, S9GCQWS6L8 315/315, N8HD86YKNS 13/13);
  - record-level overlap **11/11 pairs, 115,583,040 records compared, all
    identical** (PASS);
  - range adjacency PASS (the two annual jobs exactly adjacent, zero
    issues);
  - source selection PASS: 625 research files, 2 canonical owners, unique
    partitions, **zero sample files leaked into the research input** and
    zero partitions owned by non-eligible sources;
  - inventory WARN solely from the 11 understood vendor-degraded dates
    (1 in P3KX4KXDQF: 2024-09-18; 10 in S9GCQWS6L8), zero metadata
    problems, all manifest hashes matching the registry;
  - sample-overlap file-level WARN remains the documented expected result
    (cross-request DBN container metadata differs by design; the
    record-level comparison is the authoritative identity check);
  - storage WARN: 1,720.8 GB free — **above the 1,000 GB required
    minimum**, below the 2,000 GB preferred headroom.
- **Live `require_provenance()` PASSES** with HEAD at the implementation
  commit: gate PASS, `git_sha` a88d51d2…, `generation_git_clean` true — the
  first successful provenance acceptance since the envelope hardening.
- **Post-regeneration verification:** full suite **462/462 pass**; raw
  vendor data unchanged (1,453 files, newest mtime 2026-08-17, i.e.
  untouched by this session); all 45 calendar evidence files unchanged
  (GCC email still `67adfa61…`); evidence matrix still `89cc29fd…`;
  coverage artifact still `03545b61…`; no `partitions_active.yaml`; no
  HOLDOUT/FORWARD access; no normalization/features/labels/datasets/samples
  directories exist; no data path is tracked in Git.
- **The four historical `qa/m0_closeout/` artifacts were deliberately
  PRESERVED and verified byte-identical** to their pre-run hashes:
  `a1e2849f…` mbo_blocks_frozen.json, `4b6095e9…`
  mbp1_front_contract_series.json, `03545b61…`
  mbp1_full_history_coverage.json, `8c0d62b2…` partition_proposal.json.
  They remain historical evidence of the closeout and intentionally carry
  the older envelope (no `generation_git_clean` field); regenerating them
  is a separate reviewed decision.
- **Partitions remain INACTIVE** (`activation_ready=false`, no
  `partitions_active.yaml`); the calendar evidence state is unchanged
  (8 DOCUMENT_VERIFIED / 8 TRIANGULATED / 10 PENDING_EVIDENCE / 0
  conflicts, PROVISIONAL_DOCUMENT_VERIFICATION_PENDING). No raw or evidence
  data changed.
- **Commit:** this entry is the audit-log-only second commit; nothing
  pushed.

## AL-0047 — PA-0002 research-eligibility quarantine of the ten evidence-pending sessions (UNCOMMITTED, PENDING_INDEPENDENT_REVIEW)

- **Category:** protocol-relevant decision (evidence-policy *disposition*,
  not an evidence change) + implementation + test additions. All earlier
  entries, AL-0038 through AL-0046, are unchanged.
- **Decision implemented:** the ten `PENDING_EVIDENCE` dates — 2024-09-02,
  2024-11-29, 2025-01-01, 2025-01-20, 2025-02-17, 2025-04-18, 2025-05-26,
  2025-06-19, 2025-07-03, 2025-07-04 — are marked **research-ineligible
  (quarantined)** under canonical §50's allowed *"predefined
  holiday/partial-session rule"*, machine-readable reason code
  `PREDEFINED_HOLIDAY_PARTIAL_SESSION_RULE`, defined in advance of any
  feature, label, model or result.
- **TRUTH PRESERVED (mandatory review refinement):** no evidence state was
  changed or upgraded. All ten remain `PENDING_EVIDENCE` in
  `cme_calendar_evidence.yaml`; no evidence claim, file, hash, tier or
  hierarchy was touched; **no "quarantined" value was added to
  `EVIDENCE_STATES`** (regression-tested); the effective calendar remains
  explicitly PROVISIONAL and is never relabelled `DOCUMENT_VERIFIED`.
  `cme_calendar_overrides.yaml` was deliberately left byte-unchanged — its
  `PROVISIONAL_DOCUMENT_VERIFICATION_PENDING` summary is still the truthful
  one, and the verifier now REQUIRES exactly that value under a quarantine
  disposition.
- **Rationale:** with no obtainable official schedule, the observed corpus
  agrees only with our own baseline calendar; a baseline error would
  propagate self-consistently through session assignment, RTH windowing,
  labels and evaluation without ever surfacing. Quarantine costs 8 of 317
  observed DEV sessions (2.5%) and preserves PA-0001's threshold instead of
  opening it with an exception. Ten calendar exceptions are quarantined but
  only **eight observed sessions** are lost: 2025-01-01 is not a CME trading
  day, and 2025-04-18 closes 08:15 CT before the 08:30 RTH open and has no
  usable vendor records — neither could ever have produced an RTH sample.
- **New:** `docs/protocol-amendments/PA-0002-research-eligibility-quarantine.md`;
  `config/data/research_eligibility.yaml` (strict schema, extra fields
  forbidden, unique + ascending dates, every entry
  `research_eligible: false`, bound to evidence-matrix SHA-256
  `89cc29fd…a8570aad`, with non-negotiable semantics: research use and all
  window crossing FORBIDDEN, state reset mandatory, causal roll series must
  NOT consume the mask, zero MBO blocks quarantined, HOLDOUT sealed);
  `src/nqresearch/eligibility.py` (fail-closed loading/validation, session
  masking, `eligible_sessions_in_range`, `assert_window_session_local`,
  `next_eligible_session`, `requires_state_reset`,
  `verify_structural_quarantine_invariants`; session IDs only, never raw
  paths, no override/allow-quarantined parameter);
  `tests/unit/test_eligibility.py`.
- **Changed:** `calendar_evidence.py` — added
  `resolve_activation_disposition()` plus `conflict_dates()`/`pending_dates()`
  and the states `DISPOSITION_EVIDENCE_COMPLETE`,
  `DISPOSITION_PENDING_DATES_QUARANTINED`,
  `CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED`. Semantics: verified and
  triangulated remain evidence-complete; **`CONFLICT_REQUIRES_REVIEW` always
  blocks and can never be resolved by quarantine**; a pending date may be
  dispositioned only if it appears exactly in the bound policy and every
  pending date must be covered — extra, missing or substituted dates fail
  closed, so a verified/triangulated date can never be silently quarantined.
  `holdout.py` — `ActivePartitions` gains mandatory
  `research_eligibility_sha256`; activation now resolves the disposition,
  verifies the policy binds the committed matrix, runs the structural
  invariants, requires the bound policy hash, requires the overrides summary
  and the proposal `calendar_verification_state` to match the disposition
  exactly, and requires the approval audit entry to cite the policy hash as
  well. `config.py` — `research_eligibility.yaml` file hash added to
  `effective_config_hash()` (it determines which sessions any derived
  dataset may contain, so it is research-reproducibility identity), with the
  docstring updated to enumerate inputs accurately. `research.py` — `_gate`
  additionally validates the policy; new gated
  `research_eligible_sessions()` filters quarantined sessions so a broad DEV
  request still works; M2 contract records the mask requirement.
  `qa/closeout.py` — activation conditions reworded for PA-0001+PA-0002.
- **Structural invariants proven mechanically against the real artifacts
  (all fail-closed regression-tested):** every quarantined date lies in DEV;
  none is in SELECTION or HOLDOUT; none is a partition boundary; **none is
  an MBO session; none lies inside any MBO block span** (earliest block
  starts 2025-08-18, after every quarantined date); none is a causal-roll
  `decided_from_session`. Real-corpus invariants confirmed unchanged:
  partition trading days DEV 318 / SELECTION 100 / HOLDOUT 98; observed DEV
  sessions 317 before quarantine and **309 eligible after**; coverage **516
  expected sessions**; MBO **77 sessions in 30 blocks**; **zero** spanning
  blocks; **eight** causal switches. 2025-06-19 remains recorded
  `roll_week=true` in the data-level series while excluded from research
  sampling; `rolls.py` is regression-tested to never reference eligibility.
- **Window/state rules enforced:** no research sample for a quarantined
  session; no feature, label, sample or evaluation window may span more than
  one session (so none can cross a quarantined session or an early close);
  rolling state must reset at the next eligible session — verified for every
  successor, including the consecutive 2025-07-03/2025-07-04 pair whose next
  eligible session is **2025-07-07**. Adjacent eligible sessions are NOT
  excluded, because the CME trading day begins at 17:00 CT the prior
  calendar day and all V1 horizons (≤15 min + δ) are session-local; the
  policy records that any future pre-registered feature using prior-session
  state requires an explicit policy review and may not silently consume the
  successor session.
- **Provenance consequence (expected and honest):** adding
  `research_eligibility.yaml` to the effective config hash, plus the
  `config.py`/`sources.py`-adjacent code edits, moves both the config hash
  and the acquisition-code hash, so `require_provenance()` refuses again
  until the next separately reviewed commit-and-restamp sequence. The eight
  acquisition artifacts and the four historical `qa/m0_closeout/` artifacts
  were NOT regenerated in this phase.
- **Pilot recommendation recorded (not activated, nothing normalized):**
  **October 2025** is the preferred initial one-month Milestone 2 pilot — no
  quarantined date, fully inside DEV, away from SELECTION/HOLDOUT, with MBO
  lab sessions available for reconstruction validation. **MBO-BLK-008 spans
  2025-10-30 → 2025-11-07** and is therefore not an October-only block: the
  pilot plan must either exclude it from block-level validation or extend
  the QA-only validation window to 2025-11-07 without changing the defined
  research month.
- **Verification:** full suite **528/528 pass** (was 462); `git diff --check`
  clean. No real artifact regenerated; no raw vendor data, evidence file or
  QA artifact changed; **no `partitions_active.yaml`**; proposal remains
  `PROPOSED_NOT_ACTIVE` with `activation_ready=false`; no HOLDOUT/FORWARD
  access; no normalization, feature, label or model work.
- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0048 — Independent-review remediation of PA-0002: reset semantics, strict policy schema/lifecycle, session-ID validation, validated-policy path, both-branch activation coherence, structural-artifact binding (supersedes parts of AL-0047)

- **Category:** review findings + implementation fixes + test additions.
  AL-0047 and all earlier entries are unchanged; the corrections below
  supersede specific AL-0047 statements.
- **CORRECTION TO AL-0047 (overstatement):** AL-0047 stated that state reset
  was "verified for every successor". That was wrong. The reviewer
  reproduced `requires_state_reset("2025-01-02") == False` and
  `requires_state_reset("2025-04-21") == False`, because the implementation
  only inspected the immediately preceding OBSERVED session and therefore
  missed quarantined CALENDAR dates that have no observed session
  (2025-01-01 New Year's Day; 2025-04-18 Good Friday). Reset detection now
  additionally returns true when ANY quarantined calendar date falls
  chronologically between the preceding observed session and the current
  one. Regressions added: 2025-01-02 true, 2025-04-21 true, 2025-07-07 true
  after the consecutive July pair, every observed quarantined-session
  successor true, ordinary session false, first observed corpus session
  true, and a coherence test asserting `next_eligible_session()` and
  `requires_state_reset()` can never disagree for any quarantined date.
- **Session-ID fail-open (reproduced):** `is_research_eligible("not-a-date")`
  returned True, as did whitespace-padded strings, timestamps, ints and —
  most dangerously — `datetime` objects, which subclass `date` and whose
  `.isoformat()` silently missed the mask. Added ONE canonical parser
  `parse_session_id()` used by every public entry point; it accepts only an
  exact `datetime.date` (a `datetime` is refused) or canonical
  `YYYY-MM-DD`, and rejects malformed/padded/non-canonical strings,
  timestamps, ints, bools, None and arbitrary objects.
  `assert_window_session_local()` additionally refuses canonical-but-unknown
  sessions. Coverage-artifact session IDs are validated canonical, unique
  and ascending before being used as the observed universe.
- **Schema fail-open (reproduced):** the policy accepted arbitrary status,
  id, amendment path, version 999, arbitrary QA semantics,
  `prior_session_state_features_require_policy_review=false`,
  `VENDOR_CORRUPT_SESSION` as a PA-0002 reason,
  `evidence_state_at_policy_time=DOCUMENT_VERIFIED`, and numeric `0` for
  `research_eligible`. The schema is now PA-0002-SPECIFIC: exact
  `Literal` policy id, amendment path, QA/research/window semantics, reason
  code `PREDEFINED_HOLIDAY_PARTIAL_SESSION_RULE` and evidence state
  `PENDING_EVIDENCE`; `policy_version` must be a plain int exactly 1 (bool
  and string coercion refused); `research_eligible` must be strict boolean
  `false` (`0`, `"false"`, `None`, `[]` refused); every mandated boolean is
  strict; policy id, canonical basis, rationale and per-date notes must be
  non-blank.
- **Explicit policy lifecycle added:** `PROPOSED_PENDING_INDEPENDENT_REVIEW`
  → `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL` → `APPROVED_FOR_ACTIVATION`.
  **Activation accepts ONLY the approved state**, so a proposed or merely
  implemented policy always blocks even against a fabricated
  activation-ready proposal. The live policy is deliberately set to
  `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL` and is **NOT approved** in this
  phase. Synthetic fixtures now use real PA-0002 constants and legitimate
  lifecycle states instead of an arbitrary `SYNTHETIC` placeholder.
- **Validated production path:** new `load_validated_policy()` verifies the
  strict schema at the committed fixed path, the exact evidence-matrix SHA
  binding, matrix/policy date-set consistency (which also guarantees no
  conflict is dispositioned) and the caller's permitted lifecycle states.
  It is now used by calendar verification-state generation, research gating
  (`research._gate` no longer relies on `load_policy()`), eligibility
  enumeration and activation. `current_calendar_verification_state()` falls
  back to the ordinary provisional/pending state when the binding is stale
  or the policy malformed — regression-tested with a stale binding.
- **Both-branch activation coherence:** the eligibility-policy SHA is now
  compared in BOTH dispositions (previously only under quarantine), and the
  proposal's `calendar_verification_state` must equal the state implied by
  the computed disposition in BOTH branches (evidence-complete → exact
  complete state; quarantine → exact provisional-quarantined state).
- **Structural evidence bound by identity:** `ActivePartitions` gains
  mandatory `coverage_artifact_sha256`, `mbo_blocks_sha256` and
  `front_contract_series_sha256`. At activation the actual bytes are hashed
  and compared, the artifact type/status and required internal keys are
  validated, and this happens BEFORE any content is trusted — so a modified
  MBO/front-series artifact can no longer make an unsafe quarantine look
  safe. A single truth is enforced for coverage: the identity bound in the
  active configuration must equal the identity the evidence matrix already
  verified. The approval audit entry must now cite all seven identities.
  `verify_structural_quarantine_invariants()` no longer merely reports the
  artifact's own counts — it ASSERTS coverage 516, DEV/SELECTION/HOLDOUT
  318/100/98, observed DEV 317, eligible DEV 309, excluded 8, MBO 77/30,
  spanning 0 and 8 causal roll switches.
- **Machine-readable closeout bindings:** `qa/closeout.py` now emits a
  `research_eligibility_binding` block on both the MBO-block and
  partition-proposal payloads (evidence disposition, provisional calendar
  state, policy SHA-256 and lifecycle state, quarantined-date set and its
  deterministic digest, 10 quarantined dates, 8 excluded observed DEV
  sessions, 309 eligible, and the structural-quarantine facts) plus named
  checks: `eligibility_policy_bound_to_evidence_matrix`,
  `pending_dates_exactly_covered`, `quarantine_structurally_safe`,
  `structural_artifact_identities_valid`,
  `calendar_disposition_truth_preserved`. The block is fail-safe (any
  validation failure records a FAIL check, never a silent success), and the
  artifacts remain `PROPOSED_NOT_ACTIVE` / `activation_ready=false` /
  explicitly provisional. **The real artifacts were NOT regenerated.**
- **Vacuous test removed (rule 7):** the assertion ending in `or True` in
  `tests/unit/test_eligibility.py` is deleted and replaced with executable
  checks that public eligibility APIs return only canonical session-ID
  strings or booleans, never `Path` objects, that no path-returning or
  raw-file enumeration API exists, and that the research loader stays
  fail-closed while partitions are inactive.
- **Files changed:** `src/nqresearch/eligibility.py` (rewritten),
  `src/nqresearch/holdout.py`, `src/nqresearch/calendar_evidence.py`,
  `src/nqresearch/research.py`, `src/nqresearch/qa/closeout.py`,
  `config/data/research_eligibility.yaml` (lifecycle state only — the ten
  dates, reason codes and evidence states are unchanged),
  `tests/unit/test_eligibility.py`, `tests/unit/test_holdout_fence.py`,
  `tests/unit/conftest.py`. No earlier test was weakened or deleted to make
  anything pass; two fixtures were corrected (the synthetic coverage
  artifact now carries `status`/`n_expected_complete_sessions`, and the
  synthetic proposal now declares the exact complete state) because the
  new checks are stricter, and one test's expectation was updated from the
  removed "pending blocks unconditionally" semantics to the PA-0002
  "pending-but-unquarantined blocks" semantics.
- **Truth preservation re-verified:** all ten evidence states remain
  `PENDING_EVIDENCE`; `EVIDENCE_STATES` still contains no quarantine value;
  `cme_calendar_evidence.yaml` and `cme_calendar_overrides.yaml` remain
  byte-unchanged; the calendar state is the provisional
  `PROVISIONAL_PENDING_DATES_QUARANTINED` and is never `DOCUMENT_VERIFIED`.
- **Verification:** full suite **686/686 pass** (was 528); `git diff
  --check` clean; no real artifact regenerated; no raw vendor data or
  evidence file changed; **no `partitions_active.yaml`**; no HOLDOUT/FORWARD
  access; no normalization, feature, label or model work.
- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0049 — Second-round PA-0002 remediation: pre-coercion strict types, candidate-aware closeout bindings, per-artifact/envelope acceptance, lifecycle API hardening

- **Category:** review findings + implementation fixes + test additions.
  AL-0047, AL-0048 and all earlier entries are unchanged.
- **(1) Pydantic coercion fail-open (reproduced):** the semantics
  after-validator inspected values Pydantic had ALREADY coerced, so
  `rolling_state_reset_... = 1`, `prior_session_state_... = "true"`,
  `causal_roll_series_consumes_eligibility = 0`, `holdout_sealed = "true"`
  and `n_mbo_blocks_quarantined = "0"` were all accepted. Every semantic
  boolean is now `StrictBool`, the block count and `policy_version` are
  `StrictInt`, and `research_eligible` is `StrictBool` plus an identity
  check — so numeric, string, null, float and container representations are
  refused BEFORE coercion even when Python would equate them to the
  mandated value. Adversarial parameterised tests cover every boolean and
  integer field against `0, 1, "true", "false", "0", "1", None, [], {},
  1.0, 0.0` (the legitimate value is excluded per field, and a positive
  test proves correct strict values still parse).
- **(2) Stale self-validation of generated output (reproduced):** a
  synthetic one-session candidate from `freeze_mbo_blocks()` reported
  `n_sessions_final = 1` while embedding
  `structural_quarantine.n_mbo_sessions = 77` and claiming
  `structural_artifact_identities_valid = PASS`, because
  `_quarantine_binding()` read the REAL on-disk closeout artifacts instead
  of the candidate being generated. Closeout generation is now
  candidate-aware: `_policy_binding_core()` carries only config-level facts;
  `_block_stage_binding()` describes the CANDIDATE blocks and hashes only
  the source artifact that stage actually consumed; `_proposal_stage_binding()`
  derives every structural fact from the candidate blocks passed in plus the
  candidate partition counts being produced, never from a prior
  `partition_proposal.json`. Full structural safety is not provable while
  freezing blocks, so it is explicitly **DEFERRED (WARN)** at that stage
  instead of falsely PASS, with a narrower
  `quarantine_disjoint_from_candidate_mbo_blocks` check that IS provable
  there. `structural_artifact_identities_valid` is PASS only when real
  source bytes were hashed and those hashes are recorded machine-readably.
  `propose_partitions()` gained `mbo_blocks_artifact_sha256` and the CLI now
  hashes the just-written MBO-block artifact and passes it, so the proposal
  binds the exact bytes it was generated against, alongside the coverage and
  front-series identities activation later requires.
- **(3) Per-artifact acceptance and envelope integrity:** the generic
  PASS-or-WARN rule is replaced by per-artifact permitted statuses —
  coverage WARN (its understood status), MBO blocks PASS, front series PASS
  — and activation-bound artifacts must now carry a trustworthy provenance
  envelope: `generation_git_clean` exactly boolean true, a real ancestral
  commit SHA of the actual project repository, the current effective config
  hash, the current package/audit code hash, correct artifact type and
  required schema keys. **This correctly makes the historical closeout
  artifacts activation-INELIGIBLE** until the later reviewed clean-tree
  regeneration — asserted by a test against the real on-disk artifact.
  Activation additionally requires the approved PROPOSAL to embed the same
  structural identities the active configuration binds (one truth, not two).
- **(4) Lifecycle API hardening:** the public
  `load_validated_policy(..., allowed_states=...)` relaxation is removed.
  The injectable core is now private (`_load_validated_policy`, test-only)
  behind three intent-specific entry points:
  `load_policy_for_reporting()` (any well-formed lifecycle),
  `load_policy_for_activation()` and `load_policy_for_research()` (both
  require exactly `APPROVED_FOR_ACTIVATION`). Signature tests prove no
  public eligibility or research function exposes an allowed-state,
  override, force, bypass or quarantine parameter. The live policy remains
  `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL` and is **not** approved.
- **(5) Validated policy in every public decision:**
  `quarantined_sessions()`, `is_research_eligible()`,
  `assert_session_eligible()`, `assert_window_session_local()`,
  `next_eligible_session()`, `requires_state_reset()` and
  `eligible_sessions_in_range()` now route through the validated path, so a
  stale policy/matrix binding makes every one of them fail closed instead of
  returning an eligibility answer (regression-tested for all seven). The
  schema-only date accessor is private (`_schema_policy_dates`) and exists
  solely to let the disposition resolver avoid recursion. Session
  enumeration only trusts the coverage list after the matrix has verified
  that artifact's identity.
- **Latent bug found and fixed during this work:**
  `current_calendar_verification_state()` still imported the renamed
  `load_validated_policy` inside a broad `except Exception`, so the
  resulting `ImportError` was silently swallowed into the fail-safe pending
  state — the live calendar state degraded without any error. The import is
  now performed OUTSIDE the try block so a renamed symbol raises loudly, and
  the state is correct again.
- **Tests:** full suite **853/853 pass** (was 686). Added coverage for every
  reproduced defect plus: candidate binding never claims 77 sessions for a
  1-session candidate; a changed candidate block list changes the binding; a
  proposal cannot inherit structural facts from a prior on-disk proposal; a
  proposal without the block hash marks identities FAILED; the REAL
  candidate still yields 77 sessions / 30 blocks / 0 spanning / 8 rolls /
  516 coverage / 317 observed / 309 eligible DEV with zero quarantine
  violations; WARN MBO or front artifacts rejected; legacy, dirty,
  non-ancestor, stale-config and stale-code envelopes rejected; missing or
  mismatched embedded-vs-active structural hashes rejected. Three fixtures
  were corrected (clean envelopes and permitted statuses on synthetic
  artifacts, the proposal fixture embedding structural identities, and a
  missing tmp subdirectory); no existing test was weakened or deleted to
  make anything pass.
- **Truth preservation re-verified:** the ten evidence states remain
  `PENDING_EVIDENCE`; `EVIDENCE_STATES` has no quarantine value; the
  evidence matrix and calendar overrides remain byte-unchanged; the calendar
  state is the provisional `PROVISIONAL_PENDING_DATES_QUARANTINED`.
- **Files changed:** `src/nqresearch/eligibility.py`,
  `src/nqresearch/holdout.py`, `src/nqresearch/calendar_evidence.py`,
  `src/nqresearch/research.py`, `src/nqresearch/qa/closeout.py`,
  `src/nqresearch/cli.py`, `tests/unit/test_eligibility.py`,
  `tests/unit/test_holdout_fence.py`, `tests/unit/test_closeout.py`,
  `tests/unit/conftest.py`. No config file content changed in this round.
- **Verification:** `git diff --check` clean; no real artifact regenerated;
  no raw vendor data or evidence file changed; **no `partitions_active.yaml`**;
  no HOLDOUT/FORWARD access; no normalization, feature, label or model work.
- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0050 — Third-round PA-0002 remediation: binding failures propagate to artifact status, substantive identity/input validation, proposal-envelope verification, restricted coverage WARN

- **Category:** review findings + implementation fixes + test additions.
  AL-0047, AL-0048, AL-0049 and all earlier entries are unchanged.
- **(1) Fail-open artifact status (reproduced):** a candidate containing
  quarantined date 2024-09-02 as an MBO session produced
  `quarantine_disjoint_from_candidate_mbo_blocks = FAIL` (block stage) and
  `quarantine_structurally_safe = FAIL` with explicit violations (proposal
  stage), yet BOTH artifacts reported top-level `status = PASS`, because the
  verdict was computed only from the three original structural checks and
  ignored `research_eligibility_binding.checks`. Fixed: the top-level status
  of `mbo_blocks_frozen` and `partition_proposal` now incorporates the
  binding verdict, so an artifact can never present PASS while an embedded
  mandatory safety or identity check says FAIL. The block-stage
  `quarantine_structurally_safe = WARN (DEFERRED)` remains deliberately
  non-blocking by itself — full proof genuinely requires partition ranges
  and roll decision sources — and is excluded via an explicit non-blocking
  list rather than by ignoring the binding. The exact three
  partition-structure checks are preserved unchanged in `checks` because
  activation requires that exact set.
- **(2) Vacuous identity validation (reproduced):** `not-a-hash`, a
  63-character value and uppercase 64-character text all yielded
  `structural_artifact_identities_valid = PASS` with the proposal still
  top-level PASS. Fixed: every bound identity must now be exactly 64
  LOWERCASE hex characters (`_is_sha256_hex`), and "identities valid" no
  longer means "a file existed and produced some hash" — the coverage and
  front-series INPUTS are now substantively validated during proposal
  generation via `_validate_input_artifact()`: expected artifact type,
  required keys, permitted status semantics, clean committed-tree envelope,
  real ancestral commit SHA, current effective config hash and current
  package hash. Any problem FAILs the binding and therefore the artifact.
  **Consequence, accepted and NOT weakened:** the real candidate proposal now
  reports top-level FAIL because its historical coverage/front-series inputs
  still carry legacy envelopes (no `generation_git_clean`, stale
  config/code hashes). The three structural checks remain PASS and
  `quarantine_structurally_safe` is PASS with zero violations; only the
  input-envelope validation fails, and it will pass after the reviewed
  post-commit clean-tree regeneration. The corresponding regression test was
  updated to assert this precise decomposition rather than to force PASS.
- **(3) Unverified proposal envelope (reproduced):**
  `_verify_activation_evidence()` hashed and parsed
  `partition_proposal.json` but never applied the clean/current envelope
  verifier to it — that was applied only to the three structural artifacts.
  Fixed: the proposal's own envelope is now verified immediately after the
  artifact-type check and BEFORE any status, checks, state, readiness,
  ranges or embedded identities are trusted. Activation regressions cover
  missing/false/string cleanliness, malformed/nonexistent/non-commit and
  non-ancestor SHAs, stale config hash, stale package hash, wrong artifact
  type and a stripped legacy envelope; a further test proves a genuine clean
  proposal generated at an implementation commit REMAINS acceptable after a
  later audit-log-only descendant commit.
- **(4) Restricted coverage WARN:** the activation verifier previously
  accepted coverage status WARN generically. It now additionally requires
  the substantive state via `_coverage_substance_problems()`: `n_fail == 0`,
  no missing sessions, zero cross-file ordering violations, the coverage
  checks present, `n_expected_complete_sessions == 516`, and every coverage
  check PASS except the one specifically understood WARN,
  `pre_rth_short_sessions_without_data` (the known 2025-04-18 pre-RTH Good
  Friday session). Any additional, renamed, unknown or materially different
  WARN fails closed pending review; a PASS status is accepted when the same
  invariants hold. The live coverage artifact is verified to be in exactly
  the understood state.
- **Tests:** full suite **883/883 pass** (was 853). Added: quarantined date
  as candidate MBO session cannot be top-level PASS at either stage; the
  deferred block-stage WARN alone does not fail the artifact; malformed
  identities (`not-a-hash`, 63/65 chars, uppercase, empty, None, int) fail
  the artifact; a stale policy binding makes both candidates non-PASS; the
  real 77/30 candidate remains structurally valid with the FAIL isolated to
  legacy input envelopes; coverage substance suite (understood state clean,
  real artifact clean, unknown/renamed WARN, nonzero FAIL, missing session,
  ordering violation, wrong expected count, empty checks, PASS accepted);
  nine proposal-envelope activation rejections plus the audit-only-descendant
  acceptance. Two fixtures were extended (synthetic coverage now carries the
  corpus-shaped substance fields; the synthetic proposal now carries a clean
  envelope) and a missing `pytest` import was added; no existing test was
  weakened or deleted to make anything pass.
- **Unchanged and re-verified:** the ten evidence states remain
  `PENDING_EVIDENCE`; `EVIDENCE_STATES` has no quarantine value; the
  evidence matrix and calendar overrides remain byte-unchanged; calendar
  state `PROVISIONAL_PENDING_DATES_QUARANTINED`; policy lifecycle
  `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL`; 10 quarantined / 8 excluded /
  309 eligible DEV; coverage 516; MBO 77/30 with zero spanning; eight causal
  roll switches.
- **Files changed:** `src/nqresearch/qa/closeout.py`,
  `src/nqresearch/holdout.py`, `tests/unit/test_closeout.py`,
  `tests/unit/test_holdout_fence.py`, `tests/unit/conftest.py`. No config
  file content changed in this round.
- **Verification:** `git diff --check` clean; **no real QA artifact
  regenerated**; no raw vendor data or evidence file changed; **no
  `partitions_active.yaml`**; no HOLDOUT/FORWARD access; no normalization,
  feature, label or model work.
- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0051 — Fourth-round PA-0002 remediation: mandatory strict coverage fields, WARN bound to the machine-readable Good Friday fact, coherent PASS permitted

- **Category:** review finding + implementation fix + test additions.
  AL-0047 through AL-0050 and all earlier entries are unchanged.
- **(1) Absent fields silently accepted (reproduced):**
  `_coverage_substance_problems()` used `doc.get(...)` comparisons whose
  `None` results fell through, so an artifact missing `n_fail`,
  `missing_sessions` or `cross_file_order_violations` entirely produced ZERO
  problems. Fixed: those fields — plus `n_expected_complete_sessions`,
  `missing_pre_rth_short_sessions` and `checks` — are now MANDATORY and
  strictly typed. Integer fields must be plain non-boolean ints of the exact
  expected value (`516`, `0`, `0`), so `True`, `False`, `"0"`, `"516"`,
  `1.0`, `[]` and `{}` are all refused; `missing_sessions` must be exactly
  an empty list; `missing_pre_rth_short_sessions` must be a list of date
  strings; `checks` must be a non-empty list of well-formed entries with
  string names, valid statuses and no duplicate names. Missing keys, nulls
  and wrong container types fail closed.
- **(2) Understood WARN was name-only (reproduced):** a warning whose check
  name happened to be `pre_rth_short_sessions_without_data` was accepted
  even when the artifact's own machine-readable field pointed at
  `2099-12-31`, because only the name and status were validated. Fixed: the
  single understood WARN now additionally requires
  `missing_pre_rth_short_sessions == ["2025-04-18"]` — the actual Good
  Friday fact — and remains conditional on exactly one non-PASS check, zero
  missing expected sessions, zero FAIL sessions and zero ordering
  violations. An unknown or additional date, a renamed or duplicated
  warning, an extra WARN, or a conflicting top-level field all fail closed.
  The rule reads the machine-readable date field rather than free-form
  detail text.
- **(3) Coherent PASS was impossible (reproduced):** `_STRUCTURAL_ARTIFACTS`
  permitted only top-level coverage status `WARN`, contradicting the
  intended rule that a substantively valid PASS is acceptable. Coverage now
  permits `PASS` or `WARN`, with coherence enforced centrally:
  **PASS** only when every check passes AND
  `missing_pre_rth_short_sessions` is empty; **WARN** only for the exact
  understood 2025-04-18 condition. Any other PASS/WARN combination — a
  top-level PASS while the Good Friday warning is still present, a
  top-level WARN with every check passing, or a WARN whose missing-session
  list is not exactly `["2025-04-18"]` — fails closed. The activation
  verifier (`_STRUCTURAL_ARTIFACTS` + `_verify_structural_artifacts`) and
  the generation-time input validator (`_validate_input_artifact` via
  `PERMITTED_COVERAGE_STATUSES`) now share this one acceptance rule.
- **Live artifact re-verified:** the historical coverage artifact still
  matches the understood condition exactly — status WARN, 516 expected,
  `n_fail=0`, no missing sessions, zero ordering violations, the single
  `pre_rth_short_sessions_without_data` WARN, and
  `missing_pre_rth_short_sessions == ["2025-04-18"]` — so
  `_coverage_substance_problems()` returns no problems for it.
- **Tests:** full suite **938/938 pass** (was 883). Added refusals for each
  mandatory field missing separately, each field null, boolean/string/float
  values in every integer field, wrong container types for both list
  fields, duplicate check names, five malformed check-entry shapes, the
  understood warning name attached to 2099-12-31, an additional pending
  date, an additional WARN, a renamed WARN, top-level PASS with the Good
  Friday warning present, all-PASS checks with a non-empty missing-session
  field, top-level WARN with every check PASS, and WARN without exactly
  `["2025-04-18"]`; plus acceptance of the exact live understood WARN state
  and of a coherent synthetic PASS state. At activation: an incoherent
  coverage PASS is rejected, a coherent coverage PASS is accepted, and four
  unsound coverage mutations are rejected. All round-4 adversarial tests
  remain; the earlier `test_material_deviations_fail` needles were retargeted
  to the improved messages, and one test was renamed from
  "warn_only" to "incoherent PASS rejected" because PASS is now legitimately
  permitted when coherent. No test was weakened or deleted to make anything
  pass.
- **Unchanged and re-verified:** the ten evidence states remain
  `PENDING_EVIDENCE`; `EVIDENCE_STATES` has no quarantine value; the
  evidence matrix, calendar overrides and every other `config/data/` file
  remain byte-unchanged; calendar state
  `PROVISIONAL_PENDING_DATES_QUARANTINED`; policy lifecycle
  `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL`; 10 quarantined / 8 excluded /
  309 eligible DEV; coverage 516; MBO 77/30 with zero spanning; eight causal
  roll switches. The real proposal candidate remains top-level FAIL solely
  because its historical inputs still carry legacy envelopes — resolved by
  the reviewed clean-tree regeneration, not by weakening the check.
- **Files changed:** `src/nqresearch/qa/closeout.py`,
  `src/nqresearch/holdout.py`, `tests/unit/test_closeout.py`,
  `tests/unit/test_holdout_fence.py`, `tests/unit/conftest.py`.
- **Verification:** `git diff --check` clean; **no real QA artifact
  regenerated**; no raw vendor data, evidence file or calendar/config file
  changed; **no `partitions_active.yaml`**; no HOLDOUT/FORWARD access; no
  normalization, feature, label or model work.
- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0052 — PA-0002 implementation committed and artifacts regenerated; closeout stamping BLOCKED by a circular evidence-matrix/coverage binding (finding)

- **Category:** commit record + artifact regeneration + BLOCKING design
  finding. AL-0047 through AL-0051 and all earlier entries are unchanged.
- **Immutable implementation commit:**
  `f6b43537ebb7f301573fe4b8f95037a7fefa3e1c` — "PA-0002: quarantine
  evidence-pending sessions from research eligibility" (19 files, +4,294/-65,
  containing AL-0047..AL-0051). Never amended. Pre-commit verification:
  938/938 tests, `git diff --check` clean, exactly the 19 reviewed paths,
  `docs/canonical-spec-v1.0.md` unchanged, no data/QA/evidence/raw/registry
  path staged, no `partitions_active.yaml`, policy
  `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL`, calendar
  `PROVISIONAL_PENDING_DATES_QUARANTINED`, config hash `fbbccd44…`.
  (A first commit attempt aborted harmlessly when a PowerShell here-string
  mis-parsed an apostrophe in the message; nothing was committed and the
  commit was re-issued from a message file.)
- **All 12 artifacts regenerated from the clean committed tree** in
  dependency order (acquisition validation -> record-level overlap -> gate ->
  coverage -> front series -> MBO blocks -> partition proposal). Every one
  carries the SHARED envelope: `git_sha`
  `f6b43537ebb7f301573fe4b8f95037a7fefa3e1c`, `generation_git_clean` boolean
  true, the clean committed-tree note, `config_hash`
  `fbbccd441ae4907b2699f06535a1019a5f4631a9977947f1f96aa3146cdfef8e`,
  `audit_code_hash`
  `44cbe2508418d6e0c538eda039f27b0da1768bc5cfdf58e24c2d28b106769456`,
  `data_root` `D:\nq-research\data`.
  - `8bc8cda9dcc897cf5cde3e6c420ea4af54b6ecbff81a3a19608f2a4148ece35c` PASS mbp1_acquisition_gate.json
  - `c2a214c4f7eb87062e9c703f7e568b6c2ed21d2f5b78fd041de60fd0f0057349` PASS mbp1_manifest_validation.json
  - `8fd16bad383aa71d2084e29fa46bd22f67f4ebd8c736fb04a37395e21b5835c6` PASS mbp1_range_adjacency.json
  - `51450b7acf27be113f10600fb502469a74168a9c3e3378c2d9e1b180c0ee4a4c` WARN mbp1_sample_overlap.json
  - `608be88e437644e198ac738f9afd0075a0c5d00fc45e993df302dcd35e001adf` PASS mbp1_sample_overlap_record_level.json
  - `ae3f9ad216367b7bd26062e7d61d5274516d4f2e81d9613331b7722cd1c7c86a` WARN mbp1_source_inventory.json
  - `72d35f58e76de6bbeb89a1fefe64a26fc6d91035331ed3612923136b361d7c7d` PASS mbp1_source_selection.json
  - `8911f466f574f862f0d1b153010f85671bef47ec7426299e09d204dc63239d68` WARN storage_gate.json
  - `71db2f9e6c809c44d301e071dbeb69958a33de90d913fa2086e216712241076b` WARN mbp1_full_history_coverage.json
  - `383f586276393cd76192c317c99c0a67436e079b081978d441f6f3e65b6e2673` PASS mbp1_front_contract_series.json
  - `1281917f1e4988e655b3db93c3867b4255419cfe6c7c396dbb6c749351ad47e1` **FAIL** mbo_blocks_frozen.json
  - `739d4664516a8642d285eeacea46e1c0a9b06e92135672878af54492cff2074f` **FAIL** partition_proposal.json
- **Acquisition verification PASSES in full:** gate PASS with all 9 named
  checks PASS; manifests 642/642 with zero failures; record-level overlap
  11/11 pairs and **115,583,040 records identical**; range adjacency PASS;
  source selection PASS with zero sample leakage; inventory WARN solely from
  the 11 understood vendor-degraded dates with zero metadata problems;
  storage 1,720.7 GB (above the 1 TB minimum). **Live `require_provenance()`
  PASSES** against the regenerated gate (clean=true, sha f6b43537…).
- **Coverage and front series verified:** coverage WARN for exactly the
  understood condition — 516 expected, `n_fail=0`, `missing_sessions=[]`,
  `cross_file_order_violations=0`,
  `missing_pre_rth_short_sessions=["2025-04-18"]`, and the single non-PASS
  check `pre_rth_short_sessions_without_data`; front series PASS with 8
  causal switches and the 2026-08-17 partial edge session excluded. MBO
  blocks reproduce 77 sessions / 30 blocks with zero quarantined dates in
  candidate sessions or block spans; the proposal reproduces DEV/SELECTION/
  HOLDOUT 318/100/98, MBO 23/23/31, SPANNING 0, all three structural checks
  PASS, `PROPOSED_NOT_ACTIVE`, `activation_ready=false`.
- **BLOCKING FINDING — circular binding between the evidence matrix and the
  coverage artifact.** Regenerating coverage necessarily changed its bytes
  (`03545b61…` -> `71db2f9e…`) because the envelope now records the new
  commit, config and code hashes. The committed evidence matrix binds the
  OLD coverage identity in `meta.observed_reference.artifact_sha256`, so
  `load_validated_matrix()` correctly refuses, the PA-0002 policy cannot
  validate, and that failure propagates (exactly as designed in AL-0050) to
  `mbo_blocks_frozen` and `partition_proposal`, both FAIL. **The coverage
  SUBSTANCE is unchanged** — 516 expected, 507 PASS / 8 WARN / 0 FAIL, zero
  missing, zero ordering violations, 5,401,908,864 rows across 625 files,
  and all 26 per-date observed spans still match the matrix exactly; only
  the provenance envelope differs.
  The dependency is genuinely circular and does NOT terminate under a naive
  re-bind: coverage-artifact bytes contain `config_hash`; `config_hash`
  includes `research_eligibility.yaml` (added by PA-0002); the policy binds
  the evidence-matrix SHA; and the matrix binds the coverage-artifact SHA.
  Updating the matrix therefore changes the policy, which changes the config
  hash, which changes the coverage envelope, which changes the matrix
  binding again.
- **Consequence for tests:** the suite is **911 passed / 27 failed** in this
  state; every failure traces to the same stale matrix->coverage binding
  (the fail-closed machinery behaving correctly), not to a new logic defect.
- **Nothing was weakened, edited around, or forced.** No check was relaxed to
  make an artifact PASS; no config file was edited (the evidence matrix and
  the eligibility policy are byte-unchanged); no artifact was hand-patched;
  the policy remains `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL` and is NOT
  activation-approved; partitions remain inactive with no
  `partitions_active.yaml`; HOLDOUT/FORWARD were not accessed; no
  normalization, feature, label, sample, dataset, model or experiment work
  occurred; raw vendor data and all 45 calendar evidence files are unchanged;
  Git tracks no data artifacts.
- **Remediation options recorded for review (none applied):**
  (a) bind `meta.observed_reference` to a SUBSTANCE digest of the coverage
  observations (sessions/spans/counters) rather than the whole file, leaving
  file-identity and envelope verification to activation, which already binds
  `coverage_artifact_sha256` in `ActivePartitions` — breaks the cycle at its
  weakest link and matches what the matrix actually needs to assert;
  (b) remove `research_eligibility.yaml` from `effective_config_hash()` and
  bind it solely through activation, mirroring the rationale already
  documented for the evidence matrix — this reverses the explicit PA-0002
  decision to include it, so it needs approval;
  (c) any combination. Option (a) is the smaller and more principled change.
  A reviewed decision is required before the closeout stamping can complete.
- **Commit:** this entry is UNCOMMITTED. The audit-log-only commit
  authorized for AL-0052 was NOT made, because the stamping sequence did not
  reach its required success conditions and the reviewer must choose the
  remediation. Nothing was pushed.

## AL-0053 — Circular coverage binding broken: versioned coverage-substance digest (remediation of AL-0052)

- **Category:** protocol-relevant design remediation + implementation +
  test changes. AL-0052 is preserved verbatim as the truthful record of the
  blocked run; AL-0047..AL-0051 and all earlier entries are unchanged.
- **Approved remedy (a):** replace the evidence matrix's LIVE whole-file
  coverage binding with a deterministic, versioned coverage-SUBSTANCE
  digest. `research_eligibility.yaml` REMAINS inside
  `effective_config_hash()` (remedy (b) was explicitly not taken).
- **The cycle, restated:** the coverage artifact's bytes contain its
  provenance envelope, which contains `config_hash`; `config_hash` includes
  `research_eligibility.yaml`; the policy binds the evidence-matrix SHA; and
  the matrix bound the coverage artifact's whole-file SHA. Re-binding the
  matrix therefore changed the policy, which changed the config hash, which
  changed the coverage envelope, which invalidated the matrix again — a
  non-terminating loop that made envelope-only regeneration impossible.
- **Fix:** new `calendar_evidence.coverage_substance_sha256(document)` with
  the versioned identifier `coverage-substance-v1`. It hashes canonical JSON
  (sorted keys, `separators=(",",":")`, `ensure_ascii=True`,
  `allow_nan=False`) of the artifact's SUBSTANCE: every field except the
  eight provenance-envelope fields owned by `qa/report.py`
  (`generated_at_utc`, `nqresearch_version`, `git_sha`,
  `generation_git_clean`, `restamp_note`, `audit_code_hash`, `config_hash`,
  `data_root`) and except an informational self-digest field, so the digest
  can never include itself. It therefore covers the artifact type, every
  corpus/accounting field, all checks/warnings/classifications and the
  complete per-session observations. Non-dictionary documents, documents
  with no substantive fields, non-serialisable values and non-finite numbers
  are refused.
- **Matrix binding updated** (`config/data/cme_calendar_evidence.yaml`):
  `meta.observed_reference` now declares
  `substance_digest_algorithm: coverage-substance-v1` and
  `substance_sha256:
  2ebf83b6e44c42b24836453740702db2eb5012907bba701de46de4168cd88d39`.
  The previous whole-file SHA `03545b61…` is retained ONLY as
  `historical_whole_file_sha256_audit_only` (with the original generation
  timestamp and git SHA) and takes no part in live validation. The note now
  states exactly what is verified: the digest is RECOMPUTED from the live
  bytes (never trusted from inside the artifact), compared, and only then is
  every per-date session presence and RTH span checked; envelope-only
  regeneration does not invalidate the observation evidence while any
  substantive change does.
- **`verify_observed_against_coverage()`** now requires the declared
  algorithm to equal `coverage-substance-v1`, requires a valid 64-hex
  `substance_sha256`, parses the live artifact, recomputes the digest,
  fails on missing/unknown algorithm or malformed/mismatched digest BEFORE
  any date-level claim is trusted, and then still checks all 26 per-date
  observations. Path containment is unchanged.
- **Activation is NOT weakened — two independent identities:**
  `ActivePartitions.coverage_artifact_sha256` and the approved proposal
  continue to bind the EXACT whole-file bytes (with the clean envelope), and
  `_verify_structural_artifacts()` now enforces both guarantees separately:
  (1) live file SHA equals the SHA bound by the active configuration and
  embedded in the proposal; (2) the recomputed substance digest equals the
  digest bound by the evidence matrix. The two are deliberately never
  compared with each other. The coverage artifact must still pass the strict
  substantive Good Friday checks and the clean/current envelope checks.
- **Policy re-bound:** `research_eligibility.yaml`
  `meta.evidence_matrix_sha256` updated to the revised matrix SHA
  `f6099bd824691479dc246dfff44cdce239e9244333d21a56457f82ab714c1250`.
  Unchanged: the same ten quarantine dates, every evidence state
  `PENDING_EVIDENCE`, lifecycle `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL`,
  the provisional/quarantined calendar state, and the policy's membership of
  `effective_config_hash()`. Calendar overrides untouched; no evidence
  reinterpreted.
- **Tests:** full suite **985/985 pass** (was 938). New
  `TestCoverageSubstanceDigest` proves: each of the eight envelope fields
  individually leaves the digest unchanged; JSON indentation and key order
  leave it unchanged; nine substantive top-level fields each change it; five
  session-level fields each change it; adding or removing a session changes
  it; an embedded self-digest is excluded; malformed documents and
  non-finite values are refused; the identifier is versioned; and the live
  matrix declares exactly the live artifact's digest with no
  `artifact_sha256` remaining. Cross-check tests prove envelope-only
  regeneration validates, a substantive change fails, missing/unknown
  algorithm and missing/malformed digests fail, and a matching digest still
  does not buy trust in a wrong per-date observation. Activation tests prove
  the exact whole-file SHA is still rejected when wrong even though the
  substance digest matches, and that the two identities are checked
  independently. Per the review instruction, the test asserting the live
  closeout artifacts lack a clean envelope was REPLACED by a synthetic
  legacy fixture, and the live-corpus proposal test now asserts the actual
  current state instead of assuming a legacy envelope.
- **Verified before commit:** revised matrix validates; all 26 per-date
  observations pass; the policy resolves exactly the same ten pending dates;
  disposition `PENDING_DATES_QUARANTINED`; calendar
  `PROVISIONAL_PENDING_DATES_QUARANTINED`; 10 quarantined / 8 excluded /
  309 eligible DEV; coverage 516; MBO 77/30; zero spanning; eight causal
  rolls; no raw or evidence file changed; no `partitions_active.yaml`.
  New effective config hash
  `48c2d27ad59d14ecfda4b35690ee1ca5e6c56fedd2e8aa04380309763aa10ce5`
  (the policy re-bind), so the 12 artifacts are regenerated from the
  remediation commit in the following step.
- **Commit:** this entry belongs to the remediation implementation commit;
  the subsequent artifact stamping is recorded separately in AL-0054.
  Nothing pushed.

## AL-0054 — PA-0002 artifact stamping completed: all 12 artifacts regenerated from the remediation commit; cycle proven broken

- **Category:** artifact regeneration + identity stamping (successful
  completion of the sequence that AL-0052 recorded as blocked). AL-0047
  through AL-0053 and all earlier entries are unchanged.
- **Immutable implementation commits (neither amended):**
  - PA-0002 implementation:
    `f6b43537ebb7f301573fe4b8f95037a7fefa3e1c`
  - Circularity remediation:
    `37e38db2ba09fc6085f2f4651d757c6c88280657`
- **The circularity and its resolution:** the coverage artifact's bytes
  contain its provenance envelope, the envelope contains `config_hash`,
  `config_hash` includes `research_eligibility.yaml`, the policy binds the
  evidence-matrix SHA, and the matrix formerly bound the coverage artifact's
  whole-file SHA — so re-binding never terminated (AL-0052). The matrix now
  binds a versioned **coverage-substance digest** instead.
  **Proven empirically by this regeneration:** the coverage artifact's
  whole-file SHA changed `71db2f9e…` -> `2a215f30…` (new commit
  `37e38db2…`, new config hash `48c2d27a…`, new code hash) while its
  substance digest remained exactly
  `2ebf83b6e44c42b24836453740702db2eb5012907bba701de46de4168cd88d39`, so the
  committed matrix validated against the regenerated artifact with **no
  re-binding**, and the closeout artifacts reached PASS.
- **Digest algorithm:** `coverage-substance-v1`.
  **Final substance digest:**
  `2ebf83b6e44c42b24836453740702db2eb5012907bba701de46de4168cd88d39`.
- **Revised identities:** evidence matrix
  `f6099bd824691479dc246dfff44cdce239e9244333d21a56457f82ab714c1250`;
  research-eligibility policy
  `4dbd9432c24f5f7d86baf63c955c35ad7ca8a02225623ce445be26b150ad4bdc`;
  effective config hash
  `48c2d27ad59d14ecfda4b35690ee1ca5e6c56fedd2e8aa04380309763aa10ce5`;
  package/audit code hash
  `b2283da193fce88fd510868be6c69112ed59ddda5548f476b7fe56bb53bab0b2`;
  acquisition code hash
  `2194635f5a3ca106a7f877b4e7c72b16035e085b652687a51a3d5551a4d7e211`.
- **All 12 artifacts regenerated from the clean remediation commit**, sharing
  `git_sha 37e38db2ba09fc6085f2f4651d757c6c88280657`,
  `generation_git_clean` boolean true, the clean committed-tree note,
  `config_hash 48c2d27a…`, `audit_code_hash b2283da1…`, `data_root
  D:\nq-research\data`:
  - `9d4233f49a20d03ed52c79e2714546532ee3aa43ae72be0cfd34713773d26b49` PASS mbp1_acquisition_gate.json
  - `95177863ae3282d9e91d3c66d7510b1e0a7453ab7402887ed7ae4018c4213f12` PASS mbp1_manifest_validation.json
  - `65e69f4745338d36c385f5b3b41c3deb28b950cd8f85a6aa87c59b560806b288` PASS mbp1_range_adjacency.json
  - `3a88890c8d93e02e1a69af6c95c9e4a79b4dc5b79fd14db8d3bd8eaf03518202` WARN mbp1_sample_overlap.json
  - `1b2a35119e7d29e763fdd39b458e43ffcab47f9ea4900af2e65d83e4f6783fc7` PASS mbp1_sample_overlap_record_level.json
  - `55873038d7a94abcfbc0936ff247b732911bd1ae7de6b2233639b332699f7629` WARN mbp1_source_inventory.json
  - `221cf498bcccddbb4f7f7cdf68877e61654f8bffea1a45ca01ae61846adcc068` PASS mbp1_source_selection.json
  - `81da66dc79615a3789c97bca8f9d42b63f22a775f171e815739b55f68c5ca81d` WARN storage_gate.json
  - `2a215f3048eb0dd5447db21ad9736db964822a961e54103fbd17410dacb349ad` WARN mbp1_full_history_coverage.json
  - `dfb3640bf975f26e7688d02426adccbacd845160a1fda70a9e4ecfcf7f3e6075` PASS mbp1_front_contract_series.json
  - `6dedf2c6aa7c1e77aa45d405bcba985470265b32327adc0a6cd12c1c6b0fa0fc` PASS mbo_blocks_frozen.json
  - `a1b6d97b977cc1e80ed54b1bcba418a53091cff823f4c0551c33626cc8ff0e4b` PASS partition_proposal.json
- **Acquisition reproduced exactly:** gate PASS with all 9 named checks PASS
  and its `acquisition_code_hash` equal to the current one; manifests
  **642/642** with zero failures; record-level overlap **11/11 pairs,
  115,583,040 records identical**; range adjacency PASS; source selection
  PASS with zero sample leakage; inventory WARN solely from the 11
  understood vendor-degraded dates (zero metadata problems); storage WARN at
  **1,720.7 GB**, above the 1 TB minimum. **Live `require_provenance()`
  PASSES** (gate PASS, clean true, sha 37e38db2…).
- **Closeout completed:** coverage WARN for exactly the understood condition
  — 516 expected, `n_fail=0`, `missing_sessions=[]`,
  `cross_file_order_violations=0`,
  `missing_pre_rth_short_sessions=["2025-04-18"]`, single non-PASS check
  `pre_rth_short_sessions_without_data`; front series PASS, strictly causal,
  **8 switches**, 2026-08-17 partial edge excluded; MBO blocks **PASS with
  77 sessions / 30 blocks**, zero quarantined dates in candidate sessions or
  block spans, and the block-stage deferred structural WARN correctly
  non-blocking; partition proposal **PASS** with exactly the three
  structural checks all PASS, DEV/SELECTION/HOLDOUT **318/100/98**, MBO
  **23/23/31** with blocks 8/11/11 and **SPANNING 0**, candidate binding
  reporting **10 quarantined dates / 8 excluded observed DEV / 309 eligible
  DEV**, zero structural input problems, all five binding checks PASS, and
  its three bound structural identities equal to the freshly regenerated
  coverage, MBO-block and front-series artifacts.
- **Activation state UNCHANGED and explicitly not approved:** the partition
  proposal remains `PROPOSED_NOT_ACTIVE` with `activation_ready=false`, the
  calendar remains `PROVISIONAL_PENDING_DATES_QUARANTINED`, and the
  research-eligibility policy remains
  `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL` — it is **not**
  activation-approved. No `config/data/partitions_active.yaml` exists and the
  holdout fence still refuses. Partition activation did NOT occur.
- **Verification:** full suite **985/985 pass**; `git diff --check` clean;
  raw vendor data unchanged (1,453 files); all 45 calendar evidence files
  unchanged (rollup `396bb01d…`); Git tracks no data artifacts; no
  HOLDOUT/FORWARD access; no normalization, feature, label, sample, dataset,
  model or experiment work occurred.
- **One follow-up test-only commit:**
  `c049cb327cb3f82259068788a593b44b045e7179` — the real-corpus proposal
  regression called `propose_partitions()` without
  `mbo_blocks_artifact_sha256`, so after regeneration its structural-identity
  binding was legitimately incomplete; the test now binds the written
  MBO-block artifact hash exactly as the CLI does. It touches no file under
  `src/`, so the package/audit code hash is unchanged at `b2283da1…` and the
  12 artifacts stamped at `37e38db2…` remain valid.
- **Commit:** this entry is the audit-log-only commit; no implementation
  commit was amended. Nothing pushed.

## AL-0055 — Activation tooling implemented for review; storage-unit error corrected; approval binding hardened

- **Category:** review finding + correction of my own reporting error +
  implementation for review. AL-0047 through AL-0054 and all earlier entries
  are unchanged. **No activation occurred and the policy remains
  unapproved.**
- **(1) CORRECTION — the reported ~118 GB storage loss was MY UNIT ERROR.**
  The readiness review compared 1,602.6 **GiB** (my ad-hoc `/1024**3`
  calculation) against 1,720.7 decimal **GB** (what `storage_gate.json`
  deliberately reports, `1 GB = 1e9 bytes`) and wrongly concluded that ~118
  GB had been consumed. Verified this round: free space is
  **1,720,742,952,960 bytes = 1,602.6 GiB = 1,720.7 GB**, and the live
  `storage_gate.json` figure of 1,720.7 GB matches the current volume state
  exactly. **No space was lost and nothing was consumed.** No deletion or
  cleanup is authorised or recommended anywhere on the data volume;
  `D:\nq-research` and `D:\futures-data-research-s3-backup` are untouched,
  and `D:\projects` is out of scope and was never read.
- **(2) SEPARATION OF POWERS — candidate state.** A generated artifact can
  never self-certify that a human approved its exact bytes, because its own
  SHA-256 does not exist while it is being written. Activation now requires
  three independent records: (a) a structurally-ready CANDIDATE
  (`state=READY_FOR_ACTIVATION_APPROVAL`, `structural_ready=true`,
  `activation_ready=false`); (b) a separately committed append-only
  human-approval entry binding the candidate's exact SHA and every
  dependency; (c) `config/data/partitions_active.yaml`. The verifier was
  updated coherently: it now REFUSES any artifact declaring
  `activation_ready=true` (self-certification), requires
  `structural_ready` to be boolean true, and requires the exact candidate
  state. The proposal generator still emits the neutral
  `PROPOSED_NOT_ACTIVE` and can never emit an approved artifact.
- **(3) NEW fail-closed tooling — `src/nqresearch/activation.py`:**
  `verify_activation_preconditions()` re-verifies the policy lifecycle
  (exactly `APPROVED_FOR_ACTIVATION`), the policy/evidence-matrix binding,
  all ten pending dates exactly quarantined with every state still truthfully
  `PENDING_EVIDENCE`, the quarantine structural invariants and frozen corpus
  counts, the clean CURRENT committed envelope of every activation-bound
  artifact, the coverage substance digest AND the exact coverage file
  identity, the exact understood 2025-04-18 coverage WARN, the causal front
  series (PASS, 8 switches, no 2026-08-17 edge), MBO blocks (PASS, 77/30),
  every partition structural check with SPANNING empty, and the exact
  DEV/SELECTION/HOLDOUT ranges and counts (318/100/98, 23/23/31); it also
  refuses if an active configuration already exists.
  `finalize_activation_candidate()` builds the candidate payload;
  `generate_active_partitions()` writes the active configuration and refuses
  unless the candidate and a valid, already-committed approval entry both
  exist and agree on every identity. **There is no override, force, bypass,
  alternate policy path, or caller-supplied relaxed state anywhere**
  (signature-tested), and nothing in the module opens or enumerates
  HOLDOUT/raw records (source-scanned). CLI:
  `nqr data audit --part finalize-activation-candidate`.
  **Against the live repository all three entry points REFUSE today**, because
  the policy is still `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL` — verified
  live and regression-tested.
- **(4) Human-approval binding hardened.** The entry must now bind ALL
  EIGHT identities — the previously missing **effective calendar SHA-256**
  plus proposal, evidence matrix, CME correspondence, research-eligibility
  policy, coverage, MBO blocks and front series — and additionally the exact
  DEV/SELECTION/HOLDOUT ranges, `approved_by`, the exact UTC timestamp, an
  explicit statement approving PA-0002 and this exact candidate, and the
  quarantine disposition and calendar state. `approval_reference` must be
  the exact `AL-\d{4}` form resolving to EXACTLY ONE `## AL-nnnn` heading:
  prefix attacks are refused (AL-0055 can never match AL-00550, enforced by
  a line-anchored non-digit boundary), duplicate headings are refused, and
  missing or ambiguous entries are refused. The approving identity and
  timestamp in `partitions_active.yaml` must match the audit entry exactly.
- **Defect found and fixed while testing the above:** the calendar constant
  `PROVISIONAL_PENDING_DATES_QUARANTINED` CONTAINS the disposition constant
  `PENDING_DATES_QUARANTINED` as a substring, so a naive membership test let
  the calendar line silently satisfy the disposition requirement. The
  verifier now strips every occurrence of the calendar state before checking
  that the disposition is recorded INDEPENDENTLY.
- **(5) Eventual sequence (documented, NOT executed) — separate review
  gates:** Commit A reviewed tooling while the policy stays unapproved →
  independent review + push → explicit human approval to transition PA-0002
  → Commit B policy transition + its approval record → regenerate the 12
  artifacts ONCE from the clean approved-policy commit → produce the
  immutable structurally-ready candidate → independent review of every final
  artifact and identity → explicit human approval of the exact candidate →
  Commit C audit-log-only exact-candidate approval → independent
  verification → Commit D `partitions_active.yaml` → mechanically verify
  DEV/SELECTION access and HOLDOUT refusal. **Policy approval is never
  combined with unreviewed tooling.**
- **(6) Cache and storage policy:** cache scoping is deliberately NOT
  redesigned during activation preparation. `qa/cache.py` keys on the
  effective config hash, so approving the policy will invalidate all caches
  and force one full re-decode (5,401,908,864 coverage records and
  115,583,040 overlap records). That cost is accepted as correct under the
  current strict cache identity rather than introducing a new cache-validity
  model mid-flight. Storage remains ~1,720.7 decimal GB free, far above the
  1 TB minimum; the next regeneration may add caches and remains safely
  above it. No caches or data were deleted.
- **(7) October pilot treatment recorded (pilot NOT started):** the research
  normalization pilot remains **October 2025 only** (23 sessions, all in DEV,
  no quarantined date). **MBO-BLK-008 spans 2025-10-30 → 2025-11-07 and is
  NOT an October-only block.** Block-level MBO validation must either
  exclude MBO-BLK-008 from an October-only validation, or extend a separate
  QA-ONLY reconstruction window through 2025-11-07. Extending that QA window
  must never extend the research pilot or alter its session set.
- **Files changed:** NEW `src/nqresearch/activation.py`, NEW
  `tests/unit/test_activation.py`; modified `src/nqresearch/holdout.py`
  (candidate-state constants and semantics, eight-identity approval binding,
  exact/unique heading resolution, independent disposition check),
  `src/nqresearch/cli.py` (new fail-closed part),
  `tests/unit/test_holdout_fence.py` (candidate-shaped fixtures, complete
  approval entry, self-certification and structural_ready regressions).
  No configuration file changed; the policy is untouched.
- **Verification:** full suite **1033/1033 pass** (was 985); `git diff
  --check` clean. **No real artifact regenerated; no real
  `partitions_active.yaml` exists; the policy remains
  IMPLEMENTED_PENDING_ACTIVATION_APPROVAL; the partition proposal remains
  PROPOSED_NOT_ACTIVE with activation_ready=false; the calendar remains
  PROVISIONAL_PENDING_DATES_QUARANTINED.** Raw vendor data, all 45 calendar
  evidence files and HOLDOUT/FORWARD were untouched; no normalization,
  feature, label, sample, dataset, model or experiment work occurred. All
  tests requiring activation files used temporary synthetic directories only.
- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0056 — Activation candidate remediation: distinct nine-identity binding, strict candidate substance, machine-readable approval, no path injection, atomic write, end-to-end synthetic proof

- **Category:** remediation of blocking review findings against the AL-0055
  activation tooling. AL-0055 and every earlier entry are unchanged. **No
  activation occurred, no artifact was regenerated, the research-eligibility
  policy remains unapproved, and `config/data/partitions_active.yaml` still
  does not exist.**
- **(1) BLOCKING DEFECT FIXED — the candidate had no identity of its own.**
  The active configuration bound only `partition_proposal_sha256`, so the
  artifact a human actually approves (the activation CANDIDATE) was either
  unbound or disguised as the neutral proposal's hash. Activation now binds
  **NINE** identities: a new, distinct `activation_candidate_sha256` field
  plus the eight underlying dependencies
  (`UNDERLYING_IDENTITY_FIELDS` in `src/nqresearch/holdout.py`). The
  fence reads the CANONICAL `partition_activation_candidate.json`, verifies
  its exact bytes against `activation_candidate_sha256`, its declared
  artifact type, and its clean committed provenance envelope BEFORE trusting
  any of its content; it then verifies
  `state=READY_FOR_ACTIVATION_APPROVAL`, `structural_ready=true`,
  `activation_ready=false`, and that its eight bound identities equal the
  ones the active configuration binds. **The neutral
  `partition_proposal.json` is verified SEPARATELY and must still be
  `PROPOSED_NOT_ACTIVE` with `activation_ready=false`** — a relabelled
  proposal is now refused explicitly ("must remain independently
  identifiable"), so one artifact can never stand in for both the mechanical
  source and the approved candidate.
- **(2) The candidate's COMPLETE substance is now validated, not sampled.**
  New strict Pydantic model `ActivationCandidate` (`extra="forbid"` at every
  level, `StrictBool`/`StrictInt`, `Literal` artifact/state/status, an exact
  eight-key `bound_identities` sub-model) refuses unknown, missing or
  malformed fields instead of trusting only the fields the verifier happens
  to read. The bespoke state checks still run FIRST so their fail-closed
  reasons stay legible. On top of the schema, every substantive field is
  compared against evidence **recomputed at verification time**: the
  disposition, the live policy lifecycle state, the live quarantined-date
  set, the freshly recomputed structural-quarantine facts, the neutral
  proposal's checks and MBO distributions, and the exact DEV/SELECTION/HOLDOUT
  ranges (which must agree across the active configuration, the candidate AND
  the neutral proposal). `_verify_calendar_evidence()` now RETURNS
  `(disposition, policy, quarantine_facts)` for exactly this purpose.
  `generate_active_partitions()` additionally rebuilds the entire expected
  candidate payload from freshly proven preconditions and refuses if any key
  differs, naming the differing keys.
- **(3) Human approval is now mechanically unambiguous.** The audit entry
  must carry each required value EXACTLY ONCE as `- key: value`:
  `decision: APPROVE_PA_0002_ACTIVATION_CANDIDATE` (a loose "APPROVE"
  substring is no longer sufficient and never matches "DO NOT APPROVE",
  "NOT APPROVED" or "APPROVAL REFUSED"), `activation_candidate_sha256`, all
  eight dependency identities, `dev_range`/`selection_range`/`holdout_range`,
  `approved_by`, `approved_at_utc`, `quarantine_disposition` and
  `calendar_state`. Any duplicate declaration of a required key is refused as
  ambiguous — identical repeats included. `approval_reference` must satisfy
  `re.fullmatch(r"AL-\d{4}")` and resolve to EXACTLY ONE line-anchored
  `## AL-nnnn` heading with a non-identifier boundary, so AL-0055 can never
  match AL-00550 and duplicate headings are refused. Fields belonging to a
  NEIGHBOURING entry can no longer complete an incomplete approval
  (regression test).
- **(4) Public path/root injection removed.** `verify_activation_preconditions()`
  now takes NO parameters, `finalize_activation_candidate()` takes NO
  parameters, and `generate_active_partitions()` takes only
  `(approved_by, approval_reference, approved_at_utc)`. The
  caller-supplied `candidate_path` is GONE — the candidate path is canonical
  and derived from the data root. All injection moved to private
  `_verify_activation_preconditions_from` /
  `_finalize_activation_candidate_from` / `_generate_active_partitions_from`,
  whose roots are required positional parameters with no defaults.
  Signature-tested in both directions.
- **(5) Crash-safe atomic activation write.** `_atomic_write_text()` writes to
  an exclusively-created sibling `*.tmp`, flushes and `fsync`s it, re-checks
  that the target still does not exist, then `os.replace()`s atomically; any
  failure unlinks the temp file. A pre-existing stale `.tmp` is refused
  rather than overwritten. Failure-injection tests simulate a write error and
  an `fsync` error and prove neither the target nor the temp file survives,
  plus a race test proving a target that appears mid-write is never
  clobbered.
- **(6) NEW end-to-end synthetic success test.** `conftest.full_corpus_tree()`
  builds a COMPLETE synthetic repository and data root that satisfies every
  frozen corpus invariant (516 expected sessions; 318/100/98 trading days;
  317 observed DEV sessions; 309 eligible; 8 excluded; 10 quarantined dates;
  77 MBO sessions in 30 blocks distributed 23/23/31; 0 spanning; 8 causal
  roll switches) under the PA-0002 quarantine disposition with an APPROVED
  synthetic policy. `TestEndToEndSyntheticActivation` then runs the whole
  chain: approved policy → mechanical candidate → canonical envelope path →
  exact SHA-256 → machine-readable approval entry → `partitions_active.yaml`
  written by the real generator → reload through the FULL public verifier →
  DEV and SELECTION ranges permitted → every kind of HOLDOUT overlap refused
  (start, end, whole span, straddles on both sides, envelopment) →
  `holdout_opening()` still refuses unconditionally. It also proves the
  neutral proposal is untouched and its hash differs from the candidate's,
  that a second activation is refused, and that tampering with the candidate
  breaks the reloaded fence. **This is a synthetic temporary tree only; the
  real repository, the real data root, and the real policy are untouched.**
- **(7) Live state re-verified after the change:** the policy is still
  `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL`; all three public activation
  entry points REFUSE against the live repository; the public fence and
  research API still fail closed; the on-disk partition proposal is still
  `PROPOSED_NOT_ACTIVE` with `activation_ready=false`; the calendar remains
  `PROVISIONAL_PENDING_DATES_QUARANTINED`; no
  `partition_activation_candidate.json` and no `partitions_active.yaml`
  exist anywhere.
- **Unresolved risk / follow-up (NOT done here):** two governance documents
  still describe the older, weaker approval binding —
  `docs/protocol-amendments/PA-0002-research-eligibility-quarantine.md` §6
  ("the exact partition-proposal, effective-calendar, evidence-matrix,
  GCC-correspondence and research-eligibility-policy hashes") and
  `docs/holdout-policy.md` §1 (same list). The IMPLEMENTED binding is
  strictly STRONGER — nine identities (candidate + eight dependencies) plus
  the exact ranges, approver, UTC timestamp, exact decision value,
  disposition and calendar state — so neither document is contradicted, but
  both understate what the code enforces. They should be brought up to date
  through the normal amendment/review process rather than edited silently in
  an implementation change.
- **Files changed:** `src/nqresearch/holdout.py` (candidate schema and
  verification, neutral-proposal verification, machine-readable approval
  binding, `_verify_calendar_evidence` return value),
  `src/nqresearch/activation.py` (private `_..._from` helpers, no-injection
  public API, `_candidate_payload`, `_read_candidate`, `_atomic_write_text`,
  complete-substance comparison), `tests/unit/conftest.py` (complete
  provenance envelope; full synthetic corpus builder),
  `tests/unit/test_holdout_fence.py` (candidate/proposal split, candidate
  identity/substance/envelope regressions),
  `tests/unit/test_activation.py` (machine-readable approval matrix,
  signature tests, atomic-write failure injection, end-to-end activation).
  No configuration file changed; no artifact regenerated.
- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0057 — Fourth-round activation remediation: strict `activated`, validated UTC approval instant, create-once atomic publication, PA-0003 documentation amendment

- **Category:** remediation of four reproduced review findings against the
  AL-0056 activation tooling, plus a protocol documentation amendment.
  AL-0055, AL-0056 and every earlier entry are unchanged. **No activation
  occurred, no artifact was regenerated, no real candidate exists, the
  research-eligibility policy remains unapproved, and
  `config/data/partitions_active.yaml` still does not exist.**

- **(1) DEFECT FIXED - `activated` accepted coerced truthy values.**
  `ActivePartitions.activated` was an ordinary `bool`, so pydantic's lax mode
  accepted `1`, `"true"` and `"yes"` as an ACTIVE partition configuration -
  the single flag that turns research data access on. It is now `StrictBool`,
  and the model validator requires `self.activated is not True` to fail
  rather than the previous truthiness test `if not self.activated`. Only the
  literal YAML/Python boolean `true` can activate. Adversarial tests cover
  `0`, `1`, `-1`, `"true"`, `"false"`, `"yes"`, `"no"`, `"True"`, `"False"`,
  `"on"`, `"off"`, `""`, `"1"`, `"0"`, `None`, `[]`, `{}`, `[True]`,
  `{"activated": True}`, `1.0` and `0.0`, plus a RAW-YAML variant that
  exercises the loader itself (PyYAML's genuine boolean spellings `true`,
  `yes`, `on`, `True` must load; `1` and `y` must fail closed). A reflective
  test now walks EVERY pydantic model in `holdout.py` and asserts that no
  `bool` field is lax - strictness lives in the field metadata
  (`StrictBool == Annotated[bool, Strict()]`), not the annotation, so the
  test inspects `field.metadata`. Audit result: the other activation-critical
  booleans (`generation_git_clean`, `structural_ready`, `activation_ready`,
  `tentative`) and the counts (`trading_days`,
  `n_quarantined_calendar_dates`) were already strict from AL-0049/AL-0056;
  `activated` was the only lax one.

- **(2) DEFECT FIXED - the approval timestamp was formatted before it was
  validated.** `generate_active_partitions()` called
  `approved_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ")` on the caller's raw value.
  A `+08:00` wall time was therefore stamped with a literal `Z` WITHOUT
  conversion, and the resulting string re-parsed cleanly through
  `ApprovalRecord`, so the permanent record would have falsely claimed a
  local time was UTC. New `activation._validated_utc_instant()` runs as the
  FIRST statement of `_generate_active_partitions_from`, before any file is
  read or written, and refuses unless the value is an actual `datetime`, is
  timezone-aware, and has a UTC offset of exactly zero. **A non-UTC instant
  is REFUSED, never converted and never relabelled** - converting silently
  would also be wrong, because the approver's recorded intent is what must be
  audited. The format string is now the shared constant
  `APPROVAL_TIMESTAMP_FORMAT` and the payload uses the VALIDATED value, so
  the audit entry and the generated YAML contain exactly the same UTC
  instant. Tests: a valid UTC datetime; a zero-offset non-`timezone.utc`
  tzinfo (accepted - same instant); naive; `+08:00`; `-05:00`; `+00:01`; a
  `date`; two datetime-shaped strings; `None`; `0`; an int and a float epoch;
  `True`; and a duck-typed object exposing `strftime()`/`utcoffset()`. A
  source test asserts no unvalidated `approved_at_utc.strftime` remains.

- **(3) DEFECT FIXED - the create-once publication race.** `_atomic_write_text`
  checked `path.exists()` and then called `os.replace()`; a concurrent
  creator winning that window would have had its activation silently
  overwritten, because `os.replace()` overwrites by design. Publication now
  uses `os.link()` - an atomic create-if-absent operation on NTFS and POSIX
  alike, which raises `FileExistsError` (Windows `ERROR_ALREADY_EXISTS`) if
  the destination exists. The intervening `exists()` check was REMOVED
  entirely, so there is no window left to lose: the filesystem operation
  itself is the guard. The complete bytes are still written to an
  exclusively-created sibling `*.tmp` and `flush`+`fsync`ed BEFORE
  publication, so the destination only ever appears carrying complete durable
  content, and the temp entry is always removed afterwards. If the atomic
  primitive is unavailable (e.g. `EXDEV`), the write is REFUSED rather than
  falling back to an overwriting primitive. A surviving `*.tmp` still causes
  a FUTURE fail-closed refusal rather than being silently reused. Race
  regression: the test monkeypatches `os.link` itself so the destination is
  created immediately before the real publication call, and proves the
  existing file survives byte-for-byte; a second test creates the destination
  inside `os.fsync`; a third asserts the source contains no
  `os.replace`/`os.rename`/`shutil.move`/`.rename`/`.replace` (docstring and
  comments excluded, since they name the rejected primitives deliberately);
  a fourth injects `EXDEV` and proves refusal with no residue.

- **(4) PROTOCOL DOCUMENTATION SYNCHRONISED WITHOUT REWRITING HISTORY.**
  PA-0002 §6 and the earlier `docs/holdout-policy.md` §1 text describe the
  five-hash activation binding. **Neither was edited**: they are approved
  historical statements and are preserved verbatim. Instead a NEW amendment
  `docs/protocol-amendments/PA-0003-activation-binding-and-publication.md`
  is the authoritative description of the activation MECHANISM, recording:
  the candidate / neutral-proposal separation and the rule that the neutral
  proposal is never relabelled; all NINE bound hashes in a table; the exact
  machine-readable approval fields verbatim (including
  `- decision: APPROVE_PA_0002_ACTIVATION_CANDIDATE` and why the calendar
  state can never satisfy the disposition field); the strict-boolean rule;
  the strict zero-offset UTC rule; and the create-once publication contract
  with its six guaranteed properties. PA-0003 explicitly states it is NOT
  activation approval, NOT approval of the PA-0002 eligibility policy, and
  confers no permission to open HOLDOUT. Current-state documents now POINT to
  it: `docs/holdout-policy.md` §1 (both the activation paragraph and the
  PA-0002 paragraph), `docs/data-specification.md` §7 item 2, and the
  `CLAUDE.md` current-status list.

- **Verification (this round):** full suite **1162/1162 pass** (was 1104; +58);
  the end-to-end synthetic activation test still passes through the REAL
  generator and verifier; every coercive `activated` value fails; every
  non-UTC or malformed approval timestamp fails; the create-once race cannot
  overwrite an existing activation; `git diff --check` clean. Live state
  re-verified read-only: policy `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL`;
  all three activation entry points REFUSE; `load_active_partitions()` and
  `assert_research_range_allowed()` fail closed; the on-disk proposal is
  `PROPOSED_NOT_ACTIVE` / `activation_ready=false` /
  `PROVISIONAL_PENDING_DATES_QUARANTINED`; no
  `partition_activation_candidate.json`; no `partitions_active.yaml`; no
  artifact or configuration file regenerated. Raw vendor data, calendar
  evidence, HOLDOUT and FORWARD untouched; no normalization, feature, label,
  sample, dataset, model or experiment work occurred. All tests used
  temporary synthetic directories only; nothing under `D:\nq-research`,
  `D:\projects` or `D:\futures-data-research-s3-backup` was read, written,
  scanned or hashed.

- **Files changed:** `src/nqresearch/holdout.py` (StrictBool `activated`,
  exact-`True` validator), `src/nqresearch/activation.py`
  (`APPROVAL_TIMESTAMP_FORMAT`, `_validated_utc_instant`, create-once
  `_atomic_write_text`, validated stamp in the payload),
  `tests/unit/test_holdout_fence.py` (coercive-`activated` matrix, raw-YAML
  loader test, reflective strict-boolean audit),
  `tests/unit/test_activation.py` (UTC-instant matrix, create-once race
  regressions, primitive-source assertion), NEW
  `docs/protocol-amendments/PA-0003-activation-binding-and-publication.md`,
  `docs/holdout-policy.md`, `docs/data-specification.md`, `CLAUDE.md`,
  `docs/implementation-audit-log.md`.

- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0058 — Fifth-round activation remediation: whole-second approval instant, genuinely strict nested candidate schema, PA-0003 wording corrected to match the implementation

- **Category:** remediation of two reproduced review findings against the
  AL-0057 activation tooling, one of which was an inaccurate claim in my own
  PA-0003 text. AL-0055, AL-0056, AL-0057 and every earlier entry are
  unchanged. **No activation occurred, no artifact was regenerated, no real
  candidate exists, the research-eligibility policy remains unapproved, and
  `config/data/partitions_active.yaml` still does not exist.**

- **(1) DEFECT FIXED — sub-second approval instants were silently truncated.**
  `_validated_utc_instant()` accepted a zero-offset datetime carrying
  microseconds, but `APPROVAL_TIMESTAMP_FORMAT` (`%Y-%m-%dT%H:%M:%SZ`) records
  whole seconds only. The reviewer reproduced
  `2026-08-21T09:30:00.987654+00:00` being written as `2026-08-21T09:30:00Z`
  — **not the approved instant**, and worse, that string re-parses cleanly, so
  nothing downstream could detect the loss. The format is deliberately fixed
  to whole seconds so the approval record is byte-comparable, so the right
  fix is to REFUSE the input rather than change the format or discard
  precision: `microsecond != 0` now fails closed with an explicit instruction
  to re-approve with a whole-second timestamp. Truncating or rounding
  silently is exactly the failure mode this module exists to prevent.
  A second, belt-and-braces guard proves the accepted value ROUND-TRIPS
  through the fixed format unchanged, so no value that survives validation
  can ever be recorded as a different instant — a future format change
  cannot silently reintroduce the loss. Tests: whole-second UTC passes;
  microseconds `1`, `2`, `500`, `999`, `1000`, `123456`, `987654`, `999999`
  all fail; the exact reviewer-reproduced `.987654` case is asserted to
  format identically to the whole-second stamp and is refused; and a
  round-trip property test asserts that any accepted value re-parses to
  exactly the validated input. The microsecond case was also added to the
  generator-level refusal matrix, so `_generate_active_partitions_from`
  refuses it before touching any file.

- **(2) DEFECT FIXED — my PA-0003 strictness claim was stronger than the
  implementation.** PA-0003 stated the candidate schema used
  `extra="forbid"` "at every level". That was NOT true: `_CandidateCheck`
  used `extra="allow"`, and `_CandidateProposal.FORWARD` plus three other
  fields were plain `dict`. An invented field inside a structural check or
  inside the FORWARD descriptor would have been carried silently.
  Remediation, in the implementation first and only then in the wording:
  `_CandidateCheck` now declares exactly `check` / `status` / `detail` (the
  three fields `qa.status.check()` produces for the frozen structural checks)
  with `extra="forbid"` and `detail` REQUIRED; a new `_CandidateForward`
  model declares exactly `start` and `note` with `extra="forbid"` (FORWARD is
  a start-only descriptor — it has no end, because everything past the
  boundary is forward data);
  and `_verify_activation_evidence` now additionally requires EXACT equality
  between the candidate's raw `checks` and `proposal` mappings and the
  neutral proposal's, so `trading_days`, `tentative` and the whole FORWARD
  descriptor are compared literally rather than merely shape-checked.
  The three genuinely free-form mappings that remain —
  `structural_quarantine`, `mbo_sessions_per_partition` and
  `mbo_blocks_per_partition`, whose interiors are DERIVED rather than fixed
  — were already accepted only by exact equality against freshly recomputed
  evidence, and a new test asserts that this set is exactly those three and
  that each is named in the verifier.
  **PA-0003 §3 was rewritten to state precisely what is enforced**: every
  DECLARED Pydantic model (`ActivationCandidate`, `_CandidateProposal`,
  `_CandidateRange`, `_CandidateForward`, `_CandidateCheck`,
  `_CandidateIdentities`) forbids extras, while the remaining mapping
  payloads are accepted only through exact equality with recomputed
  evidence. The two mechanisms are described as complementary and neither is
  claimed to do the other's job. Tests prove an invented field inside a check
  (`severity`, `status_note`, `waived`), a check missing `detail`, and an
  invented field inside FORWARD (`end`, `eligible`, `trading_days`) are all
  refused, and a reflective test asserts `extra == "forbid"` on all six
  models so the PA-0003 sentence cannot drift away from the code again.

- **Documentation:** PA-0003 §3 (strictness, rewritten as above) and §6
  (retitled "Strict UTC, whole-second approval instant", documenting both
  silent-corruption modes and the round-trip guarantee);
  `docs/holdout-policy.md` §1 summary now states the whole-second
  requirement. PA-0002 and the historical five-hash sentences remain
  untouched.

- **Verification (this round):** full suite **1183/1183 pass** (was 1162; +21); the
  end-to-end synthetic activation chain still passes through the REAL
  generator and verifier; microsecond-bearing approval timestamps fail;
  nested invented candidate fields fail; `git diff --check` clean. Live state
  re-verified read-only: policy `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL`;
  all three activation entry points REFUSE; `load_active_partitions()` and
  `assert_research_range_allowed()` fail closed; the on-disk proposal is
  `PROPOSED_NOT_ACTIVE` / `activation_ready=false` /
  `PROVISIONAL_PENDING_DATES_QUARANTINED`; no
  `partition_activation_candidate.json`; no `partitions_active.yaml`; no
  artifact or configuration file regenerated. Raw vendor data, calendar
  evidence, HOLDOUT and FORWARD untouched; no normalization, feature, label,
  sample, dataset, model or experiment work occurred. All tests used
  temporary synthetic directories only; no D: location was read, written,
  scanned or hashed.

- **Files changed:** `src/nqresearch/holdout.py` (`_CandidateForward`,
  strict `_CandidateCheck`, exact-equality comparison of `checks`/`proposal`,
  corrected `ActivationCandidate` docstring),
  `src/nqresearch/activation.py` (microsecond refusal + round-trip guard),
  `tests/unit/test_holdout_fence.py` (nested-strictness regressions, check
  `detail`, reflective model audit), `tests/unit/test_activation.py`
  (sub-second refusal matrix, reproduced truncation case, round-trip
  property), `docs/protocol-amendments/PA-0003-activation-binding-and-publication.md`,
  `docs/holdout-policy.md`, `docs/implementation-audit-log.md`.

- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0059 — Activation tooling committed (immutable implementation commit `d309628`); nothing activated, nothing regenerated

- **Category:** protocol-relevant decision + commit record. AL-0055 through
  AL-0058 and every earlier entry are unchanged; this entry is appended after
  the implementation commit and is committed separately so that commit is
  never amended.
- **Immutable implementation commit:** `d309628919630f238bca09d2ce8923e24b2b0349`
  (message: "Activation tooling: nine-identity binding, strict approval,
  create-once publication"). It contains EXACTLY the eleven independently
  reviewed paths and nothing else:
  modified `CLAUDE.md`, `docs/data-specification.md`,
  `docs/holdout-policy.md`, `docs/implementation-audit-log.md`,
  `src/nqresearch/cli.py`, `src/nqresearch/holdout.py`,
  `tests/unit/conftest.py`, `tests/unit/test_holdout_fence.py`; new
  `docs/protocol-amendments/PA-0003-activation-binding-and-publication.md`,
  `src/nqresearch/activation.py`, `tests/unit/test_activation.py`.
  Pre-commit verification proved the staged set was exactly those eleven
  paths, that **no** `data/` path, raw vendor file, QA artifact, calendar
  evidence file, experiment database or generated experiment directory,
  activation candidate, `partitions_active.yaml`, or `config/data/*.yaml` was
  staged, that `docs/canonical-spec-v1.0.md` was unmodified, and that
  `git diff --cached --check` passed. The staged audit-log diff was
  `471 0` (471 added, 0 deleted), proving rule 21 append-only across
  AL-0055..AL-0058.
- **PA-0003 is included** in that commit
  (`docs/protocol-amendments/PA-0003-activation-binding-and-publication.md`)
  and is the authoritative description of the activation MECHANISM: the
  candidate / neutral-proposal separation, all nine bound identities, the
  exact machine-readable approval fields, the strict-boolean rule, the strict
  zero-offset whole-second UTC rule, and the create-once publication
  contract. PA-0001, PA-0002 and the historical five-hash sentences are
  preserved unchanged.
- **Verification after the implementation commit:** full unit suite
  **1183/1183** passing, including the end-to-end synthetic activation that
  drives the REAL generator and verifier against temporary synthetic trees.
  Working tree clean at the commit; `git diff --check` passes.
- **State explicitly UNCHANGED by this commit — committing TOOLING is not
  activation:**
  - research-eligibility policy remains **`IMPLEMENTED_PENDING_ACTIVATION_APPROVAL`**
    (PA-0002 is NOT approved);
  - calendar verification state remains
    **`PROVISIONAL_PENDING_DATES_QUARANTINED`**, and the ten pending dates
    remain truthfully `PENDING_EVIDENCE`;
  - the neutral partition proposal remains **`PROPOSED_NOT_ACTIVE` with
    `activation_ready=false`** (top-level status PASS);
  - **no activation candidate exists** — there is no
    `partition_activation_candidate.json` anywhere on the data volume;
  - **no `config/data/partitions_active.yaml` exists**;
  - **no real QA or closeout artifact was regenerated** — the twelve
    artifacts stamped at `37e38db` are byte-unchanged;
  - **partitions and HOLDOUT remain sealed**: verified live, all three
    activation entry points REFUSE, and both `load_active_partitions()` and
    `assert_research_range_allowed()` fail closed.
- **Data-volume scope:** no D: location was accessed or modified. Nothing
  under `D:\nq-research` was written; nothing under `D:\projects` or
  `D:\futures-data-research-s3-backup` was read, scanned, hashed, modified or
  deleted. Every test requiring activation files used temporary synthetic
  directories only. No normalization, feature, label, sample, dataset, model
  or experiment work occurred, and HOLDOUT/FORWARD were not accessed.
- **Not authorised and not done in this step:** approving PA-0002,
  regenerating artifacts, producing an activation candidate, creating an
  active partition configuration, or pushing. **Neither commit has been
  pushed**; pushing requires separate explicit approval.
- **Commit:** this entry is committed separately as an audit-log-only commit
  immediately after `d309628`; that implementation commit is NOT
  amended.

## AL-0060 — PA-0002 research-eligibility quarantine APPROVED by the project owner; policy transitioned to APPROVED_FOR_ACTIVATION (policy approval only — nothing activated)

- **Category:** protocol-relevant decision (human approval) + the
  configuration transition it authorises, prepared for independent review.
  AL-0055 through AL-0059 and every earlier entry are unchanged.
- **Decision.** The project owner, **Wian**, explicitly approved the PA-0002
  research-eligibility quarantine policy after independent review, and
  authorised transitioning `config/data/research_eligibility.yaml` from
  `IMPLEMENTED_PENDING_ACTIVATION_APPROVAL` to **`APPROVED_FOR_ACTIVATION`**.
  Approval date: 2026-08-20.
- **Exactly these ten calendar dates are quarantined from research
  eligibility** (unchanged from the proposal; not one added, removed or
  substituted):

  ```text
  2024-09-02  2024-11-29  2025-01-01  2025-01-20  2025-02-17
  2025-04-18  2025-05-26  2025-06-19  2025-07-03  2025-07-04
  ```

- **Counts (asserted mechanically, unchanged by the approval):** **10**
  quarantined calendar dates → **8** observed DEV sessions excluded → **309**
  eligible observed DEV sessions (of 317 observed, 318 DEV trading days).
  2025-01-01 is not a CME trading day and 2025-04-18 closes 08:15 CT before
  the 08:30 RTH open with no usable vendor records, so neither could ever
  have produced an RTH sample. Coverage stays 516 expected sessions;
  DEV/SELECTION/HOLDOUT stay 318/100/98 trading days; MBO stays 77 sessions /
  30 blocks with **0** quarantined blocks and **0** spanning blocks; the 8
  causal roll switches are unchanged.
- **Evidence truth preserved.** All ten dates remain truthfully
  **`PENDING_EVIDENCE`** in `config/data/cme_calendar_evidence.yaml`; the
  matrix and the calendar overrides are BYTE-UNCHANGED. Quarantine is a
  research-eligibility DISPOSITION, never a verification claim. The calendar
  verification state remains **`PROVISIONAL_PENDING_DATES_QUARANTINED`**.
- **THIS IS POLICY APPROVAL ONLY. It is NOT approval of an activation
  candidate and it does NOT activate partitions.** No activation candidate
  has been generated; no `config/data/partitions_active.yaml` exists; the
  neutral `partition_proposal.json` remains `PROPOSED_NOT_ACTIVE` with
  `activation_ready=false`; **HOLDOUT remains sealed**. Under PA-0003,
  activation additionally requires a generated candidate, a separately
  recorded human approval of that exact candidate's SHA-256 carrying the
  reserved machine-readable decision line, and only then the active
  configuration. **That decision line is deliberately NOT present in this
  entry** and is not authorised now.
- **Identities before → after this transition:**
  - research-eligibility policy SHA-256:
    `4dbd9432c24f5f7d86baf63c955c35ad7ca8a02225623ce445be26b150ad4bdc`
    → `b8678e628ea1dd25d8b7be05dbd6e24299bda002eec4593a223bf618c5620d0f`
  - effective config hash:
    `48c2d27ad59d14ecfda4b35690ee1ca5e6c56fedd2e8aa04380309763aa10ce5`
    → `3d4ad51132b60c612b6212ca058fcc04243bd371c40b82f8ef1dd17fe7958fbd`
  - package source hash: `ea44ea0b70457d4f643e9f38d6d0a2219e93f443bd40fdc2c78c7af056bf624f`
    (unchanged — no `src/` file was touched)
  - evidence-matrix SHA-256 binding: `f6099bd8…` (UNCHANGED)
- **ARTIFACT STALENESS — expected and required.** The eligibility policy is
  an input to `effective_config_hash()`, so changing it invalidates the
  config-keyed identity of **all 12 existing QA artifacts** (8 acquisition +
  coverage + MBO blocks + front series + partition proposal), which are
  stamped `config_hash 48c2d27a…` from commit `37e38db`. They are therefore
  now activation-INELIGIBLE by design. **No artifact was regenerated in this
  step** and regeneration is NOT authorised here: it must happen only after
  this transition is committed, from a clean committed tree, and only then
  may an activation candidate be produced. Approving the policy also
  invalidates the config-keyed QA caches, so that regeneration will incur a
  full re-decode — accepted, as recorded in AL-0055 item (6).
- **Change scope.** `config/data/research_eligibility.yaml`: ONLY
  `meta.status` and the stale comment that asserted the policy was
  "deliberately NOT approved while under review". The ten-date set, evidence
  states, reason codes, semantics, counts, matrix binding, rationale,
  canonical basis, policy id and version are all byte-identical.
- **Tests (rule 7 — changed requirement, documented).**
  `TestPolicyLifecycle` previously asserted the live policy was NOT
  activation-approved; that requirement was CHANGED by this authorised human
  decision, so those assertions are retargeted to pin the new state EXACTLY
  (`== APPROVED_FOR_ACTIVATION`, and still `not in`
  `NON_ACTIVATION_POLICY_STATES`). They were not relaxed: a new test proves
  every other lifecycle state — including the near-misses `APPROVED` and
  `approved_for_activation` — is still refused for activation. New
  `TestApprovedPolicyInvariants` pins the exact ten dates, all ten evidence
  states still `PENDING_EVIDENCE` in the live matrix, the 10 / 8 / 309 counts
  plus 516 / 77 / 30 / 0 / 8, the provisional calendar state, the reason
  codes and semantics, and the intact matrix binding. New
  `test_activation.py::TestLiveRefusal` was retargeted the same way: the
  SAFETY property (every live activation entry point must REFUSE) is
  unchanged and still pinned, but the expected REASON moved from the policy
  lifecycle to the stale-artifact envelope, and the test now asserts that new
  reason explicitly so a silent regression cannot pass as "still refusing".
  New `TestPolicyApprovalIsNotCandidateApproval` proves activation still refuses,
  no `partitions_active.yaml` exists, the fence and research API still fail
  closed, `holdout_opening()` still refuses, the neutral proposal state is
  still the only thing the generator can emit, and — mechanically — that
  **no `- decision:` line exists anywhere in this audit log**, so a policy
  approval can never be mistaken for candidate approval.
- **OBSERVATION FOR REVIEW (not fixed here, out of the authorised scope).**
  With the policy gate now cleared, `verify_activation_preconditions()`
  reaches the artifact-envelope check and raises
  `PartitionsNotActiveError` (from `holdout._verify_artifact_envelope`)
  rather than an `ActivationError`. The behaviour is fail-closed and correct
  — activation is refused because the artifacts are stale — but the exception
  type leaks across the module boundary instead of being wrapped like the
  other precondition failures. Recorded here rather than changed, because
  this step authorises only the policy transition. A regression test pins the
  current behaviour and asserts the refusal reason is the stale
  configuration, not a missing gate.
- **Verification:** full unit suite **1198/1198** passing;
  `git diff --check` clean. No artifact was regenerated (the four closeout
  artifacts retain their 2026-08-19 23:39 modification times); no activation
  candidate exists; no `config/data/partitions_active.yaml` exists; nothing
  under `D:\nq-research` was modified; nothing under `D:\projects` or
  `D:\futures-data-research-s3-backup` was read, scanned, hashed, modified or
  deleted; HOLDOUT and FORWARD data were not accessed and no normalization
  began.
- **Files changed:** `config/data/research_eligibility.yaml` (status +
  comment only), `CLAUDE.md`, `docs/data-specification.md`,
  `docs/holdout-policy.md`, `tests/unit/test_eligibility.py`,
  `tests/unit/test_activation.py`, `docs/implementation-audit-log.md`. Historical protocol statements
  (PA-0001, PA-0002, PA-0003) and all earlier audit entries are unchanged.
- **Commit:** none (stop-for-review rule); nothing pushed.

## AL-0061 — Activation exception boundary normalized to ActivationError; accurate record of read-only D:\nq-research access during the AL-0060 verification

- **Category:** implementation fix (remediation of the finding recorded in
  AL-0060) + a correction to my own reporting in that verification round.
  **AL-0060 is NOT altered** — it stands as written, including its
  "OBSERVATION FOR REVIEW" paragraph, which this entry resolves. AL-0055
  through AL-0059 and every earlier entry are likewise unchanged.

- **(1) DEFECT FIXED — fail-closed exceptions leaked out of the activation
  module.** `nqresearch.activation` advertises `ActivationError` as its
  refusal type, and `nqr data audit --part finalize-activation-candidate`
  catches exactly that. But the module reuses validators that live in other
  modules and raise their own fail-closed types, and several call sites were
  unwrapped, so an ENTIRELY EXPECTED refusal could escape as an uncaught
  traceback. Confirmed leaking sites:
  `_verify_artifact_envelope()` inside the activation-bound artifact loop of
  `_verify_activation_preconditions_from()` and inside the candidate check of
  `_generate_active_partitions_from()` (`PartitionsNotActiveError`);
  `load_validated_matrix()` (`CalendarEvidenceError`); and
  `verify_structural_quarantine_invariants()` (`EligibilityPolicyError`).
  The leak became reachable in practice only once AL-0060 cleared the policy
  gate, which is why it surfaced then.

- **Remediation.** New `activation._as_activation_error(context)` context
  manager translates EXACTLY three expected refusal types —
  `PartitionsNotActiveError`, `EligibilityPolicyError`,
  `CalendarEvidenceError` — into `ActivationError`, preserving the original
  message (`f"{context}: {original}"`) and chaining the original via
  `raise ... from e`. An `ActivationError` passing through is re-raised
  unchanged rather than double-wrapped. **There is deliberately no
  `except Exception` anywhere in the module** (asserted by a test): a
  `TypeError`, `AttributeError`, `KeyError`, `ValueError` or `RuntimeError`
  still propagates loudly instead of being disguised as an ordinary
  activation refusal. The two remaining broad JSON guards were narrowed to
  `(UnicodeDecodeError, json.JSONDecodeError)` and given proper chaining, and
  the `ActivePartitions` construction now catches only pydantic's
  `ValidationError`. Applied at every validation site plus, as a contract
  guard, at all three PUBLIC entry points —
  `verify_activation_preconditions()`, `finalize_activation_candidate()` and
  `generate_active_partitions()` — so nothing expected can leak from a future
  call site either.

- **CLI.** `nqr data audit --part finalize-activation-candidate` now always
  reaches its `except ActivationError` branch for an expected refusal,
  printing `[activation] REFUSED: …` and returning exit code 1 with no
  traceback. Regression-tested twice: once with a synthetic injected refusal,
  and once end-to-end against the real repository (which refuses because the
  twelve artifacts are stale), asserting exit code 1, the refusal line, the
  absence of "Traceback", and — before and after — that no candidate file was
  written.

- **Tests.** The temporary `(ActivationError, PartitionsNotActiveError)`
  tuples introduced in AL-0060 are REPLACED by strict `ActivationError`
  assertions in both `test_activation.py` and `test_eligibility.py`, and the
  live-refusal tests now additionally assert the chained
  `__cause__` is the original `PartitionsNotActiveError`. New
  `TestExceptionBoundary` (synthetic temporary trees only) covers: the
  no-`except Exception` invariant and that the translator names exactly the
  three expected types; five programming-error types passing through
  untranslated; each of the three expected types translated WITH message and
  chaining preserved; no double-wrapping; three stale-envelope mutations of a
  precondition artifact (stale config hash, stale package hash, dirty
  generation) with the proposal's embedded identity re-bound so the failure
  is proven to come from the ENVELOPE rather than a stale hash; six stale or
  malformed candidate mutations, each also asserting no
  `partitions_active.yaml` was created; and a corrupted evidence-matrix
  substance digest proving `CalendarEvidenceError` is translated too.

- **(2) CORRECTION TO MY OWN AL-0060 REPORTING — read-only D: access.** In the
  AL-0060 round I wrote that "nothing under `D:\nq-research` was modified"
  but also, in the session summary, phrasing that implied it had not been
  READ. That was imprecise. **Accurate record:** the 1198-test run and an
  explicit modification-time check performed **READ-ONLY** access to the
  existing closeout QA artifacts under
  `D:\nq-research\data\qa\m0_closeout\` (`mbp1_full_history_coverage.json`,
  `mbo_blocks_frozen.json`, `mbp1_front_contract_series.json`,
  `partition_proposal.json`) plus the immutable calendar-evidence reference
  files that matrix validation reads. That is how the live regression tests
  prove the real artifacts cannot activate. **No file under `D:` was written,
  modified, moved, renamed, deleted or regenerated**, and **no HOLDOUT or
  FORWARD market records were accessed, enumerated or decoded** — no raw
  vendor data was opened at all. The same read-only access occurred in this
  AL-0061 round.

- **Separately confirmed, and unchanged:** nothing under `D:\projects` and
  nothing under `D:\futures-data-research-s3-backup` was read, scanned,
  inventoried, hashed, modified or deleted at any point.

- **State unchanged by this entry.** Policy remains
  **`APPROVED_FOR_ACTIVATION`** (SHA-256 `b8678e62…`); the exact ten
  quarantined dates and the 10 / 8 / 309 counts are unchanged; all ten
  evidence states remain `PENDING_EVIDENCE`; the calendar remains
  `PROVISIONAL_PENDING_DATES_QUARANTINED`; **no activation candidate
  exists**; **no `config/data/partitions_active.yaml` exists**; the neutral
  proposal remains `PROPOSED_NOT_ACTIVE` with `activation_ready=false`;
  HOLDOUT remains sealed. **All 12 artifacts remain stale and
  byte-unchanged** — no regeneration and no normalization occurred.

- **Identity note.** This entry changes `src/nqresearch/activation.py`, so the
  **package source hash moves**: `ea44ea0b70457d4f643e9f38d6d0a2219e93f443bd40fdc2c78c7af056bf624f`
  -> `39eea4a5e93f31096fe96037d7414bc40a8a70af8fc684fcbe93196b34134a0c`. The
  effective config hash is unchanged at `3d4ad511…` (no config file was
  touched) and the policy SHA-256 is unchanged at `b8678e62…`. The twelve
  artifacts were already stale under the AL-0060 config-hash change; the
  package-hash move keeps them stale, which is the intended state until the
  reviewed clean-tree regeneration.

- **Verification:** full unit suite **1220/1220** passing;
  `git diff --check` clean; every expected activation refusal surfaces as
  `ActivationError`; the CLI refuses with exit code 1 and no traceback.

- **Files changed:** `src/nqresearch/activation.py` (exception translator,
  narrowed guards, public-boundary contract), `tests/unit/test_activation.py`
  (strict assertions, `TestExceptionBoundary`, `TestCliRefusesCleanly`),
  `tests/unit/test_eligibility.py` (strict assertions, docstring),
  `docs/implementation-audit-log.md`. No configuration file changed; the
  PA-0002 transition prepared in AL-0060 is carried forward untouched.

- **Commit:** none (stop-for-review rule); nothing pushed.
