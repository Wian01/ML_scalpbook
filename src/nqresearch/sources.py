"""MBP-1 source selection driven by the provenance registry.

Raw job directories under <data_root>/raw/mbp1/ must NEVER be enumerated
recursively as one pool: the Milestone 0 QA sample overlaps the canonical
annual corpus, so blind globbing would double-count dates and mix acquisition
vintages. All selection goes through config/data/mbp1_sources.yaml:

- the Milestone 0 sample audit selects only the MILESTONE0_QA_SAMPLE source;
- research/normalization input enumerates only research-eligible
  (FULL_HISTORY_CANONICAL) sources, one file per logical daily partition;
- any date covered by two research-eligible sources fails loudly.

Deduplication happens only at this source-job/partition level — never by
row-level or timestamp/price/size heuristics (legitimate market messages can
share those values).
"""

from __future__ import annotations

from pathlib import Path

from nqresearch import paths
from nqresearch.config import (
    ROLE_M0_QA_SAMPLE,
    Mbp1Source,
    Mbp1SourceRegistry,
    load_mbp1_sources,
)
from nqresearch.filenames import file_date_key


class SourceRegistryError(RuntimeError):
    """The registry is missing, ambiguous, or inconsistent with intent."""


class ResearchOverlapError(RuntimeError):
    """Two research-eligible sources cover the same logical daily partition."""


def source_dir(source: Mbp1Source, data_root: Path | None = None) -> Path:
    return (data_root or paths.data_root()) / source.path


def qa_sample_source(registry: Mbp1SourceRegistry | None = None) -> Mbp1Source:
    reg = registry if registry is not None else load_mbp1_sources()
    samples = reg.by_role(ROLE_M0_QA_SAMPLE)
    if len(samples) != 1:
        raise SourceRegistryError(
            f"expected exactly one MILESTONE0_QA_SAMPLE source, found {len(samples)}; "
            "refusing to guess the Milestone 0 sample directory"
        )
    return samples[0]


def m0_sample_dir(
    registry: Mbp1SourceRegistry | None = None, data_root: Path | None = None
) -> Path:
    """Directory audited by the Milestone 0 MBP-1 sample audit — only ever the
    registered QA sample, never the full raw/mbp1 tree."""
    return source_dir(qa_sample_source(registry), data_root)


def file_date_key_safe(filename: str) -> str | None:
    """file_date_key, returning None for non-daily filenames."""
    try:
        return file_date_key(filename)
    except ValueError:
        return None


def _canonical_corpus_entries(
    registry: Mbp1SourceRegistry | None = None, data_root: Path | None = None
) -> dict[str, tuple[Path, str]]:
    """PRIVATE canonical-corpus enumeration (QA-only via nqresearch.qa_corpus).

    Logical daily partition (YYYYMMDD) -> (DBN file, owning request_id) over
    research-eligible sources, with explicit ownership tracking. A partition
    appearing in more than one research-eligible source raises
    ResearchOverlapError — an unexpected overlap must never be silently
    resolved.

    THERE IS NO PUBLIC RESEARCH ENUMERATION HERE: the former
    research_input_entries/research_input_files interfaces were removed
    (independent-audit remediation) because they mechanically bypassed the
    holdout fence. Ordinary research loading goes through
    nqresearch.research, which is fenced, provenance-checked, and — until
    the Milestone 2 session-filtered reader exists — refuses entirely.
    """
    reg = registry if registry is not None else load_mbp1_sources()
    eligible = reg.research_sources()
    if not eligible:
        raise SourceRegistryError("no research-eligible MBP-1 sources registered")
    out: dict[str, tuple[Path, str]] = {}
    for src in eligible:
        base = source_dir(src, data_root)
        for f in sorted(base.glob("*.mbp-1.dbn.zst")):
            key = file_date_key(f.name)
            if key in out:
                raise ResearchOverlapError(
                    f"logical partition {key} covered by both "
                    f"{out[key][1]} and {src.request_id}; a partition may enter "
                    "the research input set exactly once"
                )
            out[key] = (f, src.request_id)
    return out




class ProvenanceError(RuntimeError):
    """Acquisition/provenance gate evidence is missing, stale, or failed."""


def _verify_committed_ancestor(sha: str, repo_root: Path) -> None:
    """PRIVATE fail-closed Git binding check (tests may inject a synthetic
    repo root here; require_provenance() itself always validates against the
    actual project repository and exposes no root override).

    Requires — via non-mutating Git operations — that `sha`:
    - is EXACTLY a commit object: `git cat-file -t <sha>` must succeed and
      print exactly "commit". The peeling form `<sha>^{commit}` is
      deliberately NOT used as the type proof: it resolves an annotated-tag
      object to its target commit, so a tag-object SHA would masquerade as
      a commit. Tags (annotated tag objects), blobs, trees, missing
      objects, and malformed output all refuse here. A lightweight tag is
      unaffected — its SHA *is* the commit object's SHA.
    - is an ANCESTOR of current HEAD (`git merge-base --is-ancestor`),
      checked only after the exact object-type proof passes.
    Any Git execution failure, missing repository, or unborn HEAD refuses.
    HEAD equality is deliberately NOT required: an audit-log-only commit
    after artifact generation keeps the generation commit a valid ancestor.
    """
    import subprocess

    def _git(*args) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                ["git", "-C", str(repo_root), *args],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise ProvenanceError(
                "git is unavailable or failed while verifying the gate "
                f"git_sha; unverifiable generation provenance is never "
                f"accepted: {e}"
            ) from e

    r = _git("cat-file", "-t", sha)
    obj_type = r.stdout.strip() if r.returncode == 0 else None
    if obj_type != "commit":
        raise ProvenanceError(
            f"acquisition gate git_sha {sha[:12]}… does not exist as a "
            f"commit object in the project repository (object type "
            f"{obj_type!r}: fabricated, foreign, tag, or other non-commit "
            "generation evidence is never accepted)"
        )
    r = _git("merge-base", "--is-ancestor", sha, "HEAD")
    if r.returncode != 0:
        raise ProvenanceError(
            f"acquisition gate git_sha {sha[:12]}… is not an ancestor of "
            "current HEAD (unrelated-branch or unverifiable generation "
            "evidence is never accepted)"
        )


def require_provenance(
    data_root: Path | None = None,
    registry: Mbp1SourceRegistry | None = None,
) -> dict:
    """Refuse research preparation unless a valid, bound acquisition gate exists.

    Loads <data_root>/qa/mbp1_full_history/mbp1_acquisition_gate.json and
    verifies:
    - gate status PASS AND all nine named gate checks present and PASS
      (never trusting only the top-level status field);
    - gate generated from a CLEAN COMMITTED tree: `generation_git_clean`
      must be exactly boolean true (missing/false/"true"/anything else is
      rejected — the envelope layer stamps it and payloads cannot forge it)
      and `git_sha` must be a real 40-hex committed SHA. The gate SHA is
      deliberately NOT required to equal current HEAD: the audit-log-only
      second commit legitimately follows artifact generation; semantic
      validity is carried by the code/config/manifest bindings below;
    - gate generated under the CURRENT effective configuration hash;
    - gate generated by the CURRENT acquisition/provenance code
      (recomputes acquisition_code_hash() — stale code evidence is rejected);
    - vendor manifest identities on disk still match both the registry and
      the gate.

    Raises ProvenanceError otherwise; returns the gate payload on success.
    Cheap (no decode) — the expensive record-level comparison is not re-run
    once valid bound evidence exists.
    """
    import json

    from nqresearch.config import effective_config_hash
    from nqresearch.qa.manifest import sha256_file
    from nqresearch.qa.mbp1_acquisition import (
        EXPECTED_GATE_CHECKS,
        acquisition_code_hash,
    )

    root = data_root or paths.data_root()
    gate_path = root / "qa" / "mbp1_full_history" / "mbp1_acquisition_gate.json"
    if not gate_path.is_file():
        raise ProvenanceError(f"acquisition gate artifact missing: {gate_path}")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if gate.get("status") != "PASS":
        raise ProvenanceError(f"acquisition gate status is {gate.get('status')!r}, not PASS")

    checks = gate.get("checks")
    if not isinstance(checks, list):
        raise ProvenanceError("acquisition gate has no 'checks' list; malformed gate")
    by_name = {c.get("check"): c.get("status") for c in checks if isinstance(c, dict)}
    for name in EXPECTED_GATE_CHECKS:
        if name not in by_name:
            raise ProvenanceError(f"acquisition gate is missing required check {name!r}")
        if by_name[name] != "PASS":
            raise ProvenanceError(
                f"acquisition gate check {name!r} is {by_name[name]!r}, not PASS"
            )

    clean = gate.get("generation_git_clean")
    if clean is not True or not isinstance(clean, bool):
        raise ProvenanceError(
            "acquisition gate was not generated from a clean committed tree "
            f"(generation_git_clean={clean!r}; must be exactly boolean "
            "true): dirty-tree or legacy-envelope evidence is never "
            "accepted; regenerate from a clean committed tree"
        )
    import re as _re

    sha = gate.get("git_sha")
    if not (isinstance(sha, str) and _re.fullmatch(r"[0-9a-f]{40}", sha)):
        raise ProvenanceError(
            f"acquisition gate has no valid committed git_sha ({sha!r}); "
            "unverifiable generation provenance is never accepted"
        )
    # Format alone proves nothing: the SHA must be a REAL commit in the
    # actual project repository AND an ancestor of current HEAD (the
    # audit-log-only second commit legitimately moves HEAD past it; a
    # fabricated, foreign, non-ancestor, or non-commit object never passes).
    _verify_committed_ancestor(sha, paths.ROOT)
    if gate.get("config_hash") != effective_config_hash():
        raise ProvenanceError(
            "acquisition gate was generated under a different effective "
            "configuration; re-run the acquisition validation"
        )
    if gate.get("acquisition_code_hash") != acquisition_code_hash():
        raise ProvenanceError(
            "acquisition gate was generated by different acquisition/provenance "
            "code; re-run the acquisition validation"
        )
    reg = registry if registry is not None else load_mbp1_sources()
    for s in reg.sources:
        actual = sha256_file(source_dir(s, root) / s.manifest)
        if actual != s.manifest_sha256 or (
            gate.get("current_manifest_sha256", {}).get(s.request_id) != actual
        ):
            raise ProvenanceError(
                f"{s.request_id}: manifest identity changed since the gate was "
                "generated; re-run the acquisition validation"
            )
    return gate


def validate_adjacent_ranges(sources: list[Mbp1Source]) -> dict:
    """Check that research sources form one contiguous [start, end) chain in
    UTC-ns query time, with no gap and no overlap."""
    ordered = sorted(sources, key=lambda s: s.start_ns)
    issues = []
    for a, b in zip(ordered, ordered[1:]):
        if a.end_ns < b.start_ns:
            issues.append(
                {"issue": "gap", "after": a.request_id, "before": b.request_id,
                 "gap_ns": b.start_ns - a.end_ns}
            )
        elif a.end_ns > b.start_ns:
            issues.append(
                {"issue": "overlap", "first": a.request_id, "second": b.request_id,
                 "overlap_ns": a.end_ns - b.start_ns}
            )
    return {
        "ordered_request_ids": [s.request_id for s in ordered],
        "range_start_ns": ordered[0].start_ns if ordered else None,
        "range_end_ns": ordered[-1].end_ns if ordered else None,
        "adjacent": not issues,
        "issues": issues,
    }
