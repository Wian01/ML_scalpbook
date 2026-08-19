"""Experiment pre-registration model (canonical §37) and lifecycle states.

Every §37 field is REQUIRED at registration; once execution begins the
registered specification is immutable (enforced by the registry via content
hashing). A new idea after seeing results is a new experiment.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

STATE_PLANNED = "PLANNED"
STATE_RUNNING = "RUNNING"
STATE_PASSED = "PASSED"
STATE_FAILED = "FAILED"
STATE_INCONCLUSIVE = "INCONCLUSIVE"
STATE_SUSPECT = "SUSPECT_AUDIT_REQUIRED"

TERMINAL_STATES = frozenset(
    {STATE_PASSED, STATE_FAILED, STATE_INCONCLUSIVE, STATE_SUSPECT}
)
ALL_STATES = frozenset({STATE_PLANNED, STATE_RUNNING, *TERMINAL_STATES})

# The only legal transitions (canonical §37). Terminal states have none.
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    STATE_PLANNED: frozenset({STATE_RUNNING}),
    STATE_RUNNING: TERMINAL_STATES,
    **{s: frozenset() for s in TERMINAL_STATES},
}


class PreRegistration(BaseModel):
    """Complete §37 pre-registration. All fields required unless noted."""

    research_question: str
    hypothesis: str
    dataset_version: str
    source_dataset_hashes: dict[str, str]  # dataset name -> content identity (§38)
    partition: str
    sample_table_version: str
    feature_family_versions: dict[str, str]  # name -> version/hash
    label_version: str
    volatility_estimator_version: str
    horizon: str
    latency_ms: int
    fold_scheme: str
    seeds: list[int]
    model_type: str
    hyperparameters: dict
    primary_metric: str
    secondary_metrics: list[str]
    acceptance_criterion: str
    kill_criteria: list[str]
    cost_model_version: str
    parent_experiment: str | None = None
    parent_hypothesis: str | None = None
    notes: str = ""

    model_config = {"extra": "forbid"}

    @field_validator(
        "research_question", "hypothesis", "dataset_version", "partition",
        "sample_table_version", "label_version", "volatility_estimator_version",
        "horizon", "fold_scheme", "model_type", "primary_metric",
        "acceptance_criterion", "cost_model_version",
    )
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("required pre-registration field must be non-empty")
        return v

    @field_validator("kill_criteria", "seeds")
    @classmethod
    def _non_empty_list(cls, v: list) -> list:
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("source_dataset_hashes")
    @classmethod
    def _valid_dataset_identities(cls, v: dict[str, str]) -> dict[str, str]:
        """§38: identities must be normalized `algo:hex` (sha256 supported);
        bare 64-hex is normalized to `sha256:<hex>`; arbitrary strings fail."""
        import re

        if not v:
            raise ValueError("source_dataset_hashes must not be empty (§38)")
        out: dict[str, str] = {}
        for name, ident in v.items():
            if not name.strip():
                raise ValueError("dataset name must be non-empty")
            s = ident.strip().lower()
            if re.fullmatch(r"[0-9a-f]{64}", s):
                s = f"sha256:{s}"
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", s):
                raise ValueError(
                    f"dataset identity for {name!r} must be a SHA-256 "
                    "(64 hex chars, optionally 'sha256:'-prefixed); got "
                    f"{ident!r}"
                )
            out[name] = s
        return out


class OutputRecord(BaseModel):
    """One §38 output: identity, size, type, and location."""

    name: str
    output_type: str  # e.g. metrics, predictions, plot, report
    location: str     # path/URI relative to the experiment's storage policy
    size_bytes: int
    sha256: str

    model_config = {"extra": "forbid"}

    @field_validator("name", "output_type", "location")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("output fields must be non-empty")
        return v

    @field_validator("size_bytes")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("size_bytes must be >= 0")
        return v

    @field_validator("sha256")
    @classmethod
    def _sha(cls, v: str) -> str:
        import re

        if not re.fullmatch(r"[0-9a-f]{64}", v.lower()):
            raise ValueError("output sha256 must be 64 hex chars")
        return v.lower()


class OutputsManifest(BaseModel):
    """Structured terminal outputs manifest (§38). Synthetic/null experiments
    may record an EXPLICITLY empty manifest; arbitrary dictionaries are
    rejected."""

    outputs: list[OutputRecord] = []
    note: str = ""

    model_config = {"extra": "forbid"}
