# PA-0002 — Research-eligibility quarantine of ten evidence-pending calendar sessions

- **Date:** 2026-08-19
- **Status:** IMPLEMENTED, PENDING_INDEPENDENT_REVIEW (uncommitted at
  authoring time). **This amendment is NOT partition-activation approval**
  and confers no permission to open HOLDOUT.
- **Relationship to PA-0001:** supplements, does not weaken. PA-0001's
  evidence thresholds are unchanged, no evidence state is upgraded, and no
  evidence claim, file, hash, or tier is altered.

## 1. What this amendment does

The ten calendar sessions below are marked **research-ineligible
(quarantined)**. They remain, unchanged, in the effective calendar, in
coverage accounting, and in the evidence matrix at their true state
`PENDING_EVIDENCE`.

```text
2024-09-02  2024-11-29  2025-01-01  2025-01-20  2025-02-17
2025-04-18  2025-05-26  2025-06-19  2025-07-03  2025-07-04
```

Ten *calendar exceptions* are quarantined, but only **eight observed DEV
sessions** are actually lost to research: `2025-01-01` is not a CME trading
day at all (no session exists), and `2025-04-18` (Good Friday) closes at
08:15 CT — before the 08:30 RTH open — and additionally has no usable
vendor records. Neither could ever have produced an RTH sample under the V1
design, so the research cost of this amendment is 8 of 317 observed DEV
sessions (2.5%), leaving **309 eligible observed DEV sessions**.

## 2. Canonical basis

Canonical §50 lists, among the **allowed** exclusions, a *"predefined
holiday/partial-session rule"*, and requires that every exclusion carry a
machine-readable reason. Every quarantined date is a holiday or
partial/shortened session, and the rule is defined **in advance of any
feature, label, model, or result** — it is therefore an allowed, predefined
exclusion and explicitly not one of §50's forbidden outcome-driven
exclusions ("bad P&L day", "unusual market", "model doesn't work here",
outliers removed after seeing performance, event days removed because they
hurt results). The machine-readable code is
`PREDEFINED_HOLIDAY_PARTIAL_SESSION_RULE`.

## 3. Why the missing documentation creates a self-consistent-calendar risk

CME GCC confirmed in writing (PA-0001) that no archive of previous years'
holiday calendars exists, so official schedules for these dates cannot be
obtained. For eight of the ten, the canonical MBP-1 corpus shows the
session ending exactly at the shortened close our baseline calendar
predicts, agreeing to within 0.3 seconds. That agreement is strong, but it
is **agreement between our data and our own calendar**. If the baseline
calendar were wrong about one of these dates, the error would reproduce
itself consistently through session assignment, RTH windowing, label
horizons and evaluation, and nothing downstream would reveal it. PA-0001
requires an *independent* corroborating source precisely to break that
circularity; for these ten dates no qualifying independent source exists.

## 4. Why quarantine rather than weakening PA-0001

Retaining these sessions under an "archive-unavailable exception" would
mean training and evaluating on sessions whose scheduled structure rests on
a single, self-referential source. The cost of the alternative is small and
bounded — eight sessions, 2.5% of DEV — while the failure it prevents is
silent and systematic. Quarantine also keeps PA-0001's threshold intact
rather than establishing a precedent that an inconvenient evidence gap can
be dissolved by exception. The evidence record therefore stays truthful:
these dates are *pending*, not *verified*, and they are excluded from
research **because** they are pending.

## 5. Policy semantics

- **Raw data remains immutable.** Nothing under `<data_root>/raw/` is
  touched, moved, or reinterpreted.
- **Calendar evidence remains `PENDING_EVIDENCE`** for all ten dates. No
  `EVIDENCE_STATES` value is added, and no date is relabelled. The
  effective calendar remains explicitly PROVISIONAL.
- **Dates remain in the effective calendar and in coverage accounting.**
  Removing them would change `next_trading_day()` and break partition
  contiguity; coverage stays at 516 expected sessions and research
  eligibility is a **separate mask**, never a deletion.
- **Normalization and QA may process them** for session reconstruction,
  boundary/halo handling and QA reporting.
- **Research may never use or cross them**: no sample may be emitted for a
  quarantined session; no feature window, label horizon, or evaluation
  window may span one; rolling state must reset at the next eligible
  session.
- **Partition ranges remain contiguous date ranges** — DEV 2024-08-19 →
  2025-11-07, SELECTION 2025-11-10 → 2026-03-31, HOLDOUT 2026-04-01 →
  2026-08-14 — with trading-day counts unchanged at 318 / 100 / 98.
- **No MBO block is quarantined.** No quarantined date is an MBO session or
  falls inside any block span (the earliest block begins 2025-08-18, after
  every quarantined date); the inventory stays 77 sessions in 30 blocks
  with zero partition-spanning blocks.
- **The causal front-contract series is unaffected and must not consume the
  eligibility mask.** No quarantined date is a `decided_from_session`; the
  eight causal roll switches are unchanged. `2025-06-19` remains recorded
  as roll-week adjacent to the 2025-06-17 NQM5→NQU5 switch in the
  data-level series while being excluded from research sampling.
- **HOLDOUT remains sealed.** Every quarantined date lies in DEV; none is
  in SELECTION or HOLDOUT, and none is a partition boundary. Quarantine
  alone is never permission to open HOLDOUT.

## 6. Activation disposition (truth-preserving)

Activation eligibility is evaluated by a **separate resolution check**, not
by editing evidence:

- `DOCUMENT_VERIFIED` and `TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE`
  remain evidence-complete;
- `CONFLICT_REQUIRES_REVIEW` always blocks and can **never** be resolved by
  quarantine;
- a `PENDING_EVIDENCE` date may be dispositioned only if it appears exactly
  in the reviewed quarantine policy, and every pending date must be so
  covered — an extra, missing, or substituted date fails closed;
- the resulting disposition is named `PENDING_DATES_QUARANTINED` and the
  artifact-level calendar state remains the explicitly provisional
  `PROVISIONAL_PENDING_DATES_QUARANTINED`. The calendar is never relabelled
  `DOCUMENT_VERIFIED`.

Activation may proceed only under that disposition **after** all other
gates pass and explicit human approval binds the exact partition-proposal,
effective-calendar, evidence-matrix, GCC-correspondence and
research-eligibility-policy hashes in an append-only audit entry.

## 7. Scope and non-claims

No partition is activated; `config/data/partitions_active.yaml` does not
exist; the proposal remains `PROPOSED_NOT_ACTIVE` with
`activation_ready=false`. No artifact was regenerated, no normalization,
feature, label, sample, or model work was performed, and HOLDOUT/FORWARD
data was not accessed.
