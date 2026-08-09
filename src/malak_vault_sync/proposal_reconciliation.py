from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, replace

from malak_vault_sync.evidence import sanitize_text
from malak_vault_sync.execution_lock import (
    ExecutionLockError,
    execution_lock,
)
from malak_vault_sync.models import AgentConfig
from malak_vault_sync.state_store import (
    StateStoreError,
    SyncState,
    load_state,
    load_state_with_metadata,
    save_state,
)


class ProposalReconciliationError(RuntimeError):
    """Raised when a pending proposal cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class PullRequestSnapshot:
    url: str
    head_commit: str
    head_branch: str
    base_branch: str
    state: str
    merged_at: str | None


@dataclass(frozen=True, slots=True)
class RecoverableProposal:
    url: str
    head_commit: str
    branch: str
    source_commit: str
    state: str
    is_draft: bool
    merged_at: str | None


def discover_remote_proposal(
    config: AgentConfig,
    *,
    current_source_commit: str,
    reconciled_commit: str,
) -> RecoverableProposal | None:
    """Recover one agent-owned PR identity after local persistence failed."""

    _require_controlled_proposal_mode(config)
    assert config.proposal is not None

    normalized_current = _normalize_commit(
        current_source_commit,
        label="current source",
    )
    normalized_reconciled = _normalize_commit(
        reconciled_commit,
        label="reconciled",
    )
    command = [
        config.proposal.github_cli,
        "pr",
        "list",
        "--repo",
        config.vault.repository,
        "--state",
        "all",
        "--limit",
        "100",
        "--json",
        (
            "url,headRefOid,headRefName,baseRefName,baseRefOid,state,"
            "isDraft,mergedAt,body"
        ),
    ]

    try:
        completed = subprocess.run(
            command,
            cwd=config.vault.local_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.limits.command_timeout_seconds,
            check=False,
            shell=False,
        )
    except (FileNotFoundError, OSError) as exc:
        raise ProposalReconciliationError(
            f"Command could not be executed: {config.proposal.github_cli}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ProposalReconciliationError(
            f"Command timed out: {config.proposal.github_cli}"
        ) from exc

    if completed.returncode != 0:
        detail = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "unknown command error"
        )
        raise ProposalReconciliationError(
            "GitHub proposal recovery failed: "
            f"{sanitize_text(detail)}"
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ProposalReconciliationError(
            "GitHub CLI returned invalid proposal recovery metadata."
        ) from exc

    if not isinstance(payload, list):
        raise ProposalReconciliationError(
            "GitHub CLI returned invalid proposal recovery metadata."
        )
    if any(not isinstance(item, dict) for item in payload):
        raise ProposalReconciliationError(
            "GitHub CLI returned invalid proposal recovery metadata."
        )

    prefix = f"{config.proposal.branch_prefix}-"
    open_matching: list[dict[str, object]] = []
    historical_matching: list[dict[str, object]] = []

    for item in payload:
        head_branch = item.get("headRefName")
        body = item.get("body")
        state = item.get("state")
        is_draft = item.get("isDraft")

        if (
            not isinstance(head_branch, str)
            or not head_branch.startswith(prefix)
            or not isinstance(body, str)
            or not isinstance(state, str)
            or not isinstance(is_draft, bool)
        ):
            continue

        body = body.replace("\r\n", "\n").replace("\r", "\n")

        body_source = _body_commit(body, "Malāk HEAD")
        body_base = _body_commit(body, "Malāk base")
        is_open_draft = state.upper() == "OPEN" and is_draft
        is_current_source = body_source == normalized_current
        has_reconciled_base = body_base == normalized_reconciled

        if is_open_draft and (is_current_source or has_reconciled_base):
            open_matching.append(item)
        elif (
            has_reconciled_base
            and body_source is not None
            and body_source != body_base
        ):
            historical_matching.append(item)

    matching = open_matching or historical_matching

    if not matching:
        return None
    if len(matching) != 1:
        raise ProposalReconciliationError(
            "Remote proposal identity is ambiguous."
        )

    item = matching[0]
    url = item.get("url")
    head_commit = item.get("headRefOid")
    head_branch = item.get("headRefName")
    base_branch = item.get("baseRefName")
    base_commit = item.get("baseRefOid")
    state = item.get("state")
    is_draft = item.get("isDraft")
    merged_at = item.get("mergedAt")
    body = item.get("body")

    if (
        not isinstance(url, str)
        or not isinstance(head_commit, str)
        or not isinstance(head_branch, str)
        or not isinstance(base_branch, str)
        or not isinstance(base_commit, str)
        or not isinstance(state, str)
        or not isinstance(is_draft, bool)
        or (merged_at is not None and not isinstance(merged_at, str))
        or not isinstance(body, str)
    ):
        raise ProposalReconciliationError(
            "GitHub CLI returned incomplete proposal recovery metadata."
        )

    normalized_state = state.upper()
    expected_url_prefix = (
        "https://github.com/Aranwill/"
        "malak-project-vault/pull/"
    )
    normalized_head = head_commit.lower()
    normalized_vault_base = base_commit.lower()

    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body_source = _body_commit(body, "Malāk HEAD")
    body_reconciled = _body_commit(body, "Malāk base")
    body_vault_base = _body_commit(body, "Vault base")
    expected_branch = (
        f"{config.proposal.branch_prefix}-"
        f"{body_source[:8]}"
        if body_source is not None
        else ""
    )

    if (
        body_source is None
        or head_branch != expected_branch
        or base_branch != config.vault.branch
        or not url.startswith(expected_url_prefix)
        or len(normalized_head) != 40
        or any(
            character not in "0123456789abcdef"
            for character in normalized_head
        )
        or len(normalized_vault_base) != 40
        or any(
            character not in "0123456789abcdef"
            for character in normalized_vault_base
        )
        or body_vault_base != normalized_vault_base
        or (
            body_source != normalized_current
            and body_reconciled != normalized_reconciled
        )
        or normalized_state not in {"OPEN", "CLOSED", "MERGED"}
        or (normalized_state == "OPEN" and not is_draft)
        or (normalized_state == "MERGED" and merged_at is None)
        or (normalized_state == "CLOSED" and merged_at is not None)
    ):
        raise ProposalReconciliationError(
            "Remote proposal does not match the governed identity."
        )

    return RecoverableProposal(
        url=url,
        head_commit=normalized_head,
        branch=head_branch,
        source_commit=body_source,
        state=normalized_state,
        is_draft=is_draft,
        merged_at=merged_at,
    )


def _normalize_commit(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if (
        len(normalized) != 40
        or any(character not in "0123456789abcdef" for character in normalized)
    ):
        raise ProposalReconciliationError(
            f"Remote proposal recovery requires a full {label} commit SHA."
        )
    return normalized


def _body_commit(body: str, label: str) -> str | None:
    match = re.search(
        rf"^- {re.escape(label)}: `([0-9A-Fa-f]{{40}})`$",
        body,
        re.MULTILINE,
    )
    return match.group(1).lower() if match is not None else None


def reconcile_migrated_proposal(
    config: AgentConfig,
    *,
    decision: str,
    expected_base_commit: str,
    expected_commit: str,
    proposal_vault_commit: str,
    pull_request_url: str,
) -> None:
    """Resolve one v1/v2 proposal using explicit human-supplied identity."""

    if decision not in {"accept", "reject"}:
        raise ProposalReconciliationError(
            "Migrated proposal decision must be accept or reject."
        )

    _require_controlled_proposal_mode(config)
    lock_path = config.state.path.with_name("agent.lock")

    with execution_lock(lock_path):
        loaded = load_state_with_metadata(config.state.path)

        if loaded.source_schema_version not in {1, 2}:
            raise ProposalReconciliationError(
                "Migrated proposal reconciliation requires an original "
                "v1 or v2 state file."
            )

        try:
            identified_state = (
                loaded.state.with_migrated_proposal_identity(
                    expected_base_commit=expected_base_commit,
                    expected_commit=expected_commit,
                    vault_commit=proposal_vault_commit,
                    pull_request_url=pull_request_url,
                )
            )
        except StateStoreError as exc:
            raise ProposalReconciliationError(
                "The migrated proposal does not match the explicit "
                "range and identity."
            ) from exc

        pull_request = _inspect_expected_pull_request(
            config,
            identified_state,
        )

        if decision == "accept":
            if (
                pull_request.state != "MERGED"
                or pull_request.merged_at is None
            ):
                raise ProposalReconciliationError(
                    "The migrated proposal pull request is not merged."
                )

            next_state = identified_state.accept_pending_proposal(
                expected_commit=expected_commit,
            )
        else:
            if (
                pull_request.state != "CLOSED"
                or pull_request.merged_at is not None
            ):
                raise ProposalReconciliationError(
                    "The migrated proposal pull request is not closed "
                    "without merge."
                )

            rejected_state = identified_state.reject_pending_proposal(
                expected_commit=expected_commit,
            )
            next_state = replace(
                rejected_state,
                last_reconciled_commit=(
                    identified_state.pending_proposal_base_commit
                ),
            )

        save_state(config.state.path, next_state)


def accept_proposal(
    config: AgentConfig,
    *,
    expected_commit: str,
) -> None:
    """Accept a pending proposal only after its PR has been merged."""

    lock_path = config.state.path.with_name("agent.lock")

    with execution_lock(lock_path):
        state, next_state = _prepare_resolution(
            config,
            expected_commit=expected_commit,
            accept=True,
        )
        pull_request = _inspect_expected_pull_request(config, state)

        if (
            pull_request.state != "MERGED"
            or pull_request.merged_at is None
        ):
            raise ProposalReconciliationError(
                "The pending proposal pull request is not merged."
            )

        save_state(config.state.path, next_state)


def reject_proposal(
    config: AgentConfig,
    *,
    expected_commit: str,
) -> None:
    """Reject a pending proposal only after its PR closed unmerged."""

    lock_path = config.state.path.with_name("agent.lock")

    with execution_lock(lock_path):
        state, next_state = _prepare_resolution(
            config,
            expected_commit=expected_commit,
            accept=False,
        )
        pull_request = _inspect_expected_pull_request(config, state)

        if (
            pull_request.state != "CLOSED"
            or pull_request.merged_at is not None
        ):
            raise ProposalReconciliationError(
                "The pending proposal pull request is not closed without merge."
            )

        save_state(config.state.path, next_state)


def inspect_pull_request(
    *,
    url: str,
    repository: str,
    github_cli: str,
    cwd: object,
    timeout_seconds: int,
) -> PullRequestSnapshot:
    """Read the immutable identity and current state of one GitHub PR."""

    command = [
        github_cli,
        "pr",
        "view",
        url,
        "--repo",
        repository,
        "--json",
        "url,headRefOid,headRefName,baseRefName,state,mergedAt",
    ]

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except (FileNotFoundError, OSError) as exc:
        raise ProposalReconciliationError(
            f"Command could not be executed: {github_cli}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ProposalReconciliationError(
            f"Command timed out: {github_cli}"
        ) from exc

    if completed.returncode != 0:
        detail = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "unknown command error"
        )
        raise ProposalReconciliationError(
            f"GitHub pull request inspection failed: "
            f"{sanitize_text(detail)}"
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ProposalReconciliationError(
            "GitHub CLI returned invalid pull request metadata."
        ) from exc

    if not isinstance(payload, dict):
        raise ProposalReconciliationError(
            "GitHub CLI returned invalid pull request metadata."
        )

    snapshot_url = payload.get("url")
    head_commit = payload.get("headRefOid")
    head_branch = payload.get("headRefName")
    base_branch = payload.get("baseRefName")
    state = payload.get("state")
    merged_at = payload.get("mergedAt")

    if (
        not isinstance(snapshot_url, str)
        or not isinstance(head_commit, str)
        or not isinstance(head_branch, str)
        or not isinstance(base_branch, str)
        or not isinstance(state, str)
        or (merged_at is not None and not isinstance(merged_at, str))
    ):
        raise ProposalReconciliationError(
            "GitHub CLI returned incomplete pull request metadata."
        )

    return PullRequestSnapshot(
        url=snapshot_url,
        head_commit=head_commit.lower(),
        head_branch=head_branch,
        base_branch=base_branch,
        state=state.upper(),
        merged_at=merged_at,
    )


def _prepare_resolution(
    config: AgentConfig,
    *,
    expected_commit: str,
    accept: bool,
) -> tuple[SyncState, SyncState]:
    _require_controlled_proposal_mode(config)

    state = load_state(config.state.path)

    try:
        if accept:
            next_state = state.accept_pending_proposal(
                expected_commit=expected_commit,
            )
        else:
            next_state = state.reject_pending_proposal(
                expected_commit=expected_commit,
            )
    except StateStoreError as exc:
        raise ProposalReconciliationError(
            "The pending proposal does not match the expected commit."
        ) from exc

    if (
        state.pending_proposal_vault_commit is None
        or state.pending_proposal_pull_request_url is None
    ):
        raise ProposalReconciliationError(
            "The pending proposal identity is incomplete."
        )

    return state, next_state


def _require_controlled_proposal_mode(config: AgentConfig) -> None:
    if config.mode != "controlled-proposal" or config.proposal is None:
        raise ProposalReconciliationError(
            "Proposal reconciliation requires controlled-proposal mode."
        )


def _commit_is_ancestor(
    config: AgentConfig,
    *,
    ancestor: str,
    descendant: str,
) -> bool:
    command = [
        "git",
        "merge-base",
        "--is-ancestor",
        ancestor,
        descendant,
    ]

    try:
        completed = subprocess.run(
            command,
            cwd=config.vault.local_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.limits.command_timeout_seconds,
            check=False,
            shell=False,
        )
    except (FileNotFoundError, OSError) as exc:
        raise ProposalReconciliationError(
            "Git ancestry verification could not be executed."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ProposalReconciliationError(
            "Git ancestry verification timed out."
        ) from exc

    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False

    detail = (
        completed.stderr.strip()
        or completed.stdout.strip()
        or "unknown command error"
    )
    raise ProposalReconciliationError(
        "Git ancestry verification failed: "
        f"{sanitize_text(detail)}"
    )


def _inspect_expected_pull_request(
    config: AgentConfig,
    state: SyncState,
) -> PullRequestSnapshot:
    assert config.proposal is not None
    assert state.pending_proposal_vault_commit is not None
    assert state.pending_proposal_pull_request_url is not None

    pull_request = inspect_pull_request(
        url=state.pending_proposal_pull_request_url,
        repository=config.vault.repository,
        github_cli=config.proposal.github_cli,
        cwd=config.vault.local_path,
        timeout_seconds=config.limits.command_timeout_seconds,
    )

    if (
        pull_request.url != state.pending_proposal_pull_request_url
        or pull_request.base_branch != config.vault.branch
    ):
        raise ProposalReconciliationError(
            "The pull request identity does not match the pending proposal."
        )

    expected_branch = (
        f"{config.proposal.branch_prefix}-"
        f"{state.pending_proposal_commit[:8]}"
    )
    if pull_request.head_branch != expected_branch:
        raise ProposalReconciliationError(
            "The pull request identity does not match the pending proposal."
        )

    if pull_request.head_commit == state.pending_proposal_vault_commit:
        return pull_request

    if pull_request.state != "MERGED" or pull_request.merged_at is None:
        raise ProposalReconciliationError(
            "The pull request identity does not match the pending proposal."
        )

    if not _commit_is_ancestor(
        config,
        ancestor=state.pending_proposal_vault_commit,
        descendant=pull_request.head_commit,
    ):
        raise ProposalReconciliationError(
            "The pull request identity does not match the pending proposal."
        )

    return pull_request
