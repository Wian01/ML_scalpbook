# PA-0003 — Partition-activation binding, approval record, and active-configuration publication

- **Date:** 2026-08-20
- **Status:** IMPLEMENTED, PENDING_INDEPENDENT_REVIEW (uncommitted at
  authoring time). **This amendment is NOT partition-activation approval,
  is NOT approval of the PA-0002 research-eligibility policy, and confers no
  permission to open HOLDOUT.** No partition is activated by this document.
- **Relationship to PA-0001 and PA-0002:** supplements, never weakens.
  PA-0001's evidence thresholds and PA-0002's quarantine disposition are
  unchanged; no evidence state is upgraded and no evidence claim, file, hash,
  or tier is altered. This amendment only makes the ACTIVATION MECHANISM
  stricter.
- **Supersession note:** PA-0002 §6 and the earlier text of
  `docs/holdout-policy.md` §1 describe the activation binding as the five
  proposal / effective-calendar / evidence-matrix / GCC-correspondence /
  research-eligibility-policy hashes. Those statements are **historical and
  are not rewritten**. They are not contradicted — every one of those five
  hashes is still required — but they are now **incomplete**: this amendment
  is the authoritative description of what activation requires.

## 1. Why this amendment exists

The activation model implemented under PA-0002 had a structural gap: the
generated partition proposal was the only artifact bound by hash, so the
artifact a human actually approves either had no identity of its own or was
conflated with the neutral proposal. Three further defects were found by
independent review: an ordinary `bool` accepted `1` / `"true"` / `"yes"` as
an active flag; the approval timestamp was formatted with a literal `Z`
before its timezone was validated; and the active configuration was published
with an `exists()`-then-`replace()` pair that can overwrite a concurrently
created activation.

## 2. Separation of the neutral proposal from the activation candidate

Two DISTINCT artifacts exist under `<data_root>/qa/m0_closeout/`:

| Artifact | `artifact` field | State | Role |
|---|---|---|---|
| `partition_proposal.json` | `partition_proposal` | always `PROPOSED_NOT_ACTIVE`, `activation_ready=false` | the neutral mechanical SOURCE |
| `partition_activation_candidate.json` | `partition_activation_candidate` | `READY_FOR_ACTIVATION_APPROVAL`, `structural_ready=true`, `activation_ready=false` | the artifact human approval NAMES |

Rules:

- The neutral proposal is **never overwritten, relabelled, or reused** as the
  candidate. A `partition_proposal.json` declaring the candidate state is
  refused fail-closed.
- A generated artifact can never self-certify approval of its own bytes,
  because its own SHA-256 does not exist while it is being written.
  `activation_ready=true` in ANY generated artifact is refused.
- Activation therefore requires **three independent records**: the
  structurally-ready candidate; a separately committed append-only
  human-approval audit entry; and `config/data/partitions_active.yaml`.

## 3. The nine bound identities

`config/data/partitions_active.yaml` binds NINE SHA-256 identities. The
candidate identity is a field of its own and is never disguised as the
neutral proposal's hash.

| Field | Binds |
|---|---|
| `activation_candidate_sha256` | the exact approved `partition_activation_candidate.json` bytes |
| `partition_proposal_sha256` | the neutral `partition_proposal.json` bytes |
| `effective_calendar_sha256` | the merged effective calendar at approval time |
| `evidence_matrix_sha256` | committed `config/data/cme_calendar_evidence.yaml` |
| `cme_correspondence_sha256` | the immutable GCC archive-unavailability `.eml` |
| `research_eligibility_sha256` | committed `config/data/research_eligibility.yaml` (PA-0002) |
| `coverage_artifact_sha256` | `mbp1_full_history_coverage.json` |
| `mbo_blocks_sha256` | `mbo_blocks_frozen.json` |
| `front_contract_series_sha256` | `mbp1_front_contract_series.json` |

Both bound artifacts are proven by exact bytes, declared artifact type, and a
clean committed provenance envelope (AL-0043/44/45 policy) **before** any of
their content is trusted.

The candidate is then validated in two complementary ways, and the
distinction is deliberate — neither is claimed to do the other's job:

1. **Schema.** Every Pydantic model declared for the candidate —
   `ActivationCandidate`, `_CandidateProposal`, `_CandidateRange`,
   `_CandidateForward`, `_CandidateCheck` and `_CandidateIdentities` — sets
   `extra="forbid"`. An unexpected field at any of those levels, including
   inside an individual structural check or inside the FORWARD descriptor,
   is refused rather than silently carried. Booleans and integers are strict
   (§5) and the artifact/state/status values are `Literal`s.
2. **Exact equality against recomputed evidence.** Three fields remain
   free-form mappings because their shape is derived rather than fixed:
   `structural_quarantine`, `mbo_sessions_per_partition` and
   `mbo_blocks_per_partition`. The schema does not constrain their interior,
   so they are accepted ONLY by exact equality against evidence recomputed at
   verification time; an invented key inside one of them changes the mapping
   and is refused there. The `checks` list and the whole `proposal` mapping
   are likewise compared for exact equality with the neutral proposal, in
   addition to being schema-validated.

Everything else substantive is compared against evidence RECOMPUTED at
verification time — disposition, live policy lifecycle state, live
quarantined-date set, structural-quarantine facts, structural checks, MBO
distributions, and the exact DEV/SELECTION/HOLDOUT ranges, which must agree
across the active configuration, the candidate, and the neutral proposal.

## 4. The machine-readable approval record

`approval.approval_reference` must match `AL-\d{4}` exactly and resolve to
EXACTLY ONE line-anchored `## AL-nnnn` heading in
`docs/implementation-audit-log.md` (prefix collisions such as `AL-0055`
against `AL-00550` and duplicate headings are refused).

That entry must carry each of the following exactly once, in the literal form
`- key: value`. Prose is never sufficient, and any duplicate declaration of a
required key is refused as ambiguous.

```text
- decision: APPROVE_PA_0002_ACTIVATION_CANDIDATE
- activation_candidate_sha256: <64 hex>
- partition_proposal_sha256: <64 hex>
- effective_calendar_sha256: <64 hex>
- evidence_matrix_sha256: <64 hex>
- cme_correspondence_sha256: <64 hex>
- research_eligibility_sha256: <64 hex>
- coverage_artifact_sha256: <64 hex>
- mbo_blocks_sha256: <64 hex>
- front_contract_series_sha256: <64 hex>
- dev_range: YYYY-MM-DD..YYYY-MM-DD
- selection_range: YYYY-MM-DD..YYYY-MM-DD
- holdout_range: YYYY-MM-DD..YYYY-MM-DD
- approved_by: <approving identity>
- approved_at_utc: YYYY-MM-DDTHH:MM:SSZ
- quarantine_disposition: PENDING_DATES_QUARANTINED
- calendar_state: PROVISIONAL_PENDING_DATES_QUARANTINED
```

`decision` must be the exact value shown. A loose `APPROVE` substring is
never sufficient, and negations (`NOT_APPROVED`, `DO_NOT_APPROVE_…`,
`APPROVAL_REFUSED`) and near-misses are refused. The disposition and the
calendar state must be recorded INDEPENDENTLY: the calendar constant
`PROVISIONAL_PENDING_DATES_QUARANTINED` contains the disposition constant
`PENDING_DATES_QUARANTINED` as a substring, so one can never satisfy the
other.

## 5. Strict types in the active configuration

- `activated` is a **strict boolean**. Only the literal YAML/Python `true`
  activates research access; `1`, `1.0`, `"true"`, `"yes"`, `"on"`, `"1"`
  and every other truthy-but-not-boolean value are refused fail-closed.
- Every activation-critical boolean in the candidate schema
  (`generation_git_clean`, `structural_ready`, `activation_ready`,
  `tentative`) and every count (`trading_days`,
  `n_quarantined_calendar_dates`) is likewise strict, so a coerced value can
  never stand in for a declared fact.

## 6. Strict UTC, whole-second approval instant

`approved_at_utc` must be an actual timezone-aware `datetime` whose UTC
offset is **exactly zero** and whose **microsecond component is zero**. A
naive datetime, a `date`, a string, `None`, an arbitrary object, any non-zero
offset (`+08:00`, `-05:00`, `+00:01`), or any sub-second precision is REFUSED
before anything formats it.

Two distinct silent-corruption modes are closed here:

- A non-UTC instant is **never converted and never relabelled** with a
  literal `Z`: relabelling `09:30+08:00` as `09:30Z` would make the permanent
  record lie about when approval happened.
- A sub-second instant is **never truncated or rounded**: the approval format
  `%Y-%m-%dT%H:%M:%SZ` is intentionally fixed to whole seconds so the record
  is byte-comparable, which means `09:30:00.987654Z` could only be written as
  `09:30:00Z` — a different instant from the one approved. The approver
  re-states a whole-second timestamp instead.

The validator additionally proves the accepted value round-trips through the
fixed format without loss, so no value that survives validation can ever be
recorded as a different instant. The audit entry and the generated YAML
therefore contain exactly the validated UTC instant.

## 7. Create-once publication of the active configuration

`config/data/partitions_active.yaml` is published with an atomic
**create-if-absent** operation: the complete bytes are written to a sibling
temporary file and flushed to stable storage (`flush` + `fsync`) first, then
published via `os.link()`, which the filesystem (NTFS and POSIX alike)
performs only if no entry of that name exists.

`os.replace()` / `os.rename()` are deliberately NOT used: they overwrite, and
any `exists()`-then-`replace()` pair leaves a window in which a concurrent
creator silently loses its activation.

Guaranteed properties:

1. the destination only ever appears carrying complete, flushed bytes;
2. an existing activation is never overwritten;
3. a concurrent creator wins safely;
4. a failure at any point leaves no partial activation;
5. a temporary file surviving a crash causes a FUTURE fail-closed refusal
   rather than being silently reused;
6. if the atomic primitive is unavailable, the write is refused rather than
   falling back to an overwriting primitive.

## 8. Scope and non-claims

This amendment changes only the activation MECHANISM. It does not activate
any partition, does not approve the PA-0002 research-eligibility policy, does
not alter any evidence state, does not regenerate any artifact, and does not
open HOLDOUT. At authoring time the research-eligibility policy remains
`IMPLEMENTED_PENDING_ACTIVATION_APPROVAL`, the partition proposal remains
`PROPOSED_NOT_ACTIVE` with `activation_ready=false`, the calendar remains
`PROVISIONAL_PENDING_DATES_QUARANTINED`, no activation candidate exists, and
`config/data/partitions_active.yaml` does not exist.

## 9. Implementation and evidence

- `src/nqresearch/holdout.py` — `ActivePartitions` (nine identities, strict
  `activated`), `ActivationCandidate` strict schema, `_verify_neutral_proposal`,
  `_verify_activation_candidate`, `_verify_activation_evidence`,
  `_verify_approval_bound_to_audit_record`.
- `src/nqresearch/activation.py` — `_validated_utc_instant`,
  `_atomic_write_text` (create-once publication), `_candidate_payload`,
  and the no-injection public entry points.
- Audit-log entries **AL-0055**, **AL-0056**, **AL-0057**.
