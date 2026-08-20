"""Activation tooling (PA-0002): fail-closed finalization, candidate identity
and substance, the nine-identity machine-readable human-approval binding,
atomic active-config generation, and a COMPLETE end-to-end synthetic
activation proving the whole chain actually works.

The LIVE repository is only ever exercised for REFUSAL. Every success path
uses synthetic approved-policy fixtures in temporary directories — never any
real data path, and never any sibling directory on the data volume.
"""

import hashlib
import inspect
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

import conftest as fx
from nqresearch.activation import (
    APPROVAL_TIMESTAMP_FORMAT,
    ActivationError,
    _atomic_write_text,
    _finalize_activation_candidate_from,
    _generate_active_partitions_from,
    _validated_utc_instant,
    _verify_activation_preconditions_from,
    finalize_activation_candidate,
    generate_active_partitions,
    verify_activation_preconditions,
)
from nqresearch.holdout import (
    APPROVAL_DECISION_VALUE,
    CANDIDATE_ARTIFACT_FILENAME,
    CANDIDATE_STATE_NOT_ACTIVE,
    CANDIDATE_STATE_READY,
    UNDERLYING_IDENTITY_FIELDS,
    ActivePartitions,
    PartitionsNotActiveError,
    _verify_approval_bound_to_audit_record,
)

APPROVER = "Wian van der Walt"
STAMP = datetime(2026, 8, 21, 9, 30, 0, tzinfo=timezone.utc)
STAMP_TEXT = "2026-08-21T09:30:00Z"
ALL_IDENTITY_KEYS = ["activation_candidate_sha256", *UNDERLYING_IDENTITY_FIELDS]
RANGES = {"dev": ("2099-01-05", "2099-03-31"),
          "selection": ("2099-04-01", "2099-05-29"),
          "holdout": ("2099-06-01", "2099-08-31")}


def _identities():
    return {k: hashlib.sha256(k.encode()).hexdigest()
            for k in ALL_IDENTITY_KEYS}


def _approval_entry(entry_id, identities, ranges=RANGES, approver=APPROVER,
                    stamp=STAMP_TEXT, decision=APPROVAL_DECISION_VALUE,
                    disposition=True, cal=True, omit=(), extra_lines=()):
    """A machine-readable approval entry: every field appears exactly once as
    ``- key: value``. Prose is never sufficient."""
    from nqresearch.calendar_evidence import (
        CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED,
        DISPOSITION_PENDING_DATES_QUARANTINED,
    )

    fields = {}
    if decision is not None:
        fields["decision"] = decision
    for k in ALL_IDENTITY_KEYS:
        fields[k] = identities[k]
    for name, (a, b) in ranges.items():
        fields[f"{name}_range"] = f"{a}..{b}"
    fields["approved_by"] = approver
    fields["approved_at_utc"] = stamp
    if disposition:
        fields["quarantine_disposition"] = DISPOSITION_PENDING_DATES_QUARANTINED
    if cal:
        fields["calendar_state"] = CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED
    for key in omit:
        fields.pop(key, None)
    lines = [f"## {entry_id} - human approval of the activation candidate", "",
             "Explicit human approval of the PA-0002 activation candidate.", ""]
    lines += [f"- {k}: {v}" for k, v in fields.items()]
    lines += list(extra_lines)
    return "\n".join(lines) + "\n"


class TestLiveRefusal:
    """Against the REAL repository the policy is still
    IMPLEMENTED_PENDING_ACTIVATION_APPROVAL, so every entry point refuses."""

    @pytest.mark.parametrize("fn", [verify_activation_preconditions,
                                    finalize_activation_candidate])
    def test_refuses_under_unapproved_live_policy(self, fn):
        with pytest.raises(ActivationError, match="lifecycle state"):
            fn()

    def test_generate_active_partitions_refuses_live(self):
        with pytest.raises(ActivationError):
            generate_active_partitions(APPROVER, "AL-9999", STAMP)

    def test_live_policy_is_not_approved(self):
        from nqresearch.eligibility import (
            NON_ACTIVATION_POLICY_STATES,
            load_policy,
        )

        assert load_policy().meta.status in NON_ACTIVATION_POLICY_STATES

    def test_no_real_active_configuration_exists(self):
        from nqresearch.config import _repo_root

        assert not (_repo_root() / "config" / "data"
                    / "partitions_active.yaml").is_file()

    def test_no_override_force_or_bypass_parameter_exists(self):
        for fn in (verify_activation_preconditions,
                   finalize_activation_candidate,
                   generate_active_partitions):
            params = set(inspect.signature(fn).parameters)
            assert not any(
                k in p for p in params
                for k in ("override", "force", "bypass", "allow",
                          "relax", "state", "skip")
            ), (fn.__name__, params)

    def test_public_api_has_no_path_or_root_injection(self):
        # A caller must never be able to point the PUBLIC entry points at a
        # fabricated tree or substitute a hand-written candidate file.
        banned = {"repo_root", "data_root", "root", "path", "candidate_path",
                  "config", "proposal_path"}
        for fn in (verify_activation_preconditions,
                   finalize_activation_candidate,
                   generate_active_partitions):
            params = set(inspect.signature(fn).parameters)
            assert not params & banned, (fn.__name__, params)
        assert set(inspect.signature(verify_activation_preconditions)
                   .parameters) == set()
        assert set(inspect.signature(finalize_activation_candidate)
                   .parameters) == set()
        assert list(inspect.signature(generate_active_partitions)
                    .parameters) == ["approved_by", "approval_reference",
                                     "approved_at_utc"]

    def test_private_helpers_require_explicit_roots(self):
        # The private helpers take roots POSITIONALLY and without defaults, so
        # no code path can silently fall back to an injected root.
        for fn in (_verify_activation_preconditions_from,
                   _finalize_activation_candidate_from,
                   _generate_active_partitions_from):
            for name in ("repo_root", "data_root"):
                p = inspect.signature(fn).parameters[name]
                assert p.default is inspect.Parameter.empty, (fn.__name__, name)
        assert "candidate_path" not in inspect.signature(
            _generate_active_partitions_from).parameters

    def test_module_never_opens_holdout_or_raw_market_data(self):
        # Precise check: the module may reference the holdout RANGE, but must
        # never touch holdout/raw DATA paths or vendor files.
        import nqresearch.activation as act

        src = inspect.getsource(act)
        for banned in ('paths.holdout', 'paths.raw', '/ "holdout"',
                       "/ 'holdout'", '.dbn', 'raw_mbp1', 'raw_trades',
                       'dbnio', 'read_dbn', 'iter_records', 'qa_corpus',
                       'research_session_records'):
            assert banned not in src, banned


class TestApprovalBinding:
    """The human-approval audit entry must bind the candidate identity AND all
    eight dependency identities, the exact ranges, the approver, the exact
    timestamp, the exact decision value, and the disposition/calendar state —
    all as unambiguous machine-readable fields."""

    def _env(self, tmp_path, entry_text=None, reference="AL-0055",
             approver=APPROVER, stamp=STAMP, extra_log=""):
        root = tmp_path / "repo"
        (root / "docs").mkdir(parents=True)
        (root / "config" / "data").mkdir(parents=True)
        ident = _identities()
        text = "# log\n\n" + (_approval_entry("AL-0055", ident)
                              if entry_text is None else entry_text)
        (root / "docs" / "implementation-audit-log.md").write_text(
            text + extra_log, encoding="utf-8")
        parts = ActivePartitions(**{
            "activated": True,
            "approval": {"approved_by": approver,
                         "approval_reference": reference,
                         "approved_at_utc": stamp},
            **ident,
            "dev": {"start": RANGES["dev"][0], "end": RANGES["dev"][1]},
            "selection": {"start": RANGES["selection"][0],
                          "end": RANGES["selection"][1]},
            "holdout": {"start": RANGES["holdout"][0],
                        "end": RANGES["holdout"][1]},
        })
        return parts, root, ident

    def test_complete_approval_entry_accepted(self, tmp_path):
        parts, root, _ = self._env(tmp_path)
        _verify_approval_bound_to_audit_record(parts, root)  # must not raise

    @pytest.mark.parametrize("omit", ALL_IDENTITY_KEYS)
    def test_each_missing_identity_rejected(self, tmp_path, omit):
        parts, root, ident = self._env(
            tmp_path,
            entry_text=_approval_entry("AL-0055", _identities(), omit=(omit,)))
        with pytest.raises(PartitionsNotActiveError,
                           match=f"missing the machine-readable approval "
                                 f"field '- {omit}"):
            _verify_approval_bound_to_audit_record(parts, root)

    def test_candidate_identity_is_bound_separately_from_the_proposal(self,
                                                                     tmp_path):
        # The candidate SHA must never be satisfiable by citing the neutral
        # proposal SHA: they are two distinct required fields.
        ident = _identities()
        disguised = dict(ident)
        disguised["activation_candidate_sha256"] = \
            ident["partition_proposal_sha256"]
        parts, root, _ = self._env(
            tmp_path, entry_text=_approval_entry("AL-0055", disguised))
        with pytest.raises(PartitionsNotActiveError,
                           match="activation_candidate_sha256"):
            _verify_approval_bound_to_audit_record(parts, root)

    @pytest.mark.parametrize("key", ALL_IDENTITY_KEYS)
    def test_each_wrong_identity_rejected(self, tmp_path, key):
        wrong = _identities()
        wrong[key] = "9" * 64
        parts, root, _ = self._env(
            tmp_path, entry_text=_approval_entry("AL-0055", wrong))
        with pytest.raises(PartitionsNotActiveError, match=key):
            _verify_approval_bound_to_audit_record(parts, root)

    @pytest.mark.parametrize("name", ["dev", "selection", "holdout"])
    def test_range_mismatch_rejected(self, tmp_path, name):
        bad = dict(RANGES)
        bad[name] = ("2098-01-01", "2098-02-02")
        parts, root, _ = self._env(
            tmp_path,
            entry_text=_approval_entry("AL-0055", _identities(), ranges=bad))
        with pytest.raises(PartitionsNotActiveError,
                           match=f"{name}_range"):
            _verify_approval_bound_to_audit_record(parts, root)

    def test_approver_mismatch_rejected(self, tmp_path):
        parts, root, _ = self._env(
            tmp_path,
            entry_text=_approval_entry("AL-0055", _identities(),
                                       approver="Someone Else"))
        with pytest.raises(PartitionsNotActiveError, match="approved_by"):
            _verify_approval_bound_to_audit_record(parts, root)

    def test_timestamp_mismatch_rejected(self, tmp_path):
        parts, root, _ = self._env(
            tmp_path,
            entry_text=_approval_entry("AL-0055", _identities(),
                                       stamp="2026-08-21T09:31:00Z"))
        with pytest.raises(PartitionsNotActiveError, match="approved_at_utc"):
            _verify_approval_bound_to_audit_record(parts, root)

    def test_missing_decision_field_rejected(self, tmp_path):
        # Prose alone ("APPROVED: PA-0002 ...") can never authorise activation.
        entry = _approval_entry("AL-0055", _identities(), decision=None)
        entry = entry.replace(
            "Explicit human approval of the PA-0002 activation candidate.",
            "APPROVED: PA-0002 and this exact partition candidate.")
        parts, root, _ = self._env(tmp_path, entry_text=entry)
        with pytest.raises(PartitionsNotActiveError, match="'- decision"):
            _verify_approval_bound_to_audit_record(parts, root)

    @pytest.mark.parametrize("decision", [
        "DO_NOT_APPROVE_PA_0002_ACTIVATION_CANDIDATE",
        "APPROVAL_REFUSED",
        "NOT_APPROVED",
        "APPROVE_PA_0002_ACTIVATION_CANDIDATE_LATER",
        "APPROVE",
    ])
    def test_negative_or_near_miss_decision_rejected(self, tmp_path, decision):
        parts, root, _ = self._env(
            tmp_path, entry_text=_approval_entry("AL-0055", _identities(),
                                                 decision=decision))
        with pytest.raises(PartitionsNotActiveError, match="'decision'"):
            _verify_approval_bound_to_audit_record(parts, root)

    @pytest.mark.parametrize("key", ["decision", "approved_by",
                                     "activation_candidate_sha256",
                                     "holdout_range"])
    def test_duplicate_field_rejected(self, tmp_path, key):
        ident = _identities()
        entry = _approval_entry("AL-0055", ident)
        # A second, identical declaration is still ambiguous and is refused.
        line = [ln for ln in entry.splitlines()
                if ln.startswith(f"- {key}:")][0]
        parts, root, _ = self._env(
            tmp_path, entry_text=entry + line + "\n")
        with pytest.raises(PartitionsNotActiveError, match="duplicate"):
            _verify_approval_bound_to_audit_record(parts, root)

    def test_conflicting_duplicate_field_rejected(self, tmp_path):
        entry = _approval_entry("AL-0055", _identities())
        parts, root, _ = self._env(
            tmp_path, entry_text=entry + "- decision: NOT_APPROVED\n")
        with pytest.raises(PartitionsNotActiveError, match="duplicate"):
            _verify_approval_bound_to_audit_record(parts, root)

    def test_fields_in_a_neighbouring_entry_do_not_count(self, tmp_path):
        # Approval must live INSIDE the referenced entry; a later entry's
        # fields can never complete an incomplete approval.
        incomplete = _approval_entry("AL-0055", _identities(), decision=None)
        neighbour = ("\n## AL-0056 unrelated\n\n"
                     f"- decision: {APPROVAL_DECISION_VALUE}\n")
        parts, root, _ = self._env(tmp_path, entry_text=incomplete,
                                   extra_log=neighbour)
        with pytest.raises(PartitionsNotActiveError, match="'- decision"):
            _verify_approval_bound_to_audit_record(parts, root)

    @pytest.mark.parametrize("flag,match", [
        ("disposition", "quarantine_disposition"),
        ("cal", "calendar_state"),
    ])
    def test_missing_disposition_or_calendar_state_rejected(self, tmp_path,
                                                            flag, match):
        kw = {flag: False}
        parts, root, _ = self._env(
            tmp_path,
            entry_text=_approval_entry("AL-0055", _identities(), **kw))
        with pytest.raises(PartitionsNotActiveError, match=match):
            _verify_approval_bound_to_audit_record(parts, root)

    def test_calendar_state_never_satisfies_the_disposition_field(self,
                                                                  tmp_path):
        # PROVISIONAL_PENDING_DATES_QUARANTINED CONTAINS
        # PENDING_DATES_QUARANTINED: the two must be recorded independently.
        from nqresearch.calendar_evidence import (
            CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED,
        )

        entry = _approval_entry("AL-0055", _identities(), disposition=False)
        entry += (f"- quarantine_disposition: "
                  f"{CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED}\n")
        parts, root, _ = self._env(tmp_path, entry_text=entry)
        with pytest.raises(PartitionsNotActiveError,
                           match="quarantine_disposition"):
            _verify_approval_bound_to_audit_record(parts, root)

    def test_prefix_heading_attack_rejected(self, tmp_path):
        # AL-0055 must NEVER match a heading AL-00550
        entry = _approval_entry("AL-00550", _identities())
        parts, root, _ = self._env(tmp_path, entry_text=entry)
        with pytest.raises(PartitionsNotActiveError, match="no entry"):
            _verify_approval_bound_to_audit_record(parts, root)

    def test_duplicate_heading_rejected(self, tmp_path):
        entry = _approval_entry("AL-0055", _identities())
        parts, root, _ = self._env(tmp_path, entry_text=entry,
                                   extra_log="\n" + entry)
        with pytest.raises(PartitionsNotActiveError, match="ambiguous"):
            _verify_approval_bound_to_audit_record(parts, root)

    def test_missing_entry_rejected(self, tmp_path):
        parts, root, _ = self._env(
            tmp_path, entry_text=_approval_entry("AL-0099", _identities()))
        with pytest.raises(PartitionsNotActiveError, match="no entry"):
            _verify_approval_bound_to_audit_record(parts, root)

    @pytest.mark.parametrize("ref", ["AL-055", "AL-55", "no reference here",
                                     "AL-abcd", "0055", "AL-0055 (synthetic)",
                                     " AL-0055", "AL-00550"])
    def test_unsupported_reference_forms_rejected(self, tmp_path, ref):
        with pytest.raises(PartitionsNotActiveError,
                           match="EXACTLY the supported form"):
            parts, root, _ = self._env(tmp_path, reference=ref)
            _verify_approval_bound_to_audit_record(parts, root)


class TestCandidateSemantics:
    def test_candidate_state_constants_are_distinct_and_explicit(self):
        assert CANDIDATE_STATE_READY == "READY_FOR_ACTIVATION_APPROVAL"
        assert CANDIDATE_STATE_NOT_ACTIVE == "PROPOSED_NOT_ACTIVE"
        assert CANDIDATE_STATE_READY != CANDIDATE_STATE_NOT_ACTIVE

    def test_candidate_artifact_is_separate_from_the_neutral_proposal(self):
        from nqresearch.holdout import CANDIDATE_ARTIFACT_TYPE

        assert CANDIDATE_ARTIFACT_FILENAME == \
            "partition_activation_candidate.json"
        assert CANDIDATE_ARTIFACT_TYPE == "partition_activation_candidate"
        assert CANDIDATE_ARTIFACT_FILENAME != "partition_proposal.json"

    def test_generated_proposal_never_declares_itself_activation_ready(self):
        # The generator must not be able to emit activation_ready=true.
        import nqresearch.qa.closeout as co

        src = inspect.getsource(co)
        assert '"activation_ready": True' not in src
        assert '"activation_ready": False' in src

    def test_finalizer_marks_structural_ready_but_not_activation_ready(self):
        from nqresearch.activation import _candidate_payload

        src = inspect.getsource(_candidate_payload)
        assert '"structural_ready": True' in src
        assert '"activation_ready": False' in src
        assert '"activation_ready": True' not in src


class TestActiveConfigGeneration:
    """generate_active_partitions() must refuse without a valid candidate AND
    a valid, already-committed human-approval entry."""

    def test_refuses_without_candidate_or_approval(self, tmp_path):
        root = tmp_path / "repo"
        (root / "config" / "data").mkdir(parents=True)
        (root / "docs").mkdir()
        (root / "docs" / "implementation-audit-log.md").write_text("# log\n")
        with pytest.raises(ActivationError):
            _generate_active_partitions_from(APPROVER, "AL-0055", STAMP,
                                             root, tmp_path / "dataroot")

    def test_refuses_to_overwrite_existing_activation(self, tmp_path):
        root = tmp_path / "repo"
        (root / "config" / "data").mkdir(parents=True)
        (root / "config" / "data" / "partitions_active.yaml").write_text(
            "activated: true\n")
        with pytest.raises(ActivationError, match="already exists"):
            _generate_active_partitions_from(APPROVER, "AL-0055", STAMP,
                                             root, tmp_path / "dataroot")

    def test_writes_only_the_tracked_config_file_atomically(self):
        src = inspect.getsource(_generate_active_partitions_from)
        # Exactly ONE write, through the crash-safe helper — no direct
        # write_text/open call anywhere in the generator.
        assert src.count("_atomic_write_text(") == 1
        assert src.replace("_atomic_write_text(", "").count("write_text") == 0
        assert "open(" not in src
        assert "ACTIVE_PARTITIONS_FILENAME" in src


class TestAtomicWrite:
    """A crash mid-write must never leave a half-written activation."""

    def test_writes_complete_content_and_leaves_no_temp_file(self, tmp_path):
        out = tmp_path / "partitions_active.yaml"
        _atomic_write_text(out, "activated: true\n")
        assert out.read_text(encoding="utf-8") == "activated: true\n"
        assert not (tmp_path / "partitions_active.yaml.tmp").exists()

    @pytest.mark.parametrize("target", ["write", "fsync"])
    def test_failure_mid_write_leaves_nothing_behind(self, tmp_path,
                                                     monkeypatch, target):
        import os as _os

        out = tmp_path / "partitions_active.yaml"
        if target == "fsync":
            monkeypatch.setattr(_os, "fsync",
                                lambda *_a: (_ for _ in ()).throw(
                                    OSError("simulated disk failure")))
        else:
            real = _os.fdopen

            class _Boom:
                def __init__(self, fh):
                    self._fh = fh

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    self._fh.close()
                    return False

                def write(self, _text):
                    raise OSError("simulated write failure")

            monkeypatch.setattr(_os, "fdopen",
                                lambda *a, **k: _Boom(real(*a, **k)))
        with pytest.raises(OSError):
            _atomic_write_text(out, "activated: true\n")
        assert not out.exists()
        assert not (tmp_path / "partitions_active.yaml.tmp").exists()

    def test_stale_temp_file_is_never_silently_overwritten(self, tmp_path):
        out = tmp_path / "partitions_active.yaml"
        (tmp_path / "partitions_active.yaml.tmp").write_text("partial")
        with pytest.raises(ActivationError, match="stale temporary"):
            _atomic_write_text(out, "activated: true\n")
        assert not out.exists()

    def test_existing_target_appearing_mid_write_is_never_clobbered(
            self, tmp_path, monkeypatch):
        # A concurrent creator that wins between the flush and the
        # publication must keep its file.
        import os as _os

        out = tmp_path / "partitions_active.yaml"
        real_fsync = _os.fsync

        def _racy(fd):
            real_fsync(fd)
            out.write_text("someone else activated\n", encoding="utf-8")

        monkeypatch.setattr(_os, "fsync", _racy)
        with pytest.raises(ActivationError, match="already exists"):
            _atomic_write_text(out, "activated: true\n")
        assert out.read_text(encoding="utf-8") == "someone else activated\n"
        assert not (tmp_path / "partitions_active.yaml.tmp").exists()

    def test_destination_created_immediately_before_publication_wins(
            self, tmp_path, monkeypatch):
        # THE remaining-window regression: the destination is created inside
        # the very call that publishes, i.e. after every check the writer
        # could possibly make. Only an ATOMIC create-if-absent publication
        # can refuse here; an exists()-then-replace() pair would overwrite.
        import os as _os

        out = tmp_path / "partitions_active.yaml"
        real_link = _os.link

        def _racing_link(src, dst, **kw):
            Path(dst).write_text("concurrent winner\n", encoding="utf-8")
            return real_link(src, dst, **kw)

        monkeypatch.setattr(_os, "link", _racing_link)
        with pytest.raises(ActivationError, match="already exists"):
            _atomic_write_text(out, "activated: true\n")
        assert out.read_text(encoding="utf-8") == "concurrent winner\n"
        assert not (tmp_path / "partitions_active.yaml.tmp").exists()

    def test_publication_never_uses_an_overwriting_primitive(self):
        # Inspect the CODE, not the docstring (which names the rejected
        # primitives on purpose).
        src = inspect.getsource(_atomic_write_text)
        body = "".join(ln for ln in src.splitlines(keepends=True)
                       if not ln.lstrip().startswith("#"))
        doc = _atomic_write_text.__doc__ or ""
        body = body.replace(doc, "")
        assert "os.link(" in body
        # os.replace/os.rename/shutil.move all overwrite the destination.
        for banned in ("os.replace(", "os.rename(", "shutil.move(",
                       ".rename(", ".replace("):
            assert banned not in body, banned

    def test_non_atomic_publication_failure_is_refused_not_retried(
            self, tmp_path, monkeypatch):
        # If the atomic primitive is unavailable (e.g. an exotic filesystem),
        # the write is REFUSED rather than falling back to something that
        # could overwrite.
        import errno
        import os as _os

        out = tmp_path / "partitions_active.yaml"

        def _boom(src, dst, **kw):
            raise OSError(errno.EXDEV, "cross-device link not permitted")

        monkeypatch.setattr(_os, "link", _boom)
        with pytest.raises(ActivationError, match="atomically"):
            _atomic_write_text(out, "activated: true\n")
        assert not out.exists()
        assert not (tmp_path / "partitions_active.yaml.tmp").exists()


def _write_candidate(data_root, payload):
    """Write the canonical candidate artifact with a clean provenance
    envelope, exactly as `nqr data audit --part finalize-activation-candidate`
    would, and return its path and exact SHA-256."""
    p = data_root / "qa" / "m0_closeout" / CANDIDATE_ARTIFACT_FILENAME
    p.write_text(json.dumps({**fx.clean_envelope(), **payload}, indent=2,
                            default=str), encoding="utf-8")
    return p, hashlib.sha256(p.read_bytes()).hexdigest()


class TestEndToEndSyntheticActivation:
    """The ONE genuine success path: an approved synthetic policy is carried
    all the way to an active configuration, reloaded through the full public
    verifier, and proven to permit DEV/SELECTION while refusing HOLDOUT."""

    def _activate(self, tmp_path):
        # 1. Approved synthetic policy over a complete, invariant-satisfying
        #    synthetic corpus.
        root, droot = fx.full_corpus_tree(tmp_path)
        # 2. Mechanical candidate (refuses unless every precondition holds).
        payload = _finalize_activation_candidate_from(root, droot)
        # 3./4. Canonical envelope path and the exact identity it produces.
        _, candidate_sha = _write_candidate(droot, payload)
        # 5. The separately recorded human approval, naming that exact SHA.
        ident = {"activation_candidate_sha256": candidate_sha,
                 **payload["bound_identities"]}
        ranges = {name.lower(): (payload["proposal"][name]["start"],
                                 payload["proposal"][name]["end"])
                  for name in ("DEV", "SELECTION", "HOLDOUT")}
        log = root / "docs" / "implementation-audit-log.md"
        log.write_text(
            log.read_text(encoding="utf-8") + "\n"
            + _approval_entry("AL-0056", ident, ranges=ranges),
            encoding="utf-8")
        # 6. The active configuration itself.
        out = _generate_active_partitions_from(APPROVER, "AL-0056", STAMP,
                                               root, droot)
        return root, droot, out, candidate_sha, ranges

    def test_full_chain_activates_and_fences_correctly(self, tmp_path):
        from nqresearch.holdout import (
            HoldoutAccessError,
            HoldoutFenceError,
            _check_range,
            _load_active_partitions_from,
            _verify_activation_evidence,
            holdout_opening,
        )

        root, droot, out, candidate_sha, ranges = self._activate(tmp_path)
        assert out.is_file()
        written = yaml.safe_load(out.read_text(encoding="utf-8"))
        # The candidate identity is bound in its OWN field, never disguised as
        # the neutral proposal SHA.
        assert written["activation_candidate_sha256"] == candidate_sha
        assert written["partition_proposal_sha256"] != candidate_sha
        assert all(k in written for k in UNDERLYING_IDENTITY_FIELDS)

        # 7. Reload through the FULL verifier (schema + activation evidence).
        parts = _load_active_partitions_from(root)
        _verify_activation_evidence(parts, root, droot)

        # 8. DEV and SELECTION are permitted.
        dev_a, dev_b = (date.fromisoformat(x) for x in ranges["dev"])
        sel_a, sel_b = (date.fromisoformat(x) for x in ranges["selection"])
        _check_range(dev_a, dev_b, parts)
        _check_range(sel_a, sel_b, parts)
        _check_range(dev_a, sel_b, parts)

        # 9. EVERY kind of HOLDOUT overlap is refused.
        h_a, h_b = (date.fromisoformat(x) for x in ranges["holdout"])
        from datetime import timedelta
        for a, b in [(h_a, h_a), (h_b, h_b), (h_a, h_b),
                     (sel_b, h_a), (h_a - timedelta(days=1), h_a),
                     (h_b, h_b + timedelta(days=30)),
                     (dev_a, h_b), (date(2020, 1, 1), date(2030, 1, 1))]:
            with pytest.raises(HoldoutAccessError):
                _check_range(a, b, parts)

        # 10. The holdout OPENING workflow still refuses unconditionally.
        with pytest.raises(HoldoutFenceError, match="not implemented"):
            holdout_opening()

    def test_neutral_proposal_is_untouched_by_activation(self, tmp_path):
        root, droot, _, candidate_sha, _ = self._activate(tmp_path)
        prop = json.loads(
            (droot / "qa" / "m0_closeout" / "partition_proposal.json")
            .read_text(encoding="utf-8"))
        assert prop["artifact"] == "partition_proposal"
        assert prop["state"] == CANDIDATE_STATE_NOT_ACTIVE
        assert prop["activation_ready"] is False
        assert hashlib.sha256(
            (droot / "qa" / "m0_closeout" / "partition_proposal.json")
            .read_bytes()).hexdigest() != candidate_sha

    def test_second_activation_is_refused(self, tmp_path):
        root, droot, _, _, _ = self._activate(tmp_path)
        with pytest.raises(ActivationError, match="already exists"):
            _generate_active_partitions_from(APPROVER, "AL-0056", STAMP,
                                             root, droot)

    def test_tampered_candidate_breaks_the_reloaded_fence(self, tmp_path):
        from nqresearch.holdout import (
            _load_active_partitions_from,
            _verify_activation_evidence,
        )

        root, droot, _, _, _ = self._activate(tmp_path)
        p = droot / "qa" / "m0_closeout" / CANDIDATE_ARTIFACT_FILENAME
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["quarantined_dates"] = doc["quarantined_dates"][:-1]
        p.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        parts = _load_active_partitions_from(root)
        with pytest.raises(PartitionsNotActiveError,
                           match="activation candidate"):
            _verify_activation_evidence(parts, root, droot)


class TestCandidateSubstance:
    """A candidate whose substance disagrees with freshly recomputed
    preconditions can never be activated."""

    def _prepared(self, tmp_path):
        root, droot = fx.full_corpus_tree(tmp_path)
        return root, droot, _finalize_activation_candidate_from(root, droot)

    def test_missing_candidate_refused(self, tmp_path):
        root, droot, _ = self._prepared(tmp_path)
        with pytest.raises(ActivationError, match="candidate missing"):
            _generate_active_partitions_from(APPROVER, "AL-0056", STAMP,
                                             root, droot)

    @pytest.mark.parametrize("mutation", [
        {"quarantined_dates": ["2024-09-02"], "n_quarantined_calendar_dates": 1},
        {"mbo_sessions_per_partition": {"DEV": 1, "SELECTION": 1,
                                        "HOLDOUT": 1}},
        {"activation_requires": ["nothing at all"]},
    ])
    def test_substance_divergence_refused(self, tmp_path, mutation):
        root, droot, payload = self._prepared(tmp_path)
        _write_candidate(droot, {**payload, **mutation})
        with pytest.raises(ActivationError, match="differs from the freshly"):
            _generate_active_partitions_from(APPROVER, "AL-0056", STAMP,
                                             root, droot)

    def test_unknown_field_refused(self, tmp_path):
        root, droot, payload = self._prepared(tmp_path)
        _write_candidate(droot, {**payload, "activation_approved": True})
        with pytest.raises(ActivationError, match="not usable"):
            _generate_active_partitions_from(APPROVER, "AL-0056", STAMP,
                                             root, droot)

    def test_self_certifying_candidate_refused(self, tmp_path):
        root, droot, payload = self._prepared(tmp_path)
        _write_candidate(droot, {**payload, "activation_ready": True})
        with pytest.raises(ActivationError, match="self-certify"):
            _generate_active_partitions_from(APPROVER, "AL-0056", STAMP,
                                             root, droot)

    def test_identity_divergence_refused(self, tmp_path):
        root, droot, payload = self._prepared(tmp_path)
        bound = {**payload["bound_identities"],
                 "coverage_artifact_sha256": "0" * 64}
        _write_candidate(droot, {**payload, "bound_identities": bound})
        with pytest.raises(ActivationError, match="differs from the freshly"):
            _generate_active_partitions_from(APPROVER, "AL-0056", STAMP,
                                             root, droot)

    def test_ninth_invented_identity_refused(self, tmp_path):
        root, droot, payload = self._prepared(tmp_path)
        bound = {**payload["bound_identities"], "invented_sha256": "0" * 64}
        _write_candidate(droot, {**payload, "bound_identities": bound})
        with pytest.raises(ActivationError, match="not usable|differs from"):
            _generate_active_partitions_from(APPROVER, "AL-0056", STAMP,
                                             root, droot)

    def test_approval_naming_the_wrong_candidate_sha_refused(self, tmp_path):
        root, droot, payload = self._prepared(tmp_path)
        _write_candidate(droot, payload)
        ident = {"activation_candidate_sha256": "7" * 64,
                 **payload["bound_identities"]}
        ranges = {name.lower(): (payload["proposal"][name]["start"],
                                 payload["proposal"][name]["end"])
                  for name in ("DEV", "SELECTION", "HOLDOUT")}
        log = root / "docs" / "implementation-audit-log.md"
        log.write_text(log.read_text(encoding="utf-8") + "\n"
                       + _approval_entry("AL-0056", ident, ranges=ranges),
                       encoding="utf-8")
        with pytest.raises(ActivationError,
                           match="activation_candidate_sha256"):
            _generate_active_partitions_from(APPROVER, "AL-0056", STAMP,
                                             root, droot)


class _NotADatetime:
    def strftime(self, _fmt):          # quacks like a datetime, is not one
        return "2026-08-21T09:30:00Z"

    def utcoffset(self):
        return timedelta(0)


class TestApprovalTimestampIsUtc:
    """`approved_at_utc` must be proven to be a UTC instant BEFORE anything
    stamps a literal `Z` on it. Relabelling a +08:00 wall time as UTC would
    make the permanent record lie about when approval happened."""

    VALID = datetime(2026, 8, 21, 9, 30, 0, tzinfo=timezone.utc)

    def test_valid_utc_datetime_accepted(self):
        assert _validated_utc_instant(self.VALID) is self.VALID
        assert self.VALID.strftime(APPROVAL_TIMESTAMP_FORMAT) == STAMP_TEXT
        assert self.VALID.microsecond == 0

    @pytest.mark.parametrize("micro", [1, 2, 500, 999, 1000, 123456, 987654,
                                       999999])
    def test_subsecond_precision_refused(self, micro):
        # The approval format records whole seconds, so a microsecond-bearing
        # instant could only be recorded by DISCARDING precision. Refuse it
        # rather than silently truncate or round.
        value = self.VALID.replace(microsecond=micro)
        with pytest.raises(ActivationError, match="microseconds"):
            _validated_utc_instant(value)

    def test_reproduced_truncation_case_is_refused(self):
        # The exact reviewer-reproduced case: .987654 would have been written
        # as 09:30:00Z, which is not the approved instant.
        value = datetime(2026, 8, 21, 9, 30, 0, 987654, tzinfo=timezone.utc)
        assert value.strftime(APPROVAL_TIMESTAMP_FORMAT) == STAMP_TEXT
        assert value != datetime.strptime(
            STAMP_TEXT, APPROVAL_TIMESTAMP_FORMAT).replace(
                tzinfo=timezone.utc)
        with pytest.raises(ActivationError, match="microseconds"):
            _validated_utc_instant(value)

    @pytest.mark.parametrize("micro", [0, 1, 999999])
    def test_recorded_instant_always_equals_the_validated_input(self, micro):
        # Whatever survives validation must round-trip through the fixed
        # format with NO loss: no accepted value can be recorded differently.
        value = self.VALID.replace(microsecond=micro)
        try:
            validated = _validated_utc_instant(value)
        except ActivationError:
            return          # refused, so nothing can be recorded at all
        recorded = validated.strftime(APPROVAL_TIMESTAMP_FORMAT)
        assert datetime.strptime(
            recorded, APPROVAL_TIMESTAMP_FORMAT).replace(
                tzinfo=timezone.utc) == value

    def test_zero_offset_non_utc_tzinfo_accepted(self):
        # A zero-offset timezone that is not literally `timezone.utc` still
        # denotes the same instant, so it is accepted.
        value = datetime(2026, 8, 21, 9, 30, 0,
                         tzinfo=timezone(timedelta(0), "UTC+00"))
        assert _validated_utc_instant(value) is value

    @pytest.mark.parametrize("value,match", [
        (datetime(2026, 8, 21, 9, 30, 0), "timezone-aware"),          # naive
        (datetime(2026, 8, 21, 9, 30, 0,
                  tzinfo=timezone(timedelta(hours=8))), "offset"),    # +08:00
        (datetime(2026, 8, 21, 9, 30, 0,
                  tzinfo=timezone(timedelta(hours=-5))), "offset"),   # -05:00
        (datetime(2026, 8, 21, 9, 30, 0,
                  tzinfo=timezone(timedelta(minutes=1))), "offset"),
        (date(2026, 8, 21), "must be a datetime"),                    # date
        ("2026-08-21T09:30:00Z", "must be a datetime"),
        ("2026-08-21 09:30:00+00:00", "must be a datetime"),
        (None, "must be a datetime"),
        (0, "must be a datetime"),
        (1755769800, "must be a datetime"),
        (1755769800.0, "must be a datetime"),
        (True, "must be a datetime"),
        (_NotADatetime(), "must be a datetime"),
    ])
    def test_invalid_timestamps_refused(self, value, match):
        with pytest.raises(ActivationError, match=match):
            _validated_utc_instant(value)

    def test_non_utc_is_refused_not_converted(self):
        # Explicitly: the +08:00 value is REFUSED, never silently converted
        # to 01:30Z and never relabelled 09:30Z.
        plus8 = datetime(2026, 8, 21, 9, 30, 0,
                         tzinfo=timezone(timedelta(hours=8)))
        with pytest.raises(ActivationError) as exc:
            _validated_utc_instant(plus8)
        assert "8:00:00" in str(exc.value)
        assert "refusing to relabel" in str(exc.value)

    @pytest.mark.parametrize("bad", [
        datetime(2026, 8, 21, 9, 30, 0),
        datetime(2026, 8, 21, 9, 30, 0, tzinfo=timezone(timedelta(hours=8))),
        datetime(2026, 8, 21, 9, 30, 0, tzinfo=timezone(timedelta(hours=-5))),
        datetime(2026, 8, 21, 9, 30, 0, 987654, tzinfo=timezone.utc),
        date(2026, 8, 21),
        "2026-08-21T09:30:00Z",
        None,
        _NotADatetime(),
    ])
    def test_generator_refuses_before_touching_anything(self, tmp_path, bad):
        # The refusal happens before ANY other work, so it fires even against
        # an empty tree, and no configuration file is ever produced.
        root = tmp_path / "repo"
        (root / "config" / "data").mkdir(parents=True)
        (root / "docs").mkdir()
        with pytest.raises(ActivationError, match="approved_at_utc"):
            _generate_active_partitions_from(APPROVER, "AL-0056", bad,
                                             root, tmp_path / "dataroot")
        assert not (root / "config" / "data"
                    / "partitions_active.yaml").exists()

    def test_public_generator_also_refuses_non_utc(self):
        plus8 = datetime(2026, 8, 21, 9, 30, 0,
                         tzinfo=timezone(timedelta(hours=8)))
        with pytest.raises(ActivationError, match="approved_at_utc"):
            generate_active_partitions(APPROVER, "AL-0056", plus8)

    def test_no_unvalidated_strftime_remains(self):
        import nqresearch.activation as act

        src = inspect.getsource(act)
        assert "approved_at_utc.strftime" not in src
        assert "stamp.strftime(APPROVAL_TIMESTAMP_FORMAT)" in src
