# Holdout Policy (V1)

Derived from [canonical-spec-v1.0.md](canonical-spec-v1.0.md) §5.3, §6.3, §7, §71
(authoritative).

## 1. Definition

HOLDOUT is the final untouched chronological period of historical data, tentatively
~4–5 months. Exact dates are fixed during Milestone 0 based only on data coverage, MBO
session availability, and desired development/selection length — **never on model
outcomes**. A boundary near `2026-04-01` was discussed during planning but is NOT final
until Milestone 0 establishes exact broad-data coverage. Any MBO session falling inside
HOLDOUT is itself HOLDOUT and is excluded from all MBO discovery and ladder development.

**Status: HOLDOUT dates are not yet frozen.** Freezing them is a Milestone 0 deliverable
(canonical §60 items 11–12) and must precede feature research.

## 2. Prohibitions during ordinary development (§6.3)

HOLDOUT may not be used for: feature design; model selection; threshold selection;
visual inspection; MBO exploration; hyperparameter selection; debugging results; regime
definition; candidate rescue. Only a frozen evaluation plan may access it.

## 3. Mechanical protection (§7)

Protection must be mechanical, not merely documented:

- `data/holdout/` protected by filesystem permissions; the normal development user has
  no direct read permission;
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
