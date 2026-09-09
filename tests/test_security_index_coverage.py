from __future__ import annotations

from malak_vault_sync.candidate_resolver import (
    is_allowed_vault_path,
    resolve_candidates,
)
from malak_vault_sync.git_inspector import ChangedFile


def test_security_index_is_allowlisted() -> None:
    assert is_allowed_vault_path(
        "06-security/SECURITY_INDEX.md"
    ) is True


def test_security_change_includes_security_index_candidate() -> None:
    candidates = resolve_candidates(
        (
            ChangedFile(
                status="M",
                path="SECURITY.md",
            ),
        )
    )

    assert [candidate.path for candidate in candidates] == [
        "08-session-context/MALAK_SESSION_CONTEXT.md",
        "07-audits/AUDIT_INDEX.md",
        "06-security/SECURITY_INDEX.md",
        "02-current-baseline/CURRENT_BASELINE.md",
    ]

    security_index = next(
        candidate
        for candidate in candidates
        if candidate.path == "06-security/SECURITY_INDEX.md"
    )

    assert security_index.priority == "high"
    assert security_index.disposition == "review_required"
    assert {
        (reason.rule_id, reason.source_path)
        for reason in security_index.reasons
    } == {
        ("security-change", "SECURITY.md"),
    }
