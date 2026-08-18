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
