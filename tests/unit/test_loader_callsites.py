"""Executable call-site audit: no module outside the QA allowlist may use the
QA-only full-corpus enumeration (sources.research_input_* legacy names or
qa_corpus.*). Future normalization must use nqresearch.research (fenced)."""

import re
from pathlib import Path

import nqresearch

PKG = Path(nqresearch.__file__).parent

# Modules permitted to reference the unfenced full-corpus enumerators:
QA_ALLOWLIST = {
    "sources.py",            # defines the legacy enumerators (gate-bound module)
    "qa_corpus.py",          # the explicit QA-only wrapper
    "research.py",           # fenced API; enumerates ONLY after the fence passes
    "qa/mbp1_acquisition.py",  # acquisition QA (gate-bound module)
    "qa/full_history_audit.py",  # coverage QA via qa_corpus
}

PATTERN = re.compile(
    r"research_input_entries|research_input_files|qa_corpus_entries"
    r"|qa_corpus_files|_canonical_corpus_entries"
)


class TestLoaderCallsites:
    def test_only_qa_allowlist_uses_corpus_enumeration(self):
        offenders = []
        for f in PKG.rglob("*.py"):
            rel = f.relative_to(PKG).as_posix()
            if rel in QA_ALLOWLIST:
                continue
            if PATTERN.search(f.read_text(encoding="utf-8")):
                offenders.append(rel)
        assert offenders == [], (
            f"non-QA modules reference corpus enumeration APIs: {offenders}; "
            "research loading must go through nqresearch.research"
        )

    def test_research_module_gates_and_never_enumerates(self):
        src = (PKG / "research.py").read_text(encoding="utf-8")
        assert "assert_research_range_allowed" in src
        assert "require_provenance" in src
        # Milestone 1: the research module performs NO corpus enumeration at
        # all — it refuses after the gates.
        assert "qa_corpus_entries" not in src
        assert "_canonical_corpus_entries" not in src
        assert "ResearchLoaderNotImplementedError" in src
