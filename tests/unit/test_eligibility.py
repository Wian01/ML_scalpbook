"""PA-0002 research-eligibility quarantine: schema strictness, fail-closed
masking, window/state rules, structural invariants against the REAL corpus
artifacts, and the truth-preserving activation disposition.

Synthetic fixtures except where a real-corpus invariant is asserted; raw data
is never decoded.
"""

import inspect
import re
from datetime import date, datetime, timedelta, timezone

import pytest
import yaml

import conftest as fx
from nqresearch.calendar_evidence import (
    CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED,
    DISPOSITION_EVIDENCE_COMPLETE,
    DISPOSITION_PENDING_DATES_QUARANTINED,
    EVIDENCE_STATES,
    STATE_CONFLICT,
    STATE_PENDING,
    CalendarEvidenceError,
    EvidenceMatrix,
    resolve_activation_disposition,
)
from nqresearch.eligibility import (
    CANONICAL_ALLOWED_REASON_CODES,
    NON_ACTIVATION_POLICY_STATES,
    POLICY_STATE_APPROVED,
    EligibilityPolicy,
    EligibilityPolicyError,
    IneligibleSessionError,
    InvalidSessionIdError,
    assert_session_eligible,
    parse_session_id,
    assert_window_session_local,
    eligible_sessions_in_range,
    is_research_eligible,
    load_policy,
    next_eligible_session,
    policy_sha256,
    quarantined_sessions,
    requires_state_reset,
    verify_policy_bound_to_evidence,
    verify_structural_quarantine_invariants,
)

REAL_TEN = [
    "2024-09-02", "2024-11-29", "2025-01-01", "2025-01-20", "2025-02-17",
    "2025-04-18", "2025-05-26", "2025-06-19", "2025-07-03", "2025-07-04",
]


def _policy(**kw):
    return fx.eligibility_policy_doc("a" * 64, REAL_TEN, **kw)


class TestPolicySchema:
    def test_exact_real_ten_date_policy_accepted(self):
        p = EligibilityPolicy(**_policy())
        assert sorted(p.dates) == REAL_TEN
        assert len(p.quarantined_sessions) == 10

    def test_duplicate_date_rejected(self):
        doc = _policy()
        doc["quarantined_sessions"].append(
            dict(doc["quarantined_sessions"][0]))
        with pytest.raises(Exception, match="duplicate"):
            EligibilityPolicy(**doc)

    def test_incorrectly_reordered_dates_rejected(self):
        doc = _policy()
        doc["quarantined_sessions"].reverse()
        with pytest.raises(Exception, match="ascending"):
            EligibilityPolicy(**doc)

    def test_extra_yaml_field_rejected(self):
        for where in ("meta", "semantics"):
            doc = _policy()
            doc[where]["sneaky"] = True
            with pytest.raises(Exception, match="[Ee]xtra"):
                EligibilityPolicy(**doc)
        doc = _policy()
        doc["quarantined_sessions"][0]["sneaky"] = True
        with pytest.raises(Exception, match="[Ee]xtra"):
            EligibilityPolicy(**doc)
        doc = _policy()
        doc["unexpected_top_level"] = 1
        with pytest.raises(Exception, match="[Ee]xtra"):
            EligibilityPolicy(**doc)

    def test_unknown_reason_code_rejected(self):
        doc = _policy()
        doc["quarantined_sessions"][0]["reason_code"] = "BAD_PNL_DAY"
        with pytest.raises(Exception,
                           match="PREDEFINED_HOLIDAY_PARTIAL_SESSION_RULE"):
            EligibilityPolicy(**doc)

    def test_reason_codes_are_exactly_canonical_section_50(self):
        assert CANONICAL_ALLOWED_REASON_CODES == {
            "VENDOR_CORRUPT_SESSION", "UNRECOVERABLE_DATA_GAP",
            "INVALID_BOOK_RECONSTRUCTION", "SESSION_MISSING_REQUIRED_COVERAGE",
            "FEATURE_WINDOW_CROSSING_CONTRACT_BOUNDARY",
            "TARGET_HORIZON_CROSSING_CONTRACT_BOUNDARY",
            "PREDEFINED_HOLIDAY_PARTIAL_SESSION_RULE",
        }

    def test_research_eligible_true_rejected(self):
        doc = _policy()
        doc["quarantined_sessions"][0]["research_eligible"] = True
        with pytest.raises(Exception, match="research_eligible=false"):
            EligibilityPolicy(**doc)

    def test_bad_evidence_matrix_hash_rejected(self):
        for bad in ("nothex", "", "a" * 63, "z" * 64, None, 12345):
            doc = _policy()
            doc["meta"]["evidence_matrix_sha256"] = bad
            with pytest.raises(Exception):
                EligibilityPolicy(**doc)

    def test_uppercase_hash_is_normalised_not_rejected(self):
        doc = _policy()
        doc["meta"]["evidence_matrix_sha256"] = "A" * 64
        assert EligibilityPolicy(**doc).meta.evidence_matrix_sha256 == "a" * 64

    @pytest.mark.parametrize("override", [
        {"research_use": "ALLOWED"},
        {"feature_window_crossing": "ALLOWED"},
        {"label_horizon_crossing": "ALLOWED"},
        {"evaluation_window_crossing": "ALLOWED"},
        {"rolling_state_reset_required_at_next_eligible_session": False},
        {"causal_roll_series_consumes_eligibility": True},
        {"raw_data_unchanged": False},
        {"partition_contiguity_unchanged": False},
        {"coverage_counts_unchanged": False},
        {"calendar_membership_unchanged": False},
        {"holdout_sealed": False},
        {"n_mbo_blocks_quarantined": 1},
    ])
    def test_non_negotiable_semantics_enforced(self, override):
        with pytest.raises(Exception):
            EligibilityPolicy(**_policy(**override))

    def test_missing_policy_file_fails_closed(self, tmp_path):
        with pytest.raises(EligibilityPolicyError, match="missing"):
            load_policy(tmp_path)
        with pytest.raises(EligibilityPolicyError, match="missing"):
            policy_sha256(tmp_path)

    def test_malformed_policy_fails_closed(self, tmp_path):
        p = tmp_path / "config" / "data" / "research_eligibility.yaml"
        p.parent.mkdir(parents=True)
        p.write_text("meta: [not, a, mapping")
        with pytest.raises(EligibilityPolicyError, match="malformed"):
            load_policy(tmp_path)


class TestRealPolicy:
    def test_real_policy_is_exactly_the_ten_dates(self):
        assert sorted(quarantined_sessions()) == REAL_TEN

    def test_real_policy_binds_the_committed_evidence_matrix(self):
        verify_policy_bound_to_evidence()  # must not raise

    def test_wrong_matrix_binding_fails(self, tmp_path):
        import shutil

        from nqresearch.config import _repo_root

        root = tmp_path / "repo"
        (root / "config" / "data").mkdir(parents=True)
        for f in ("cme_calendar_evidence.yaml", "research_eligibility.yaml"):
            shutil.copy(_repo_root() / "config" / "data" / f,
                        root / "config" / "data" / f)
        pol = root / "config" / "data" / "research_eligibility.yaml"
        doc = yaml.safe_load(pol.read_text(encoding="utf-8"))
        doc["meta"]["evidence_matrix_sha256"] = "c" * 64
        pol.write_text(yaml.safe_dump(doc, sort_keys=False))
        with pytest.raises(EligibilityPolicyError, match="binds evidence"):
            verify_policy_bound_to_evidence(root)

    def test_every_real_reason_code_is_the_holiday_rule(self):
        for s in load_policy().quarantined_sessions:
            assert s.reason_code == "PREDEFINED_HOLIDAY_PARTIAL_SESSION_RULE"
            assert s.evidence_state_at_policy_time == STATE_PENDING


class TestMasking:
    def test_quarantined_sessions_are_ineligible(self):
        for d in REAL_TEN:
            assert not is_research_eligible(d)
            with pytest.raises(IneligibleSessionError, match="INELIGIBLE"):
                assert_session_eligible(d)
        assert not is_research_eligible(date(2025, 7, 4))

    def test_ordinary_sessions_remain_eligible(self):
        for d in ["2024-10-01", "2025-03-03", "2025-07-07", "2025-09-01"]:
            assert is_research_eligible(d)
            assert_session_eligible(d)

    def test_broad_dev_range_yields_309_eligible_observed_sessions(self):
        out = eligible_sessions_in_range(date(2024, 8, 19), date(2025, 11, 7))
        assert len(out) == 309
        assert not (set(out) & set(REAL_TEN))

    def test_range_of_only_quarantined_sessions_refused(self):
        with pytest.raises(IneligibleSessionError, match="no research-eligible"):
            eligible_sessions_in_range(date(2025, 7, 3), date(2025, 7, 4))

    def test_malformed_range_refused(self):
        with pytest.raises(IneligibleSessionError, match="malformed"):
            eligible_sessions_in_range(date(2025, 7, 4), date(2025, 7, 3))

    def test_no_override_or_allow_quarantined_parameter_exists(self):
        for fn in (assert_session_eligible, is_research_eligible,
                   eligible_sessions_in_range, assert_window_session_local):
            params = set(inspect.signature(fn).parameters)
            assert not any(
                k in p for p in params
                for k in ("override", "allow", "force", "quarantin", "bypass")
            ), (fn, params)

    def test_public_apis_return_only_session_ids_and_booleans(self):
        # Executable proof: no Path objects, no raw-file locations.
        from pathlib import Path as _P

        out = eligible_sessions_in_range(date(2024, 10, 1), date(2024, 10, 31))
        assert out and all(isinstance(s, str) for s in out)
        assert all(not isinstance(s, _P) for s in out)
        assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) for s in out)
        assert isinstance(is_research_eligible("2024-10-01"), bool)
        assert isinstance(requires_state_reset("2024-10-02"), bool)
        nxt = next_eligible_session("2025-07-04")
        assert isinstance(nxt, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", nxt)

    def test_no_path_returning_or_raw_enumeration_api_exists(self):
        import nqresearch.eligibility as el

        banned = ("path_for", "file_for", "files", "paths", "raw_", "_raw",
                  "dbn", "enumerate_files")
        public = [n for n in dir(el) if not n.startswith("_")]
        for name in public:
            low = name.lower()
            assert not any(b in low for b in banned), name
        # policy_path is intentionally private-by-convention config access,
        # not a research-data path: it must point at config, never at data.
        assert el.policy_path().name == "research_eligibility.yaml"
        assert el.policy_path().parent.name == "data"
        assert el.policy_path().parent.parent.name == "config"

    def test_no_public_api_returns_a_path_object(self):
        from pathlib import Path as _P

        for value in (eligible_sessions_in_range(date(2024, 10, 1),
                                                 date(2024, 10, 31)),
                      quarantined_sessions(),
                      next_eligible_session("2025-07-04")):
            items = value if isinstance(value, (list, frozenset, set)) \
                else [value]
            assert all(not isinstance(v, _P) for v in items)


class TestWindowAndStateRules:
    def test_window_touching_quarantined_session_refused(self):
        with pytest.raises(IneligibleSessionError, match="INELIGIBLE"):
            assert_window_session_local(["2025-07-03"])

    def test_window_spanning_two_sessions_refused(self):
        with pytest.raises(IneligibleSessionError, match="spans multiple"):
            assert_window_session_local(["2025-07-02", "2025-07-07"])
        # even when both are eligible: no window may cross a session boundary
        with pytest.raises(IneligibleSessionError, match="spans multiple"):
            assert_window_session_local(["2024-10-01", "2024-10-02"])

    def test_session_local_eligible_window_accepted(self):
        assert_window_session_local(["2024-10-01", "2024-10-01"])

    def test_empty_window_refused(self):
        with pytest.raises(IneligibleSessionError, match="no session"):
            assert_window_session_local([])

    def test_reset_after_quarantined_dates_with_no_observed_session(self):
        # REPRODUCED REVIEW DEFECT: 2025-01-01 (holiday, no session) and
        # 2025-04-18 (Good Friday, no usable data) are quarantined CALENDAR
        # dates with no observed session. State must still reset at the next
        # eligible session, which previously returned False.
        assert next_eligible_session("2025-01-01") == "2025-01-02"
        assert requires_state_reset("2025-01-02") is True
        assert next_eligible_session("2025-04-18") == "2025-04-21"
        assert requires_state_reset("2025-04-21") is True

    def test_first_observed_corpus_session_resets(self):
        assert requires_state_reset("2024-08-19") is True

    def test_next_eligible_and_reset_are_mutually_coherent(self):
        # For every quarantined date, the next eligible session must require
        # a reset — the two functions can never disagree.
        for q in REAL_TEN:
            nxt = next_eligible_session(q)
            assert nxt is not None, q
            assert requires_state_reset(nxt) is True, (q, nxt)

    def test_consecutive_july_dates_and_successor_reset(self):
        # 2025-07-03 and 2025-07-04 are consecutive quarantined sessions;
        # the next eligible session is 2025-07-07, which must reset state.
        assert next_eligible_session("2025-07-03") == "2025-07-07"
        assert next_eligible_session("2025-07-02") == "2025-07-07"
        assert requires_state_reset("2025-07-07") is True

    def test_successor_of_each_quarantined_session_requires_reset(self):
        for d in ["2024-09-03", "2024-12-02", "2025-01-21", "2025-02-18",
                  "2025-05-27", "2025-06-20", "2025-07-07"]:
            assert requires_state_reset(d) is True, d

    def test_ordinary_session_does_not_require_reset(self):
        assert requires_state_reset("2024-10-02") is False

    def test_reset_query_for_unknown_session_fails_closed(self):
        with pytest.raises(EligibilityPolicyError, match="not an observed"):
            requires_state_reset("2025-01-01")  # holiday: no session exists


BAD_SESSION_IDS = [
    "not-a-date", " 2025-07-04", "2025-07-04 ", "2025-07-04T00:00:00",
    "2025-7-4", "20250704", "2025-13-01", "2025-02-30", "", "None",
    12345, 0, None, 3.5, True, False, ["2025-07-04"], {"d": "2025-07-04"},
    object(), datetime(2025, 7, 4), datetime(2025, 7, 4, 12, 30),
]


class TestSessionIdValidation:
    """REPRODUCED REVIEW DEFECT: is_research_eligible('not-a-date') was True.
    Every public entry point must refuse non-canonical identifiers rather
    than treating them as ordinary eligible sessions."""

    @pytest.mark.parametrize("bad", BAD_SESSION_IDS)
    def test_is_research_eligible_rejects(self, bad):
        with pytest.raises(InvalidSessionIdError):
            is_research_eligible(bad)

    @pytest.mark.parametrize("bad", BAD_SESSION_IDS)
    def test_assert_session_eligible_rejects(self, bad):
        with pytest.raises(InvalidSessionIdError):
            assert_session_eligible(bad)

    @pytest.mark.parametrize("bad", BAD_SESSION_IDS)
    def test_window_check_rejects(self, bad):
        with pytest.raises(InvalidSessionIdError):
            assert_window_session_local([bad])

    @pytest.mark.parametrize("bad", BAD_SESSION_IDS)
    def test_reset_and_next_reject(self, bad):
        with pytest.raises(InvalidSessionIdError):
            requires_state_reset(bad)
        with pytest.raises(InvalidSessionIdError):
            next_eligible_session(bad)

    @pytest.mark.parametrize("bad", BAD_SESSION_IDS)
    def test_range_endpoints_rejected(self, bad):
        with pytest.raises(InvalidSessionIdError):
            eligible_sessions_in_range(bad, date(2025, 1, 10))
        with pytest.raises(InvalidSessionIdError):
            eligible_sessions_in_range(date(2025, 1, 10), bad)

    def test_datetime_is_refused_even_though_it_subclasses_date(self):
        with pytest.raises(InvalidSessionIdError, match="datetime"):
            parse_session_id(datetime(2025, 7, 4))

    def test_canonical_forms_accepted(self):
        assert parse_session_id("2025-07-04") == "2025-07-04"
        assert parse_session_id(date(2025, 7, 4)) == "2025-07-04"

    def test_window_rejects_unknown_but_canonical_session(self):
        with pytest.raises(IneligibleSessionError, match="unknown session"):
            assert_window_session_local(["2099-01-06"])


class TestPolicyLifecycle:
    """CHANGED REQUIREMENT (2026-08-20, AL-0060): the project owner explicitly
    APPROVED the PA-0002 quarantine policy after independent review, so the
    live lifecycle state moved
    IMPLEMENTED_PENDING_ACTIVATION_APPROVAL -> APPROVED_FOR_ACTIVATION.
    These tests are retargeted at the new required state, NOT relaxed: the
    approved state is pinned EXACTLY, every other state is still refused, and
    TestApprovedPolicyInvariants below asserts that the approval changed
    nothing substantive."""

    def test_live_policy_is_exactly_activation_approved(self):
        assert load_policy().meta.status == POLICY_STATE_APPROVED
        assert load_policy().meta.status not in NON_ACTIVATION_POLICY_STATES

    def test_activation_and_research_entry_points_now_accept_the_policy(self):
        from nqresearch.eligibility import (
            load_policy_for_activation,
            load_policy_for_research,
        )

        policy, disposition = load_policy_for_activation()
        assert policy.meta.status == POLICY_STATE_APPROVED
        assert disposition == DISPOSITION_PENDING_DATES_QUARANTINED
        rpolicy, rdisposition = load_policy_for_research()
        assert rpolicy.meta.status == POLICY_STATE_APPROVED
        assert rdisposition == DISPOSITION_PENDING_DATES_QUARANTINED

    def test_only_the_approved_state_parses_for_activation(self, tmp_path):
        # Every non-approved lifecycle state must STILL be refused, so the
        # transition cannot be read as "any state now works".
        from nqresearch.eligibility import (
            _load_validated_policy,
            load_policy,
        )

        real = load_policy()
        others = sorted(NON_ACTIVATION_POLICY_STATES) + [
            "APPROVED", "SYNTHETIC", "approved_for_activation", ""]
        for i, state in enumerate(others):
            root = _synth_repo_with_status(tmp_path / f"s{i}", real, state)
            with pytest.raises(Exception):
                _load_validated_policy(
                    root, allowed_states=(POLICY_STATE_APPROVED,))
        # ...and the REAL approved policy still validates for activation.
        assert _load_validated_policy(
            allowed_states=(POLICY_STATE_APPROVED,))[0].meta.status             == POLICY_STATE_APPROVED

    def test_reporting_entry_point_accepts_current_state(self):
        from nqresearch.eligibility import load_policy_for_reporting

        policy, disposition = load_policy_for_reporting()
        assert policy.meta.status == POLICY_STATE_APPROVED
        assert disposition == DISPOSITION_PENDING_DATES_QUARANTINED

    def test_no_public_entry_point_exposes_allowed_states_or_override(self):
        import nqresearch.eligibility as el
        import nqresearch.research as rs

        public = [
            el.load_policy_for_reporting, el.load_policy_for_activation,
            el.load_policy_for_research, el.quarantined_sessions,
            el.is_research_eligible, el.assert_session_eligible,
            el.assert_window_session_local, el.next_eligible_session,
            el.requires_state_reset, el.eligible_sessions_in_range,
            rs.research_eligible_sessions, rs.research_session_records,
        ]
        for fn in public:
            params = set(inspect.signature(fn).parameters)
            assert not any(
                k in p for p in params
                for k in ("allowed_state", "allowed_states", "override",
                          "force", "bypass", "quarantin")
            ), (fn.__name__, params)
        # the injectable core stays private and test-only
        assert hasattr(el, "_load_validated_policy")
        assert not hasattr(el, "load_validated_policy")

    @pytest.mark.parametrize("field,value", [
        ("policy_id", "some-other-policy"),
        ("amendment", "docs/protocol-amendments/PA-0003-other.md"),
        ("status", "SYNTHETIC"),
        ("status", "APPROVED"),
        ("policy_version", 999),
        ("policy_version", True),
        ("policy_version", "1"),
        ("canonical_basis", "  "),
        ("rationale", ""),
    ])
    def test_arbitrary_meta_values_rejected(self, field, value):
        doc = _policy()
        doc["meta"][field] = value
        with pytest.raises(Exception):
            EligibilityPolicy(**doc)

    @pytest.mark.parametrize("value", [
        "VENDOR_CORRUPT_SESSION", "UNRECOVERABLE_DATA_GAP",
        "SESSION_MISSING_REQUIRED_COVERAGE",
    ])
    def test_other_canonical_reason_codes_rejected_for_pa0002(self, value):
        doc = _policy()
        doc["quarantined_sessions"][0]["reason_code"] = value
        with pytest.raises(Exception):
            EligibilityPolicy(**doc)

    @pytest.mark.parametrize("value", [
        "DOCUMENT_VERIFIED", "TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE",
        "CONFLICT_REQUIRES_REVIEW",
    ])
    def test_wrong_evidence_state_rejected(self, value):
        doc = _policy()
        doc["quarantined_sessions"][0]["evidence_state_at_policy_time"] = value
        with pytest.raises(Exception):
            EligibilityPolicy(**doc)

    @pytest.mark.parametrize("coercive", [0, "false", "False", None, "", []])
    def test_coercive_false_research_eligible_rejected(self, coercive):
        doc = _policy()
        doc["quarantined_sessions"][0]["research_eligible"] = coercive
        with pytest.raises(Exception, match="strict boolean|research_eligible"):
            EligibilityPolicy(**doc)

    def test_blank_note_rejected(self):
        doc = _policy()
        doc["quarantined_sessions"][0]["note"] = "   "
        with pytest.raises(Exception, match="non-blank"):
            EligibilityPolicy(**doc)

    @pytest.mark.parametrize("override", [
        {"qa_and_normalization_use": "ANYTHING"},
        {"prior_session_state_features_require_policy_review": False},
    ])
    def test_arbitrary_semantics_rejected(self, override):
        with pytest.raises(Exception):
            EligibilityPolicy(**_policy(**override))

    def test_malformed_session_date_in_policy_rejected(self):
        doc = _policy()
        doc["quarantined_sessions"][0]["date"] = "2025-7-4"
        with pytest.raises(Exception):
            EligibilityPolicy(**doc)


COERCIVE = [0, 1, "true", "false", "True", "False", "0", "1", None, [], {},
            1.0, 0.0]
STRICT_BOOL_FIELDS = [
    "rolling_state_reset_required_at_next_eligible_session",
    "prior_session_state_features_require_policy_review",
    "calendar_membership_unchanged", "partition_contiguity_unchanged",
    "coverage_counts_unchanged", "causal_roll_series_consumes_eligibility",
    "raw_data_unchanged", "holdout_sealed",
]


class TestStrictTypesBeforeCoercion:
    """REPRODUCED REVIEW DEFECT: the after-model validator saw values Pydantic
    had already coerced, so `= 1`, `= "true"`, `= 0`, `= "0"` were accepted."""

    @pytest.mark.parametrize("field", STRICT_BOOL_FIELDS)
    @pytest.mark.parametrize("value", COERCIVE)
    def test_semantic_booleans_reject_coercive_values(self, field, value):
        with pytest.raises(Exception):
            EligibilityPolicy(**_policy(**{field: value}))

    # 0 is the LEGITIMATE value for the block count, so it is excluded here.
    @pytest.mark.parametrize("value",
                             [v for v in COERCIVE if v != 0] + ["0", 1, -1])
    def test_mbo_block_count_rejects_coercive_values(self, value):
        with pytest.raises(Exception):
            EligibilityPolicy(**_policy(n_mbo_blocks_quarantined=value))

    # 1 is the LEGITIMATE policy version, so it is excluded here.
    @pytest.mark.parametrize("value",
                             [v for v in COERCIVE if v != 1] + ["1", 2, 999])
    def test_policy_version_rejects_coercive_values(self, value):
        doc = _policy()
        doc["meta"]["policy_version"] = value
        with pytest.raises(Exception):
            EligibilityPolicy(**doc)

    @pytest.mark.parametrize("value", COERCIVE)
    def test_research_eligible_rejects_coercive_values(self, value):
        doc = _policy()
        doc["quarantined_sessions"][0]["research_eligible"] = value
        with pytest.raises(Exception):
            EligibilityPolicy(**doc)

    def test_correct_strict_values_still_accepted(self):
        p = EligibilityPolicy(**_policy())
        assert p.semantics.holdout_sealed is True
        assert p.semantics.causal_roll_series_consumes_eligibility is False
        assert p.semantics.n_mbo_blocks_quarantined == 0
        assert p.meta.policy_version == 1
        assert p.quarantined_sessions[0].research_eligible is False


class TestValidatedPolicyPath:
    def test_stale_matrix_binding_blocks_quarantine_state(self, tmp_path):
        # current_calendar_verification_state must fall back to the ordinary
        # provisional/pending state when the binding is stale.
        import shutil

        from nqresearch import paths
        from nqresearch.calendar_evidence import (
            CALENDAR_EVIDENCE_PENDING_STATE,
            current_calendar_verification_state,
        )
        from nqresearch.config import _repo_root

        root = tmp_path / "repo"
        (root / "config" / "data").mkdir(parents=True)
        for f in ("cme_calendar.yaml", "cme_calendar_overrides.yaml",
                  "cme_calendar_evidence.yaml", "research_eligibility.yaml"):
            shutil.copy(_repo_root() / "config" / "data" / f,
                        root / "config" / "data" / f)
        pol = root / "config" / "data" / "research_eligibility.yaml"
        doc = yaml.safe_load(pol.read_text(encoding="utf-8"))
        doc["meta"]["evidence_matrix_sha256"] = "c" * 64  # stale binding
        pol.write_text(yaml.safe_dump(doc, sort_keys=False))
        assert current_calendar_verification_state(
            root, paths.data_root()) == CALENDAR_EVIDENCE_PENDING_STATE

    def test_validated_path_rejects_missing_policy(self, tmp_path):
        from nqresearch.eligibility import load_policy_for_reporting

        with pytest.raises(EligibilityPolicyError):
            load_policy_for_reporting(tmp_path, tmp_path)

    def test_stale_binding_fails_every_public_eligibility_decision(self,
                                                                   tmp_path):
        # A stale policy/matrix binding must make every public decision fail
        # closed rather than return an eligibility answer.
        import shutil

        from nqresearch import paths
        from nqresearch.config import _repo_root
        from nqresearch.eligibility import (
            assert_session_eligible,
            assert_window_session_local,
            eligible_sessions_in_range,
            is_research_eligible,
            next_eligible_session,
            quarantined_sessions,
            requires_state_reset,
        )

        root = tmp_path / "repo"
        (root / "config" / "data").mkdir(parents=True)
        for f in ("cme_calendar.yaml", "cme_calendar_overrides.yaml",
                  "cme_calendar_evidence.yaml", "research_eligibility.yaml"):
            shutil.copy(_repo_root() / "config" / "data" / f,
                        root / "config" / "data" / f)
        pol = root / "config" / "data" / "research_eligibility.yaml"
        doc = yaml.safe_load(pol.read_text(encoding="utf-8"))
        doc["meta"]["evidence_matrix_sha256"] = "c" * 64  # stale
        pol.write_text(yaml.safe_dump(doc, sort_keys=False))
        d = paths.data_root()
        with pytest.raises(EligibilityPolicyError):
            quarantined_sessions(root, d)
        with pytest.raises(EligibilityPolicyError):
            is_research_eligible("2024-10-01", root, d)
        with pytest.raises(EligibilityPolicyError):
            assert_session_eligible("2024-10-01", root, d)
        with pytest.raises(EligibilityPolicyError):
            assert_window_session_local(["2024-10-01"], root, d)
        with pytest.raises(EligibilityPolicyError):
            next_eligible_session("2024-10-01", root, d)
        with pytest.raises(EligibilityPolicyError):
            requires_state_reset("2024-10-02", root, d)
        with pytest.raises(EligibilityPolicyError):
            eligible_sessions_in_range(date(2024, 10, 1), date(2024, 10, 31),
                                       root, d)


class TestStructuralInvariants:
    def test_real_structural_quarantine_invariants_hold(self):
        facts = verify_structural_quarantine_invariants()
        assert facts["n_quarantined"] == 10
        assert facts["all_in_dev"]
        assert facts["none_in_selection_or_holdout"]
        assert facts["none_is_partition_boundary"]
        assert facts["none_is_mbo_session"]
        assert facts["none_inside_mbo_block_span"]
        assert facts["none_is_roll_decision_source"]
        assert facts["n_mbo_sessions"] == 77
        assert facts["n_mbo_blocks"] == 30
        assert facts["n_roll_switches"] == 8

    def _repo_with_dates(self, tmp_path, dates):
        import shutil

        from nqresearch.config import _repo_root

        root = tmp_path / "repo"
        (root / "config" / "data").mkdir(parents=True)
        shutil.copy(_repo_root() / "config" / "data" / "cme_calendar_evidence.yaml",
                    root / "config" / "data" / "cme_calendar_evidence.yaml")
        fx.write_eligibility_policy(root, "a" * 64, dates)
        return root

    @pytest.mark.parametrize("bad,why", [
        ("2025-11-10", "not inside DEV"),      # SELECTION
        ("2026-04-01", "not inside DEV"),      # HOLDOUT start
        ("2024-08-19", "partition boundary"),  # DEV start boundary
        ("2025-11-07", "partition boundary"),  # DEV end boundary
        ("2025-08-18", "MBO session"),         # real MBO session
        ("2025-08-20", "MBO block"),           # inside MBO-BLK-001 span
        ("2024-09-16", "roll decision"),       # decided_from_session
    ])
    def test_structurally_unsafe_quarantine_date_rejected(self, tmp_path, bad,
                                                          why):
        root = self._repo_with_dates(tmp_path, [bad])
        with pytest.raises(EligibilityPolicyError):
            verify_structural_quarantine_invariants(root)

    def test_missing_closeout_artifact_fails_closed(self, tmp_path):
        root = self._repo_with_dates(tmp_path, REAL_TEN)
        with pytest.raises(EligibilityPolicyError, match="artifact missing"):
            verify_structural_quarantine_invariants(root, tmp_path / "empty")


class TestActivationDisposition:
    def _matrix(self, tmp_path, states=None):
        doc, _, _ = (lambda d: (d[0], d[1], d[2]))(
            (*fx.synthetic_matrix_doc(
                tmp_path / "reference" / "cme_calendar",
                date_states=states or {}), None)
        )
        fx.write_coverage_for(tmp_path, doc)
        return EvidenceMatrix(**doc)

    def test_no_quarantine_state_added_to_evidence_states(self):
        # Truth preservation: quarantine is NOT an evidence state.
        assert EVIDENCE_STATES == {
            "DOCUMENT_VERIFIED", "TRIANGULATED_OFFICIAL_ARCHIVE_UNAVAILABLE",
            "PENDING_EVIDENCE", "CONFLICT_REQUIRES_REVIEW",
        }
        assert "QUARANTIN" not in "".join(EVIDENCE_STATES).upper()

    def test_complete_matrix_with_empty_policy_is_evidence_complete(self,
                                                                    tmp_path):
        m = self._matrix(tmp_path)
        assert resolve_activation_disposition(
            m, frozenset()) == DISPOSITION_EVIDENCE_COMPLETE

    def test_pending_fully_quarantined_yields_named_disposition(self,
                                                               tmp_path):
        m = self._matrix(tmp_path, {"2025-06-19": STATE_PENDING})
        assert resolve_activation_disposition(
            m, {"2025-06-19"}) == DISPOSITION_PENDING_DATES_QUARANTINED

    def test_missing_extra_or_substituted_quarantine_date_fails(self,
                                                                tmp_path):
        m = self._matrix(tmp_path, {"2025-06-19": STATE_PENDING,
                                    "2025-07-03": STATE_PENDING})
        for q in [{"2025-06-19"},                       # missing one
                  {"2025-06-19", "2025-07-03", "2026-01-19"},  # extra
                  {"2025-06-19", "2025-07-04"}]:        # substituted
            with pytest.raises(CalendarEvidenceError,
                               match="does not exactly cover"):
                resolve_activation_disposition(m, q)

    def test_verified_date_never_silently_quarantined(self, tmp_path):
        m = self._matrix(tmp_path)  # nothing pending
        with pytest.raises(CalendarEvidenceError,
                           match="never silently quarantined"):
            resolve_activation_disposition(m, {"2026-01-19"})

    def test_conflict_always_blocks_and_is_never_quarantinable(self, tmp_path):
        doc, _ = fx.synthetic_matrix_doc(tmp_path / "reference" / "cme_calendar")
        for d in doc["dates"]:
            if d["date"] == "2025-06-19":
                d["state"] = STATE_CONFLICT
                d["agreement"] = "DISCREPANCY"
        fx.write_coverage_for(tmp_path, doc)
        m = EvidenceMatrix(**doc)
        for q in (frozenset(), {"2025-06-19"}):
            with pytest.raises(CalendarEvidenceError,
                               match="NEVER be resolved by quarantine"):
                resolve_activation_disposition(m, q)

    def test_calendar_is_never_relabelled_document_verified(self):
        from nqresearch import paths
        from nqresearch.calendar_evidence import (
            current_calendar_verification_state,
        )
        from nqresearch.config import _repo_root

        state = current_calendar_verification_state(_repo_root(),
                                                    paths.data_root())
        assert state == CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED
        assert "PROVISIONAL" in state
        assert state != "DOCUMENT_VERIFIED"


class TestSeparationFromRolls:
    def test_rolls_module_never_consumes_eligibility(self):
        import nqresearch.rolls as rolls

        src = inspect.getsource(rolls)
        assert "eligibility" not in src
        assert "quarantin" not in src.lower()

    def test_policy_declares_roll_independence(self):
        assert load_policy().semantics.causal_roll_series_consumes_eligibility \
            is False


class TestHoldoutStillFailsClosed:
    def test_no_active_partitions_and_fence_refuses(self):
        from nqresearch.config import _repo_root
        from nqresearch.holdout import (
            PartitionsNotActiveError,
            load_active_partitions,
        )

        assert not (_repo_root() / "config" / "data"
                    / "partitions_active.yaml").is_file()
        with pytest.raises(PartitionsNotActiveError):
            load_active_partitions()

    def test_research_api_still_refuses_and_exposes_no_paths(self):
        from nqresearch.holdout import PartitionsNotActiveError
        from nqresearch.research import research_eligible_sessions

        with pytest.raises(PartitionsNotActiveError):
            research_eligible_sessions(date(2024, 10, 1), date(2024, 10, 31))


def _synth_repo_with_status(root, real_policy, status):
    """A synthetic copy of the REAL policy with only its lifecycle status
    replaced, so state handling is tested without touching the live file."""
    import shutil

    import yaml as _yaml

    from nqresearch.config import _repo_root

    (root / "config" / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy(_repo_root() / "config" / "data" / "cme_calendar_evidence.yaml",
                root / "config" / "data" / "cme_calendar_evidence.yaml")
    src = _repo_root() / "config" / "data" / "research_eligibility.yaml"
    doc = _yaml.safe_load(src.read_text(encoding="utf-8"))
    doc["meta"]["status"] = status
    (root / "config" / "data" / "research_eligibility.yaml").write_text(
        _yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return root


class TestApprovedPolicyInvariants:
    """AL-0060: approving the POLICY must change the lifecycle state and
    NOTHING else. Every fact the approval statement asserts is pinned here."""

    def test_status_is_exactly_the_approved_constant(self):
        assert load_policy().meta.status == POLICY_STATE_APPROVED
        assert POLICY_STATE_APPROVED == "APPROVED_FOR_ACTIVATION"

    def test_exact_ten_date_set_unchanged(self):
        assert sorted(quarantined_sessions()) == REAL_TEN
        assert len(REAL_TEN) == 10

    def test_all_ten_evidence_states_remain_pending(self):
        # Quarantine is a disposition, NEVER a verification claim.
        from nqresearch.calendar_evidence import load_matrix, pending_dates
        from nqresearch.config import _repo_root

        for s in load_policy().quarantined_sessions:
            assert s.evidence_state_at_policy_time == STATE_PENDING
            assert s.research_eligible is False
        pending = pending_dates(load_matrix(_repo_root()))
        assert sorted(pending) == REAL_TEN
        assert set(pending.values()) == {STATE_PENDING}

    def test_counts_remain_ten_eight_three_hundred_and_nine(self):
        facts = verify_structural_quarantine_invariants()
        assert facts["n_quarantined"] == 10
        assert facts["n_excluded_observed_dev_sessions"] == 8
        assert facts["n_eligible_dev_sessions"] == 309
        assert facts["n_observed_dev_sessions"] == 317
        assert facts["n_coverage_expected_sessions"] == 516
        assert facts["n_mbo_sessions"] == 77
        assert facts["n_mbo_blocks"] == 30
        assert facts["n_spanning_mbo_blocks"] == 0
        assert facts["n_roll_switches"] == 8

    def test_calendar_state_remains_provisional_quarantined(self):
        from nqresearch import paths
        from nqresearch.calendar_evidence import (
            CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED,
            current_calendar_verification_state,
        )
        from nqresearch.config import _repo_root

        assert (current_calendar_verification_state(_repo_root(),
                                                    paths.data_root())
                == CALENDAR_EVIDENCE_PROVISIONAL_QUARANTINED)

    def test_reason_codes_and_semantics_unchanged(self):
        p = load_policy()
        for s in p.quarantined_sessions:
            assert s.reason_code == "PREDEFINED_HOLIDAY_PARTIAL_SESSION_RULE"
        assert p.semantics.research_use == "FORBIDDEN"
        assert p.semantics.n_mbo_blocks_quarantined == 0
        assert p.semantics.holdout_sealed is True
        assert p.semantics.raw_data_unchanged is True

    def test_policy_still_binds_the_committed_evidence_matrix(self):
        verify_policy_bound_to_evidence()  # must not raise


class TestPolicyApprovalIsNotCandidateApproval:
    """The single most dangerous misreading of AL-0060: policy approval is not
    activation. Nothing below may become possible merely because the lifecycle
    state changed."""

    def test_activation_still_refuses_after_policy_approval(self):
        """Approving the policy clears ONE gate and no others.

        It also makes the artifact staleness visible: approving PA-0002
        changed the effective config hash, so the twelve artifacts stamped
        under the previous hash are now activation-INELIGIBLE until they are
        regenerated from a clean tree. Both refusals are fail-closed and,
        since AL-0061, both surface as `ActivationError` — the activation
        module's public contract — with the original
        `PartitionsNotActiveError` preserved as the chained cause.
        """
        from nqresearch.activation import (
            ActivationError,
            generate_active_partitions,
        )

        # Writing the active configuration is the step that would actually
        # activate; it must refuse.
        with pytest.raises(ActivationError):
            generate_active_partitions(
                "nobody", "AL-0060",
                datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc))

    def test_refusal_reason_is_missing_candidate_approval(self):
        # CHANGED REQUIREMENT (AL-0062): the artifacts have been regenerated
        # from the clean approved-policy commit, so "stale artifacts" is no
        # longer the blocking reason. The ONLY remaining gate is explicit
        # human approval of the exact candidate. Pinning the reason keeps a
        # silent regression from passing as "still refusing".
        from nqresearch.activation import (
            ActivationError,
            generate_active_partitions,
        )

        with pytest.raises(ActivationError) as exc:
            generate_active_partitions(
                "nobody", "AL-0060",
                datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc))
        msg = str(exc.value)
        assert "lifecycle state" not in msg, msg
        assert "human-approval audit entry" in msg, msg

    def test_no_partitions_active_yaml_exists(self):
        from nqresearch.config import _repo_root

        assert not (_repo_root() / "config" / "data"
                    / "partitions_active.yaml").is_file()

    def test_fence_and_research_api_still_fail_closed(self):
        from nqresearch.holdout import (
            PartitionsNotActiveError,
            assert_research_range_allowed,
            load_active_partitions,
        )
        from nqresearch.research import research_input_entries

        with pytest.raises(PartitionsNotActiveError):
            load_active_partitions()
        with pytest.raises(PartitionsNotActiveError):
            assert_research_range_allowed(date(2024, 10, 1), date(2024, 10, 31))
        with pytest.raises(PartitionsNotActiveError):
            research_input_entries(date(2024, 10, 1), date(2024, 10, 31))

    def test_holdout_opening_still_refuses_unconditionally(self):
        from nqresearch.holdout import HoldoutFenceError, holdout_opening

        with pytest.raises(HoldoutFenceError, match="not implemented"):
            holdout_opening()

    def test_exactly_one_candidate_approval_decision_exists(self):
        # CHANGED REQUIREMENT (AL-0064): the project owner approved the exact
        # candidate, so the reserved decision line now legitimately EXISTS.
        # It must exist exactly ONCE, carry exactly the reserved value, and
        # live under exactly AL-0064 — a second one anywhere would make
        # approval ambiguous.
        import re

        from nqresearch.config import _repo_root
        from nqresearch.holdout import APPROVAL_DECISION_VALUE

        text = (_repo_root() / "docs" / "implementation-audit-log.md").read_text(
            encoding="utf-8")
        lines = text.splitlines()
        idx = [i for i, ln in enumerate(lines)
               if re.match(r"^\s*-\s*decision\s*:", ln)]
        assert len(idx) == 1, [lines[i] for i in idx]
        assert re.fullmatch(r"-\s*decision:\s*" + re.escape(
            APPROVAL_DECISION_VALUE), lines[idx[0]].strip()), lines[idx[0]]
        # ...and it sits inside AL-0064, not any other entry.
        heading = next(lines[i] for i in range(idx[0], -1, -1)
                       if lines[i].startswith("## AL-"))
        assert heading.startswith("## AL-0064 "), heading

    def test_neutral_proposal_state_constant_is_still_required(self):
        # The generator can only ever emit the neutral state for the proposal.
        import inspect

        import nqresearch.qa.closeout as co

        src = inspect.getsource(co)
        assert '"state": "PROPOSED_NOT_ACTIVE"' in src
        assert '"activation_ready": False' in src
        assert '"activation_ready": True' not in src


class TestRealCandidateApprovalRecord:
    """AL-0064 is the real, committed human approval of candidate 5d9fc036.
    These assertions run the PRODUCTION verifier against an IN-MEMORY
    ActivePartitions model; they never call the publication path and never
    write config/data/partitions_active.yaml."""

    APPROVAL_REF = "AL-0064"
    APPROVER = "Wian"
    IDENT = {
        "activation_candidate_sha256":
            "5d9fc0362e65b263265acaf6162c04bbf5834ed58acf0354e87e861944f74b32",
        "partition_proposal_sha256":
            "24a555d6c45e691fe1838b7d7691059dce7bd6c7d07a55d5623e891a35a906fb",
        "effective_calendar_sha256":
            "ca2edfe6c2d05007c35837341ac73de955d8df6fd7821410307bf7fc18a3d010",
        "evidence_matrix_sha256":
            "f6099bd824691479dc246dfff44cdce239e9244333d21a56457f82ab714c1250",
        "cme_correspondence_sha256":
            "67adfa61f089b3d99153d412843d3b20f1ecddae9b7541778fc7b0a6556004b0",
        "research_eligibility_sha256":
            "b8678e628ea1dd25d8b7be05dbd6e24299bda002eec4593a223bf618c5620d0f",
        "coverage_artifact_sha256":
            "3230d9c28bb62d814fdf2d6c03054968b932d05f3de509a77dcbf4dc0432ba31",
        "mbo_blocks_sha256":
            "24862c197de32885f30ef976cbf258ab95b4aacaf31d8eb539e298d07d361da9",
        "front_contract_series_sha256":
            "d3d618a63c9623696b0a0f9c97b8d077e27bbb4f3cf48b23603f0d53121e960b",
    }
    RANGES = {"dev": ("2024-08-19", "2025-11-07"),
              "selection": ("2025-11-10", "2026-03-31"),
              "holdout": ("2026-04-01", "2026-08-14")}

    def _stamp(self):
        """The approval instant, read from the real AL-0064 record."""
        import re

        from nqresearch.config import _repo_root

        text = (_repo_root() / "docs" / "implementation-audit-log.md").read_text(
            encoding="utf-8")
        entry = text.split("## AL-0064 ")[1].split("\n## ")[0]
        m = re.search(r"^-\s*approved_at_utc:\s*(\S+)\s*$", entry, re.M)
        assert m, "AL-0064 must record approved_at_utc"
        return datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)

    def _parts(self, **over):
        from nqresearch.holdout import ActivePartitions

        payload = {
            "activated": True,
            "approval": {"approved_by": self.APPROVER,
                         "approval_reference": self.APPROVAL_REF,
                         "approved_at_utc": self._stamp()},
            **self.IDENT,
            "dev": {"start": self.RANGES["dev"][0],
                    "end": self.RANGES["dev"][1]},
            "selection": {"start": self.RANGES["selection"][0],
                          "end": self.RANGES["selection"][1]},
            "holdout": {"start": self.RANGES["holdout"][0],
                        "end": self.RANGES["holdout"][1]},
        }
        payload.update(over)
        return ActivePartitions(**payload)

    def test_real_approval_record_validates(self):
        from nqresearch.config import _repo_root
        from nqresearch.holdout import _verify_approval_bound_to_audit_record

        # Must not raise: all nine hashes, the three ranges, the approver, the
        # exact UTC instant, the disposition and the calendar state agree.
        _verify_approval_bound_to_audit_record(self._parts(), _repo_root())

    def test_approval_timestamp_is_whole_second_utc(self):
        stamp = self._stamp()
        assert stamp.tzinfo is not None
        assert stamp.utcoffset() == timedelta(0)
        assert stamp.microsecond == 0

    @pytest.mark.parametrize("field", sorted(IDENT))
    def test_each_wrong_identity_is_refused(self, field):
        from nqresearch.config import _repo_root
        from nqresearch.holdout import (
            PartitionsNotActiveError,
            _verify_approval_bound_to_audit_record,
        )

        with pytest.raises(PartitionsNotActiveError, match=field):
            _verify_approval_bound_to_audit_record(
                self._parts(**{field: "0" * 64}), _repo_root())

    @pytest.mark.parametrize("name", ["dev", "selection", "holdout"])
    def test_each_wrong_range_is_refused(self, name):
        from nqresearch.config import _repo_root
        from nqresearch.holdout import (
            PartitionsNotActiveError,
            _verify_approval_bound_to_audit_record,
        )

        a, b = self.RANGES[name]
        shifted = {"dev": {"start": "2024-08-20", "end": b},
                   "selection": {"start": a, "end": "2026-03-30"},
                   "holdout": {"start": "2026-04-02", "end": b}}[name]
        with pytest.raises(PartitionsNotActiveError,
                           match=f"{name}_range"):
            _verify_approval_bound_to_audit_record(
                self._parts(**{name: shifted}), _repo_root())

    @pytest.mark.parametrize("approver", ["Someone Else", "wian", "WIAN", ""])
    def test_wrong_approver_is_refused(self, approver):
        from nqresearch.config import _repo_root
        from nqresearch.holdout import (
            PartitionsNotActiveError,
            _verify_approval_bound_to_audit_record,
        )

        with pytest.raises(Exception):
            _verify_approval_bound_to_audit_record(
                self._parts(approval={"approved_by": approver,
                                      "approval_reference": self.APPROVAL_REF,
                                      "approved_at_utc": self._stamp()}),
                _repo_root())

    def test_wrong_timestamp_is_refused(self):
        from nqresearch.config import _repo_root
        from nqresearch.holdout import (
            PartitionsNotActiveError,
            _verify_approval_bound_to_audit_record,
        )

        with pytest.raises(PartitionsNotActiveError, match="approved_at_utc"):
            _verify_approval_bound_to_audit_record(
                self._parts(approval={
                    "approved_by": self.APPROVER,
                    "approval_reference": self.APPROVAL_REF,
                    "approved_at_utc": self._stamp() + timedelta(seconds=1)}),
                _repo_root())

    @pytest.mark.parametrize("ref,why", [
        ("AL-0063", "a different entry"),
        ("AL-0065", "a different entry"),
        ("AL-00640", "prefix attack"),
        ("AL-064", "malformed"),
        ("AL-0064 (approved)", "malformed"),
        (" AL-0064", "malformed"),
        ("al-0064", "malformed"),
    ])
    def test_wrong_or_malformed_reference_is_refused(self, ref, why):
        from nqresearch.config import _repo_root
        from nqresearch.holdout import (
            PartitionsNotActiveError,
            _verify_approval_bound_to_audit_record,
        )

        with pytest.raises(PartitionsNotActiveError):
            _verify_approval_bound_to_audit_record(
                self._parts(approval={"approved_by": self.APPROVER,
                                      "approval_reference": ref,
                                      "approved_at_utc": self._stamp()}),
                _repo_root())

    def test_duplicate_approval_field_is_refused(self, tmp_path):
        # A synthetic copy of the REAL entry with one field repeated must be
        # refused as ambiguous. The live log is never modified.
        import shutil

        from nqresearch.config import _repo_root
        from nqresearch.holdout import (
            PartitionsNotActiveError,
            _verify_approval_bound_to_audit_record,
        )

        root = tmp_path / "repo"
        (root / "docs").mkdir(parents=True)
        (root / "config" / "data").mkdir(parents=True)
        src = _repo_root() / "docs" / "implementation-audit-log.md"
        text = src.read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines()
                    if ln.strip().startswith("- decision:"))
        (root / "docs" / "implementation-audit-log.md").write_text(
            text + "\n" + line + "\n", encoding="utf-8")
        with pytest.raises(PartitionsNotActiveError, match="duplicate"):
            _verify_approval_bound_to_audit_record(self._parts(), root)
        assert shutil  # keep the import meaningful

    def test_approving_the_candidate_does_not_create_an_active_config(self):
        from nqresearch.config import _repo_root

        assert not (_repo_root() / "config" / "data"
                    / "partitions_active.yaml").is_file()

    def test_holdout_remains_sealed_after_approval(self):
        from nqresearch.holdout import (
            HoldoutFenceError,
            PartitionsNotActiveError,
            assert_research_range_allowed,
            holdout_opening,
            load_active_partitions,
        )

        # No active configuration exists, so the fence still refuses
        # everything, and the opening workflow refuses unconditionally.
        with pytest.raises(PartitionsNotActiveError):
            load_active_partitions()
        with pytest.raises(PartitionsNotActiveError):
            assert_research_range_allowed(date(2024, 10, 1), date(2024, 10, 31))
        with pytest.raises(HoldoutFenceError, match="not implemented"):
            holdout_opening()

    def test_approved_holdout_range_would_still_be_refused_by_the_fence(self):
        # The approval binds the HOLDOUT range so the fence knows what to
        # REFUSE — never as permission. Proven on the pure range logic.
        from nqresearch.holdout import HoldoutAccessError, _check_range

        parts = self._parts()
        h0, h1 = (date.fromisoformat(x) for x in self.RANGES["holdout"])
        for a, b in [(h0, h0), (h1, h1), (h0, h1),
                     (date.fromisoformat(self.RANGES["dev"][0]), h1)]:
            with pytest.raises(HoldoutAccessError):
                _check_range(a, b, parts)
        # ...while DEV and SELECTION are inside the permitted union.
        d0, d1 = (date.fromisoformat(x) for x in self.RANGES["dev"])
        s0, s1 = (date.fromisoformat(x) for x in self.RANGES["selection"])
        _check_range(d0, d1, parts)
        _check_range(s0, s1, parts)
        _check_range(d0, s1, parts)
