# Holdout Policy (V1)

Derived from [canonical-spec-v1.0.md](canonical-spec-v1.0.md) §5.3, §6.3, §7, §71
(authoritative).

## 1. Definition

HOLDOUT is the final untouched chronological period of historical data, tentatively
~4–5 months. Exact dates are fixed during Milestone 0 based only on data coverage, MBO
session availability, and desired development/selection length — **never on model
outcomes**. A boundary near `2026-04-01` was discussed during planning; Milestone 0
has since established exact broad-data coverage (516 expected sessions,
2024-08-19 → 2026-08-14) and produced a structurally valid HOLDOUT proposal at
exactly that boundary (2026-04-01 → 2026-08-14) — the proposal remains
tentative and unactivated pending completion of the PA-0001 date-level
calendar evidence and explicit human approval (see the Status paragraph
below). Any MBO session
falling inside HOLDOUT is itself HOLDOUT and is excluded from all MBO
discovery and ladder development.

**Status: a structurally valid HOLDOUT proposal now exists but is NOT
active.** The Milestone 0 closeout (data-spec §6a/§6b, audit-log AL-0028)
proposes HOLDOUT = 2026-04-01 → 2026-08-14 (98 trading days ≈ 4.5 months,
31 MBO sessions / 11 whole blocks) with all structural partition gates
passing; the proposal remains `PROPOSED_NOT_ACTIVE`,
`PROVISIONAL_DOCUMENT_VERIFICATION_PENDING`, `activation_ready=false`.
Calendar verification follows the **date-level evidence policy PA-0001**
(docs/protocol-amendments/PA-0001-cme-calendar-evidence-policy.md; data-spec
§6c), adopted after CME GCC officially confirmed no archive of previous
years' holiday calendars exists. Activation requires ALL of: every
exceptional calendar date `DOCUMENT_VERIFIED` or
`TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE` with no conflicts
(`config/data/cme_calendar_evidence.yaml`, mechanically validated against
the immutable evidence files and the live coverage artifact); all
calendar/MBO-block/partition structural checks PASS; the activation binding
the exact SHA-256 of the approved proposal, effective calendar, evidence
matrix and GCC correspondence; and an append-only audit-log entry recording
explicit human approval of those exact hashes (all enforced fail-closed by
`nqresearch/holdout.py`).

**The activation mechanism is now stricter than the sentence above — see
[PA-0003](protocol-amendments/PA-0003-activation-binding-and-publication.md)
(authoritative).** In summary: the artifact a human approves is a SEPARATE
`partition_activation_candidate.json`, and the neutral
`partition_proposal.json` always stays `PROPOSED_NOT_ACTIVE` and is never
relabelled; **nine** SHA-256 identities are bound (that candidate plus the
eight dependencies — proposal, effective calendar, evidence matrix, GCC
correspondence, research-eligibility policy, coverage, MBO blocks, front
series); the approval entry must carry each required value exactly once as a
machine-readable `- key: value`, including
`- decision: APPROVE_PA_0002_ACTIVATION_CANDIDATE`; `activated` is a strict
boolean (`1`/`"true"`/`"yes"` never activate); `approved_at_utc` must be a
timezone-aware **whole-second** datetime with exactly zero offset — a
non-UTC value is refused rather than relabelled `Z`, and a
microsecond-bearing value is refused rather than truncated, since the
approval format records whole seconds only; and
`config/data/partitions_active.yaml` is published with an atomic
create-if-absent operation that can never overwrite an existing activation.
PA-0003 changes no evidence state and is not activation approval.

Under the proposed **PA-0002 research-eligibility quarantine** (data-spec
§6d) the ten `PENDING_EVIDENCE` dates are dispositioned — not verified —
by a committed policy (`config/data/research_eligibility.yaml`), whose
SHA-256 becomes a further mandatory activation binding alongside the
proposal, effective-calendar, evidence-matrix and GCC-correspondence hashes
(and, per PA-0003, the activation-candidate, coverage, MBO-blocks and
front-series hashes — nine in total).
All ten lie inside DEV; **none is in SELECTION or HOLDOUT and none is a
partition boundary**, so HOLDOUT is entirely unaffected and remains sealed.
`CONFLICT_REQUIRES_REVIEW` can never be dispositioned by quarantine, the
calendar is never relabelled `DOCUMENT_VERIFIED` (it stays
`PROVISIONAL_PENDING_DATES_QUARANTINED`), and **quarantine alone is never
permission to open HOLDOUT** — the separate opening workflow of §4 below
still governs, and partitions remain `PROPOSED_NOT_ACTIVE` with
`activation_ready=false`.

Historical note: freezing the dates was a
Milestone 0 deliverable (canonical §60 items 11–12) and must precede feature
research.

## 2. Prohibitions during ordinary development (§6.3)

HOLDOUT may not be used for: feature design; model selection; threshold selection;
visual inspection; MBO exploration; hyperparameter selection; debugging results; regime
definition; candidate rescue. Only a frozen evaluation plan may access it.

## 3. Mechanical protection (§7)

Protection must be mechanical, not merely documented:

- `<data_root>/holdout/` protected by filesystem permissions; the normal development
  user has no direct read permission (canonical §7 writes `data/holdout/`; the
  physical location follows the configured data root — currently
  `D:/nq-research/data/holdout/` — per the operational mapping in
  [architecture.md](architecture.md) §3a);
- the data loader refuses HOLDOUT date ranges by default; an explicit override flag is
  required and every override writes an immutable audit entry;
- Claude Code permissions/hooks deny HOLDOUT paths;
- no notebook may directly read holdout files;
- the HOLDOUT access command is separate from normal experiment execution.

## 4. Opening procedure (§7, §71)

Before an opening, commit `docs/holdout_plan_01.md` containing: exact frozen candidate
IDs; exact feature versions; exact label version; exact model configuration; exact
sample-table version; exact metrics; exact cost model; exact success/failure criteria;
exact outputs to be generated; and a statement that no modification is permitted during
the opening.

Maximum planned historical openings: **two** — #1 for the frozen V1 system; #2 only
after a genuinely documented methodological redesign (not ordinary tuning). Every
opening is permanent and logged.

During an opening, code may not be altered except to fix a demonstrable execution bug,
in which case the opening is contaminated and must be documented as such. The outcome is
reported PASS / FAIL / INCONCLUSIVE; a failed holdout is a valid project result. Holdout
output is never used for iterative rescue, and no optimization ever occurs around a
failed holdout.
