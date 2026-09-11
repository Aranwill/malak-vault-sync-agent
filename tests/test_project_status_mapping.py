from __future__ import annotations

from malak_vault_sync.candidate_resolver import (
    find_unmapped_source_paths,
    resolve_candidates,
)
from malak_vault_sync.git_inspector import ChangedFile


def test_project_status_is_mapped_as_baseline_source() -> None:
    changed = (
        ChangedFile(
            status="A",
            path=(
                "docs/project/status/"
                "MALAK-POST-AUDIT-REBASELINE-20260911.md"
            ),
        ),
    )

    assert find_unmapped_source_paths(changed) == ()

    candidates = resolve_candidates(changed)

    assert [candidate.path for candidate in candidates] == [
        "10-knowledge-index/KNOWLEDGE_INDEX.md",
        "10-knowledge-index/CONCEPTUAL_FOUNDATIONS.md",
        "08-session-context/MALAK_SESSION_CONTEXT.md",
        "05-decisions/PENDING_DECISIONS.md",
        "03-roadmap/IMPLEMENTATION_ROADMAP.md",
        "02-current-baseline/CURRENT_BASELINE.md",
        "01-architecture/CURRENT_COMPONENTS_MAP.md",
    ]

    assert all(candidate.priority == "high" for candidate in candidates)
    assert all(
        any(
            reason.rule_id == "baseline-source-change"
            for reason in candidate.reasons
        )
        for candidate in candidates
    )
