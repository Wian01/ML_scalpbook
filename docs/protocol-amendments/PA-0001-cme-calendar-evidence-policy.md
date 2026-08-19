# PA-0001 — CME calendar evidence policy: date-level verification with an explicit archive-unavailable triangulation state

- **Date:** 2026-08-19
- **Status:** IMPLEMENTED, PENDING_INDEPENDENT_AUDIT (uncommitted at
  authoring time; commit SHA recorded in the audit log once one exists)
- **Amends:** the activation precondition, introduced at Milestone 0
  closeout (AL-0026/AL-0027/AL-0036), that every recurring holiday group of
  the effective calendar be `DOCUMENT_VERIFIED` against an official CME
  document before partitions may activate. The canonical V1.0 spec text is
  NOT modified; this amendment governs the *evidence standard* for the
  calendar underlying partitions/holdout mechanics (holdout policy §
  activation preconditions; docs/holdout-policy.md updated accordingly).

## 1. Justification (why the old requirement is impossible)

CME GCC replied in writing on 2026-08-19 (case 04700128; DKIM-verified
`d=cmegroup.com`; original `.eml` preserved immutably at
`<data_root>/reference/cme_calendar/2026-08-19_cme-gcc_no-historical-holiday-archive.eml`,
SHA-256 `67adfa61f089b3d99153d412843d3b20f1ecddae9b7541778fc7b0a6556004b0`):

> "Unfortunately we do not have an archive for previous years holidays
> calendar. You may refer to 2026 trading holidays in our CME Holiday HERE."

Official CME schedule documents for the 2024/2025 corpus dates therefore
**cannot be obtained from CME**. This correspondence proves archive
unavailability only; it does not prove any historical trading hours. This
amendment is **not** a claim that the missing CME documents were obtained.

## 2. Amended evidence model

Evidence is recorded and enforced **per exceptional date** (never only per
recurring holiday group) in the committed machine-readable matrix
`config/data/cme_calendar_evidence.yaml`, validated by
`src/nqresearch/calendar_evidence.py`.

States:

| State | Meaning |
|---|---|
| `DOCUMENT_VERIFIED` | An official CME artifact proves the applicable date and exact schedule. |
| `TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE` | CME officially confirms the archive is unavailable (verified GCC email), the canonical Databento records establish the observed session behaviour, at least one qualifying independent secondary source corroborates the applicable date/schedule, and no material conflict remains. |
| `PENDING_EVIDENCE` | Evidence is insufficient. Never silently upgraded. |
| `CONFLICT_REQUIRES_REVIEW` | Sources materially disagree. Blocks completion. |

Evidence hierarchy (tier gating is mechanical, fail-closed):

1. `OFFICIAL_CME` — official CME published schedule/export for the date.
2. `OFFICIAL_CME_CORRESPONDENCE` — GCC correspondence; establishes archive
   (un)availability ONLY, never session times.
3. Observed canonical Databento MBP-1 behaviour (per-date blocks in the
   matrix, mechanically cross-checked against the live coverage artifact).
4. `SECONDARY_STRONG` / `SECONDARY_PARTIAL` — e.g. NinjaTrader's 2026 CME
   equity-index schedule; AMP's CME-Globex-attributed dated tables; dated
   ForexLive/Insignia statements. Only these tiers, with `DIRECT` or
   `DOCUMENTED_INFERENCE` claims for the exact date, qualify as the
   independent corroboration a triangulated state requires.
5. `SECONDARY_LOWER` — CrossTrade: corroboration only where it agrees with
   stronger evidence; never sufficient alone.
6. `TERTIARY_DATE_ONLY` — Kibot: holiday dates/rules only; never NQ session
   times or session classifications.

Structural guarantees (all fail-closed, all adversarially tested):

- The matrix covers exactly the frozen 26-date exceptional-session set.
- A source supports only its declared `applicable_dates` — a 2026 document
  can never promote a 2024/2025 date; one verified year never promotes a
  multi-year group (groups roll up to the **weakest** member).
- Every evidence file SHA-256 is verified against the immutable copies under
  `<data_root>/reference/cme_calendar/`; fabricated hashes/states fail.
- Missing observed data blocks triangulation; recorded discrepancies force
  `CONFLICT_REQUIRES_REVIEW`.

## 3. Amended activation preconditions

Partitions may become eligible only when ALL hold:

1. Every applicable date is `DOCUMENT_VERIFIED` or
   `TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE`; no conflicts remain.
2. All calendar, MBO-block and partition structural checks PASS.
3. The active configuration binds the exact SHA-256 of: the approved
   partition proposal, the effective calendar, the evidence matrix file, and
   the GCC archive-unavailability correspondence.
4. An append-only audit-log entry records explicit human approval citing
   those exact hashes (mechanically verified by `nqresearch/holdout.py`).

The current proposal remains PROPOSED_NOT_ACTIVE and `activation_ready`
remains false: 10 of 26 dates are PENDING_EVIDENCE at amendment time.

## 4. Scope and non-claims

- No partition was activated; `config/data/partitions_active.yaml` does not
  exist; HOLDOUT/FORWARD remain untouched.
- Calendar *content* (holidays/early closes) is unchanged — this amendment
  changes the evidence standard and its enforcement, not any session time.
- The pending dates stay pending until qualifying evidence surfaces or an
  explicit reviewed decision addresses them.
