"""QA-ONLY full-corpus enumeration (explicitly named; never research input).

These wrappers exist so QA/audit code states its intent in its imports.
They enumerate the complete canonical corpus WITHOUT the holdout fence,
which is legitimate ONLY for data-verification operations (acquisition
validation, coverage audits, provenance checks) — never for building
research datasets. Ordinary research loading must use
`nqresearch.research`, which is fenced and provenance-checked and — until
Milestone 2 implements a session-filtered reader — refuses entirely.

The former public `sources.research_input_entries/files` interfaces were
REMOVED (independent-audit remediation): full-corpus enumeration is only
reachable through these QA-named wrappers over the private implementation,
and the executable call-site allowlist test
(tests/unit/test_loader_callsites.py) fails if any module outside the QA
allowlist references them.
"""

from __future__ import annotations

from pathlib import Path

from nqresearch.config import Mbp1SourceRegistry
from nqresearch.sources import _canonical_corpus_entries


def qa_corpus_entries(
    registry: Mbp1SourceRegistry | None = None, data_root: Path | None = None
) -> dict[str, tuple[Path, str]]:
    """QA-only: every canonical daily partition -> (file, owning request_id)."""
    return _canonical_corpus_entries(registry, data_root)


def qa_corpus_files(
    registry: Mbp1SourceRegistry | None = None, data_root: Path | None = None
) -> dict[str, Path]:
    """QA-only: every canonical daily partition -> file."""
    return {k: p for k, (p, _) in qa_corpus_entries(registry, data_root).items()}
