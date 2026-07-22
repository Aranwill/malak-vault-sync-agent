from __future__ import annotations

import pytest

from malak_vault_sync.candidate_resolver import (
    CandidateResolutionError,
    CandidateRule,
    default_rules,
    is_allowed_vault_path,
    is_denied_vault_path,
    resolve_candidates,
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
                path="examples/demo.txt",
            ),
        )
    )

    assert candidates == ()


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
        "09-snapshots/2026-07-22.md"
    ) is True

    assert is_allowed_vault_path(
        "09-snapshots/2026-07-22.md"
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
            "09-snapshots/2026-07-22.md",
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

    assert len(rules) == 5
    assert {
        rule.rule_id
        for rule in rules
    } == {
        "baseline-source-change",
        "architecture-change",
        "test-change",
        "governance-change",
        "security-change",
    }