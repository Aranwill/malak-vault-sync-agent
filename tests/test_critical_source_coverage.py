from __future__ import annotations

import pytest

from malak_vault_sync.candidate_resolver import (
    find_unmapped_source_paths,
    resolve_candidates,
)
from malak_vault_sync.git_inspector import ChangedFile


@pytest.mark.parametrize(
    ("source_path", "expected_candidates"),
    [
        (
            "AGENTS.md",
            {
                "01-architecture/CURRENT_COMPONENTS_MAP.md",
                "02-current-baseline/CURRENT_BASELINE.md",
                "03-roadmap/IMPLEMENTATION_ROADMAP.md",
                "05-decisions/PENDING_DECISIONS.md",
                "08-session-context/MALAK_SESSION_CONTEXT.md",
                "10-knowledge-index/CONCEPTUAL_FOUNDATIONS.md",
                "10-knowledge-index/KNOWLEDGE_INDEX.md",
            },
        ),
        (
            "CHANGELOG.md",
            {
                "01-architecture/CURRENT_COMPONENTS_MAP.md",
                "02-current-baseline/CURRENT_BASELINE.md",
                "03-roadmap/IMPLEMENTATION_ROADMAP.md",
                "05-decisions/PENDING_DECISIONS.md",
                "08-session-context/MALAK_SESSION_CONTEXT.md",
                "10-knowledge-index/CONCEPTUAL_FOUNDATIONS.md",
                "10-knowledge-index/KNOWLEDGE_INDEX.md",
            },
        ),
        (
            "SECURITY.md",
            {
                "02-current-baseline/CURRENT_BASELINE.md",
                "06-security/SECURITY_INDEX.md",
                "07-audits/AUDIT_INDEX.md",
                "08-session-context/MALAK_SESSION_CONTEXT.md",
            },
        ),
        (
            "docs/project/concepts/MALAK_RESEARCH_HORIZON_MAP.md",
            {
                "10-knowledge-index/CONCEPTUAL_FOUNDATIONS.md",
                "10-knowledge-index/KNOWLEDGE_INDEX.md",
            },
        ),
        (
            "docs/project/concepts/README.md",
            {
                "10-knowledge-index/CONCEPTUAL_FOUNDATIONS.md",
                "10-knowledge-index/KNOWLEDGE_INDEX.md",
            },
        ),
        (
            "docs/development/malak_construction_protocol.md",
            {
                "02-current-baseline/CURRENT_BASELINE.md",
                "08-session-context/MALAK_SESSION_CONTEXT.md",
            },
        ),
        (
            "docs/development/development_checklist.md",
            {
                "02-current-baseline/CURRENT_BASELINE.md",
                "08-session-context/MALAK_SESSION_CONTEXT.md",
            },
        ),
        (
            ".github/PULL_REQUEST_TEMPLATE.md",
            {
                "02-current-baseline/CURRENT_BASELINE.md",
                "08-session-context/MALAK_SESSION_CONTEXT.md",
            },
        ),
    ],
)
def test_critical_source_path_is_mapped_without_omission(
    source_path: str,
    expected_candidates: set[str],
) -> None:
    changed_files = (
        ChangedFile(status="M", path=source_path),
    )

    assert find_unmapped_source_paths(changed_files) == ()

    candidates = resolve_candidates(changed_files)
    assert {candidate.path for candidate in candidates} == expected_candidates
    assert all(
        candidate.disposition == "review_required"
        for candidate in candidates
    )


def test_unknown_relevant_source_path_remains_visible_as_unmapped() -> None:
    changed_files = (
        ChangedFile(
            status="A",
            path="docs/project/new-governed-source.md",
        ),
    )

    assert find_unmapped_source_paths(changed_files) == (
        "docs/project/new-governed-source.md",
    )
    assert resolve_candidates(changed_files) == ()
