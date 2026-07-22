from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath

from malak_vault_sync.git_inspector import ChangedFile


class CandidateResolutionError(RuntimeError):
    """Raised when candidate resolution rules are invalid."""


@dataclass(frozen=True, slots=True)
class CandidateRule:
    rule_id: str
    source_patterns: tuple[str, ...]
    vault_candidates: tuple[str, ...]
    priority: str


@dataclass(frozen=True, slots=True)
class CandidateReason:
    rule_id: str
    source_path: str


@dataclass(frozen=True, slots=True)
class DocumentCandidate:
    path: str
    priority: str
    disposition: str
    reasons: tuple[CandidateReason, ...]


_ALLOWED_PRIORITIES = {
    "low",
    "medium",
    "high",
}

_ALLOWED_VAULT_PATHS = {
    "01-architecture/CURRENT_COMPONENTS_MAP.md",
    "02-current-baseline/CURRENT_BASELINE.md",
    "03-roadmap/IMPLEMENTATION_ROADMAP.md",
    "04-sprints/SPRINT_INDEX.md",
    "05-decisions/PENDING_DECISIONS.md",
    "07-audits/AUDIT_INDEX.md",
    "08-session-context/MALAK_SESSION_CONTEXT.md",
    "10-knowledge-index/KNOWLEDGE_INDEX.md",
}

_DENIED_VAULT_PATTERNS = (
    "09-snapshots/**",
    ".git/**",
    "var/**",
    "**/.env",
    "**/.env.*",
    "**/*secret*",
    "**/*credential*",
    "**/*.key",
    "**/*.pem",
    "**/*.pfx",
    "**/*.p12",
)

_DEFAULT_RULES = (
    CandidateRule(
        rule_id="baseline-source-change",
        source_patterns=(
            "README.md",
            "CHANGELOG.md",
            "ROADMAP.md",
            "documents/projects/jarvis/releases/**",
            "documents/projects/jarvis/sprints/**",
        ),
        vault_candidates=(
            "02-current-baseline/CURRENT_BASELINE.md",
            "08-session-context/MALAK_SESSION_CONTEXT.md",
            "03-roadmap/IMPLEMENTATION_ROADMAP.md",
        ),
        priority="high",
    ),
    CandidateRule(
        rule_id="architecture-change",
        source_patterns=(
            "src/malak/**",
            "documents/projects/jarvis/architecture/**",
        ),
        vault_candidates=(
            "01-architecture/CURRENT_COMPONENTS_MAP.md",
            "02-current-baseline/CURRENT_BASELINE.md",
            "08-session-context/MALAK_SESSION_CONTEXT.md",
        ),
        priority="high",
    ),
    CandidateRule(
        rule_id="test-change",
        source_patterns=(
            "tests/**",
            "pyproject.toml",
        ),
        vault_candidates=(
            "02-current-baseline/CURRENT_BASELINE.md",
            "08-session-context/MALAK_SESSION_CONTEXT.md",
        ),
        priority="medium",
    ),
    CandidateRule(
        rule_id="governance-change",
        source_patterns=(
            "documents/projects/jarvis/governance/**",
            "documents/projects/jarvis/decisions/**",
            "documents/projects/jarvis/adr/**",
        ),
        vault_candidates=(
            "03-roadmap/IMPLEMENTATION_ROADMAP.md",
            "05-decisions/PENDING_DECISIONS.md",
            "08-session-context/MALAK_SESSION_CONTEXT.md",
            "10-knowledge-index/KNOWLEDGE_INDEX.md",
        ),
        priority="high",
    ),
    CandidateRule(
        rule_id="security-change",
        source_patterns=(
            "SECURITY.md",
            "documents/projects/jarvis/security/**",
        ),
        vault_candidates=(
            "02-current-baseline/CURRENT_BASELINE.md",
            "07-audits/AUDIT_INDEX.md",
            "08-session-context/MALAK_SESSION_CONTEXT.md",
        ),
        priority="high",
    ),
)


def resolve_candidates(
    changed_files: tuple[ChangedFile, ...],
    *,
    rules: tuple[CandidateRule, ...] = _DEFAULT_RULES,
) -> tuple[DocumentCandidate, ...]:
    _validate_rules(rules)

    candidate_reasons: dict[str, list[CandidateReason]] = {}
    candidate_priorities: dict[str, str] = {}

    normalized_changes = tuple(
        sorted(
            (
                ChangedFile(
                    status=changed.status,
                    path=_normalize_source_path(changed.path),
                )
                for changed in changed_files
            ),
            key=lambda item: (
                item.path,
                item.status,
            ),
        )
    )

    for changed_file in normalized_changes:
        for rule in rules:
            if not _matches_any(
                changed_file.path,
                rule.source_patterns,
            ):
                continue

            for candidate_path in rule.vault_candidates:
                _validate_candidate_path(candidate_path)

                candidate_reasons.setdefault(
                    candidate_path,
                    [],
                ).append(
                    CandidateReason(
                        rule_id=rule.rule_id,
                        source_path=changed_file.path,
                    )
                )

                current_priority = candidate_priorities.get(
                    candidate_path
                )

                candidate_priorities[candidate_path] = (
                    _max_priority(
                        current_priority,
                        rule.priority,
                    )
                )

    candidates = [
        DocumentCandidate(
            path=path,
            priority=candidate_priorities[path],
            disposition="review_required",
            reasons=tuple(
                sorted(
                    set(reasons),
                    key=lambda reason: (
                        reason.rule_id,
                        reason.source_path,
                    ),
                )
            ),
        )
        for path, reasons in candidate_reasons.items()
    ]

    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                _priority_rank(candidate.priority),
                candidate.path,
            ),
            reverse=True,
        )
    )


def default_rules() -> tuple[CandidateRule, ...]:
    return _DEFAULT_RULES


def is_denied_vault_path(path: str) -> bool:
    normalized = _normalize_vault_path(path)

    return any(
        fnmatch(normalized, pattern)
        for pattern in _DENIED_VAULT_PATTERNS
    )


def is_allowed_vault_path(path: str) -> bool:
    normalized = _normalize_vault_path(path)

    return (
        normalized in _ALLOWED_VAULT_PATHS
        and not is_denied_vault_path(normalized)
    )


def _validate_rules(
    rules: tuple[CandidateRule, ...],
) -> None:
    seen_rule_ids: set[str] = set()

    for rule in rules:
        if not rule.rule_id.strip():
            raise CandidateResolutionError(
                "Rule ID must be non-empty."
            )

        if rule.rule_id in seen_rule_ids:
            raise CandidateResolutionError(
                f"Duplicate rule ID: {rule.rule_id}"
            )

        seen_rule_ids.add(rule.rule_id)

        if not rule.source_patterns:
            raise CandidateResolutionError(
                f"Rule has no source patterns: {rule.rule_id}"
            )

        if not rule.vault_candidates:
            raise CandidateResolutionError(
                f"Rule has no Vault candidates: {rule.rule_id}"
            )

        if rule.priority not in _ALLOWED_PRIORITIES:
            raise CandidateResolutionError(
                f"Unsupported priority: {rule.priority}"
            )

        for candidate_path in rule.vault_candidates:
            _validate_candidate_path(candidate_path)


def _validate_candidate_path(path: str) -> None:
    normalized = _normalize_vault_path(path)

    if is_denied_vault_path(normalized):
        raise CandidateResolutionError(
            f"Vault candidate path is denied: {normalized}"
        )

    if normalized not in _ALLOWED_VAULT_PATHS:
        raise CandidateResolutionError(
            f"Vault candidate path is not allowlisted: "
            f"{normalized}"
        )


def _normalize_source_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()

    if not normalized:
        raise CandidateResolutionError(
            "Changed source path must be non-empty."
        )

    pure_path = PurePosixPath(normalized)

    if pure_path.is_absolute():
        raise CandidateResolutionError(
            "Changed source path must be relative."
        )

    if ".." in pure_path.parts:
        raise CandidateResolutionError(
            "Changed source path cannot contain parent traversal."
        )

    return pure_path.as_posix()


def _normalize_vault_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()

    if not normalized:
        raise CandidateResolutionError(
            "Vault path must be non-empty."
        )

    pure_path = PurePosixPath(normalized)

    if pure_path.is_absolute():
        raise CandidateResolutionError(
            "Vault path must be relative."
        )

    if ".." in pure_path.parts:
        raise CandidateResolutionError(
            "Vault path cannot contain parent traversal."
        )

    return pure_path.as_posix()


def _matches_any(
    path: str,
    patterns: tuple[str, ...],
) -> bool:
    return any(
        fnmatch(path, pattern)
        for pattern in patterns
    )


def _max_priority(
    current: str | None,
    candidate: str,
) -> str:
    if current is None:
        return candidate

    if _priority_rank(candidate) > _priority_rank(current):
        return candidate

    return current


def _priority_rank(priority: str) -> int:
    ranks = {
        "low": 1,
        "medium": 2,
        "high": 3,
    }

    return ranks[priority]