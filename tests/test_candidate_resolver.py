from __future__ import annotations

import pytest

from malak_vault_sync.candidate_resolver import (
    CandidateResolutionError,
    CandidateRule,
    default_rules,
    is_allowed_vault_path,
    is_denied_vault_path,
    resolve_candidates,
    CandidateReason,
    find_unmapped_source_paths,
    is_explicitly_ignored_source_path,
)
from malak_vault_sync.git_inspector import ChangedFile


def test_architecture_change_returns_expected_candidates() -> None:
    candidates = resolve_candidates(
        (
            ChangedFile(
                status="M",
                path="src/malak/providers/runtime_provider.py",
            ),
        )
    )

    assert [candidate.path for candidate in candidates] == [
        "08-session-context/MALAK_SESSION_CONTEXT.md",
        "02-current-baseline/CURRENT_BASELINE.md",
        "01-architecture/CURRENT_COMPONENTS_MAP.md",
    ]

    assert all(
        candidate.priority == "high"
        for candidate in candidates
    )

    assert all(
        candidate.disposition == "review_required"
        for candidate in candidates
    )


def test_test_change_returns_medium_priority_candidates() -> None:
    candidates = resolve_candidates(
        (
            ChangedFile(
                status="M",
                path="tests/test_runtime.py",
            ),
        )
    )

    assert [candidate.path for candidate in candidates] == [
        "08-session-context/MALAK_SESSION_CONTEXT.md",
        "02-current-baseline/CURRENT_BASELINE.md",
    ]

    assert all(
        candidate.priority == "medium"
        for candidate in candidates
    )


def test_multiple_rules_consolidate_reasons_and_priority() -> None:
    candidates = resolve_candidates(
        (
            ChangedFile(
                status="M",
                path="README.md",
            ),
            ChangedFile(
                status="M",
                path="tests/test_runtime.py",
            ),
        )
    )

    baseline = next(
        candidate
        for candidate in candidates
        if candidate.path
        == "02-current-baseline/CURRENT_BASELINE.md"
    )

    assert baseline.priority == "high"

    assert len(baseline.reasons) == 2

    assert {
        reason.rule_id
        for reason in baseline.reasons
    } == {
        "baseline-source-change",
        "test-change",
    }


def test_duplicate_reasons_are_removed() -> None:
    candidates = resolve_candidates(
        (
            ChangedFile(
                status="M",
                path="README.md",
            ),
            ChangedFile(
                status="M",
                path="README.md",
            ),
        )
    )

    baseline = next(
        candidate
        for candidate in candidates
        if candidate.path
        == "02-current-baseline/CURRENT_BASELINE.md"
    )

    assert len(baseline.reasons) == 1


def test_no_matching_rule_returns_empty_tuple() -> None:
    candidates = resolve_candidates(
        (
            ChangedFile(
                status="M",
                path="documents/projects/jarvis/archive/legacy.md",
            ),
        )
    )

    assert candidates == ()


def test_current_governance_path_returns_candidates() -> None:
    candidates = resolve_candidates(
        (
            ChangedFile(
                status="M",
                path="docs/governance/cognitive_constitution.md",
            ),
        )
    )

    assert {
        candidate.path for candidate in candidates
    } >= {
        "05-decisions/PENDING_DECISIONS.md",
        "08-session-context/MALAK_SESSION_CONTEXT.md",
    }


@pytest.mark.parametrize(
    "source_path",
    (
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".gitignore",
        "AGENTS.md",
        "configs/models.yaml",
        "docs/development/development_checklist.md",
        "docs/knowledge/recipes/REC-001.md",
        "documents/projects/jarvis/ideas.md",
        "examples/hello_kernel.py",
        "scripts/run.ps1",
        "src/app/main.py",
    ),
)
def test_current_malak_paths_are_covered(source_path: str) -> None:
    candidates = resolve_candidates(
        (ChangedFile(status="M", path=source_path),)
    )

    assert candidates


def test_rename_considers_previous_and_current_paths() -> None:
    candidates = resolve_candidates(
        (
            ChangedFile(
                status="R100",
                previous_path="docs/governance/old.md",
                path="archive/old.md",
            ),
        )
    )

    assert candidates
    assert all(
        reason.source_path == "docs/governance/old.md"
        for candidate in candidates
        for reason in candidate.reasons
    )


def test_windows_paths_are_normalized() -> None:
    candidates = resolve_candidates(
        (
            ChangedFile(
                status="M",
                path=r"src\malak\kernel\kernel.py",
            ),
        )
    )

    assert candidates

    assert all(
        reason.source_path
        == "src/malak/kernel/kernel.py"
        for candidate in candidates
        for reason in candidate.reasons
    )


def test_parent_traversal_in_source_path_is_rejected() -> None:
    with pytest.raises(
        CandidateResolutionError,
        match="parent traversal",
    ):
        resolve_candidates(
            (
                ChangedFile(
                    status="M",
                    path="../README.md",
                ),
            )
        )


def test_absolute_source_path_is_rejected() -> None:
    with pytest.raises(
        CandidateResolutionError,
        match="must be relative",
    ):
        resolve_candidates(
            (
                ChangedFile(
                    status="M",
                    path="/tmp/README.md",
                ),
            )
        )


def test_snapshot_path_is_denied() -> None:
    assert is_denied_vault_path(
        "09-repository-snapshots/2026-07-22.md"
    ) is True

    assert is_allowed_vault_path(
        "09-repository-snapshots/2026-07-22.md"
    ) is False


def test_allowlisted_path_is_allowed() -> None:
    assert is_allowed_vault_path(
        "02-current-baseline/CURRENT_BASELINE.md"
    ) is True


def test_non_allowlisted_path_is_rejected() -> None:
    rule = CandidateRule(
        rule_id="invalid-candidate",
        source_patterns=("README.md",),
        vault_candidates=("notes/UNTRACKED.md",),
        priority="high",
    )

    with pytest.raises(
        CandidateResolutionError,
        match="not allowlisted",
    ):
        resolve_candidates(
            (
                ChangedFile(
                    status="M",
                    path="README.md",
                ),
            ),
            rules=(rule,),
        )


def test_snapshot_candidate_rule_is_rejected() -> None:
    rule = CandidateRule(
        rule_id="snapshot-candidate",
        source_patterns=("README.md",),
        vault_candidates=(
            "09-repository-snapshots/2026-07-22.md",
        ),
        priority="high",
    )

    with pytest.raises(
        CandidateResolutionError,
        match="denied",
    ):
        resolve_candidates(
            (
                ChangedFile(
                    status="M",
                    path="README.md",
                ),
            ),
            rules=(rule,),
        )


def test_duplicate_rule_id_is_rejected() -> None:
    rule_a = CandidateRule(
        rule_id="duplicate",
        source_patterns=("README.md",),
        vault_candidates=(
            "02-current-baseline/CURRENT_BASELINE.md",
        ),
        priority="high",
    )

    rule_b = CandidateRule(
        rule_id="duplicate",
        source_patterns=("tests/**",),
        vault_candidates=(
            "08-session-context/MALAK_SESSION_CONTEXT.md",
        ),
        priority="medium",
    )

    with pytest.raises(
        CandidateResolutionError,
        match="Duplicate rule ID",
    ):
        resolve_candidates(
            (),
            rules=(rule_a, rule_b),
        )


def test_invalid_priority_is_rejected() -> None:
    rule = CandidateRule(
        rule_id="invalid-priority",
        source_patterns=("README.md",),
        vault_candidates=(
            "02-current-baseline/CURRENT_BASELINE.md",
        ),
        priority="critical",
    )

    with pytest.raises(
        CandidateResolutionError,
        match="Unsupported priority",
    ):
        resolve_candidates(
            (),
            rules=(rule,),
        )


def test_default_rules_are_available() -> None:
    rules = default_rules()

    assert len(rules) == 8
    assert {
        rule.rule_id
        for rule in rules
    } == {
        "baseline-source-change",
        "architecture-change",
        "test-change",
        "governance-change",
        "security-change",
        "knowledge-change",
        "conceptual-foundation-change",
        "operational-tooling-change",
    }



def test_baseline_source_change_invalidates_all_active_baseline_projections() -> None:
    candidates = resolve_candidates(
        (
            ChangedFile(
                status="M",
                path="docs/project/sprints/SPRINT-7.7.md",
            ),
        )
    )

    assert [candidate.path for candidate in candidates] == [
        "10-knowledge-index/KNOWLEDGE_INDEX.md",
        "08-session-context/MALAK_SESSION_CONTEXT.md",
        "05-decisions/PENDING_DECISIONS.md",
        "03-roadmap/IMPLEMENTATION_ROADMAP.md",
        "02-current-baseline/CURRENT_BASELINE.md",
        "01-architecture/CURRENT_COMPONENTS_MAP.md",
    ]

    assert all(
        any(
            reason.rule_id == "baseline-source-change"
            for reason in candidate.reasons
        )
        for candidate in candidates
    )

def test_conceptual_foundation_change_returns_knowledge_candidates() -> None:
    candidates = resolve_candidates(
        (
            ChangedFile(
                status="A",
                path=(
                    "docs/project/concepts/"
                    "MALAK_COGNITIVE_DATASET_FOUNDATION.md"
                ),
            ),
        )
    )

    assert [candidate.path for candidate in candidates] == [
        "10-knowledge-index/KNOWLEDGE_INDEX.md",
        "10-knowledge-index/CONCEPTUAL_FOUNDATIONS.md",
    ]

    assert all(
        candidate.priority == "medium"
        for candidate in candidates
    )

    assert all(
        candidate.reasons
        == (
            CandidateReason(
                rule_id="conceptual-foundation-change",
                source_path=(
                    "docs/project/concepts/"
                    "MALAK_COGNITIVE_DATASET_FOUNDATION.md"
                ),
            ),
        )
        for candidate in candidates
    )


def test_archive_source_path_is_explicitly_ignored() -> None:
    assert is_explicitly_ignored_source_path(
        "documents/projects/jarvis/archive/"
        "estado_actual_jarvis_v0.4.1.md"
    ) is True


def test_mapped_source_path_is_not_reported_unmapped() -> None:
    unmapped = find_unmapped_source_paths(
        (
            ChangedFile(
                status="M",
                path="src/malak/kernel/kernel.py",
            ),
        )
    )

    assert unmapped == ()


def test_explicitly_ignored_source_path_is_not_reported_unmapped() -> None:
    unmapped = find_unmapped_source_paths(
        (
            ChangedFile(
                status="M",
                path=(
                    "documents/projects/jarvis/archive/"
                    "legacy.md"
                ),
            ),
        )
    )

    assert unmapped == ()


def test_unknown_source_path_is_reported_unmapped() -> None:
    unmapped = find_unmapped_source_paths(
        (
            ChangedFile(
                status="A",
                path="future/new-area/file.md",
            ),
        )
    )

    assert unmapped == (
        "future/new-area/file.md",
    )


def test_unmapped_rename_checks_previous_and_current_paths() -> None:
    unmapped = find_unmapped_source_paths(
        (
            ChangedFile(
                status="R100",
                previous_path="future/old/file.md",
                path="src/malak/new/file.py",
            ),
        )
    )

    assert unmapped == (
        "future/old/file.md",
    )


def test_unmapped_source_paths_are_normalized_and_deduplicated() -> None:
    unmapped = find_unmapped_source_paths(
        (
            ChangedFile(
                status="M",
                path=r"future\new-area\file.md",
            ),
            ChangedFile(
                status="M",
                path="future/new-area/file.md",
            ),
        )
    )

    assert unmapped == (
        "future/new-area/file.md",
    )
