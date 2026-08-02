from pathlib import Path
import subprocess

import pytest

from malak_vault_sync.audit import (
    EvidenceReference,
    build_audit_report,
)
from malak_vault_sync.candidate_resolver import (
    CandidateReason,
    DocumentCandidate,
)
from malak_vault_sync.evidence import (
    CommitRange,
    EvidenceManifest,
    ExecutionMetadata,
)
from malak_vault_sync.git_inspector import (
    ChangedFile,
    RepositorySnapshot,
)
from malak_vault_sync.vault_writer import (
    _MANAGED_END,
    _MANAGED_START,
    _render_projection,
    _sprint_record_sort_key,
    _upsert_managed_block,
    _validate_written_projections,
    _write_audit_report,
    prepare_vault_proposal,
    synchronize_vault_checkout,
    SourceProjection,
    VaultProposalError,
)
import malak_vault_sync.vault_writer as writer_module


def test_final_projection_validation_accepts_valid_document(
    tmp_path: Path,
) -> None:
    target = tmp_path / "08-session-context" / "MALAK_SESSION_CONTEXT.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Context\n", encoding="utf-8")
    baseline = tmp_path / "02-current-baseline" / "CURRENT_BASELINE.md"
    baseline.parent.mkdir(parents=True)
    baseline.write_text(
        "---\ntitle: Baseline\n---\n\n"
        "[[08-session-context/MALAK_SESSION_CONTEXT|Context]]\n",
        encoding="utf-8",
    )

    _validate_written_projections(
        tmp_path,
        ("02-current-baseline/CURRENT_BASELINE.md",),
    )


def test_final_projection_validation_rejects_generated_invalid_content(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "02-current-baseline" / "CURRENT_BASELINE.md"
    baseline.parent.mkdir(parents=True)
    baseline.write_text(
        "---\ntitle: [broken\n---\n\n[[missing/document]]\n",
        encoding="utf-8",
    )

    with pytest.raises(
        VaultProposalError,
        match="failed final validation",
    ):
        _validate_written_projections(
            tmp_path,
            ("02-current-baseline/CURRENT_BASELINE.md",),
        )


def _evidence(tmp_path: Path) -> EvidenceManifest:
    source = RepositorySnapshot(
        repository_path=tmp_path / "jarvis",
        branch="main",
        head="a" * 40,
        remote_head="b" * 40,
        origin_url="https://github.com/Aranwill/jarvis.git",
        is_clean=True,
    )
    vault = RepositorySnapshot(
        repository_path=tmp_path / "vault",
        branch="main",
        head="c" * 40,
        remote_head="c" * 40,
        origin_url=(
            "https://github.com/Aranwill/"
            "malak-project-vault.git"
        ),
        is_clean=True,
    )
    return EvidenceManifest(
        schema_version=1,
        execution=ExecutionMetadata(
            run_id=(
                "20260726T120000123456Z_"
                "bbbbbbbb_cccccccc"
            ),
            generated_at="2026-07-26T12:00:00+00:00",
            python_version="3.12.10",
            platform="test",
            mode="controlled-proposal",
        ),
        source_snapshot=source,
        vault_snapshot=vault,
        commit_range=CommitRange(
            base_commit="a" * 40,
            head_commit="b" * 40,
        ),
        changed_files=(
            ChangedFile(status="M", path="README.md"),
        ),
    )


def _candidate() -> DocumentCandidate:
    return DocumentCandidate(
        path="02-current-baseline/CURRENT_BASELINE.md",
        priority="high",
        disposition="review_required",
        reasons=(
            CandidateReason(
                rule_id="baseline-source-change",
                source_path="README.md",
            ),
        ),
    )


def test_managed_projection_is_replaced_not_duplicated(
    tmp_path: Path,
) -> None:
    evidence = _evidence(tmp_path)
    candidate = _candidate()
    original = "---\ntitle: Baseline\n---\n\n# Baseline\n\nTexto.\n"
    first = _upsert_managed_block(
        original,
        _render_projection(evidence, candidate),
    )
    second = _upsert_managed_block(
        first,
        _render_projection(evidence, candidate),
    )

    assert first == second
    assert second.count(_MANAGED_START) == 1
    assert second.count(_MANAGED_END) == 1
    assert evidence.commit_range.head_commit in second


def test_active_sprint_precedes_higher_future_draft() -> None:
    active = (
        "docs/project/sprints/SPRINT-7.4.md",
        "Sprint 7.4",
        "en progreso",
        "a" * 40,
    )
    future_draft = (
        "docs/project/sprints/SPRINT-7.7.md",
        "Sprint 7.7",
        "borrador preliminar",
        "b" * 40,
    )

    assert _sprint_record_sort_key(active) > _sprint_record_sort_key(
        future_draft
    )


def test_audit_report_references_prior_content_commit(
    tmp_path: Path,
) -> None:
    evidence = _evidence(tmp_path)
    candidate = _candidate()
    report = build_audit_report(
        evidence=evidence,
        evidence_reference=EvidenceReference(
            path="var/evidence/run",
            sha256="d" * 64,
        ),
        candidates=(candidate,),
        findings=(),
    )
    worktree = tmp_path / "vault"
    worktree.mkdir()
    content_commit = "e" * 40

    report_path = _write_audit_report(
        worktree,
        evidence=evidence,
        report=report,
        candidates=(candidate,),
        branch="agent/vault-sync-bbbbbbbb",
        content_commit=content_commit,
        modified_paths=(candidate.path,),
    )
    content = (worktree / report_path).read_text(encoding="utf-8")

    assert f"vault_content_commit: {content_commit}" in content
    assert f"Commit de contenido: `{content_commit}`" in content
    assert "human_review_required: true" in content
    assert "merge_allowed: false" in content
    assert "agent_version: 0.3.0" in content
    assert "triggered_by: manual-on-demand" in content


def test_synchronize_vault_checkout_fast_forwards_clean_main(
    tmp_path: Path,
) -> None:
    remote = tmp_path / "vault.git"
    seed = tmp_path / "seed"
    vault = tmp_path / "vault"
    publisher = tmp_path / "publisher"

    _run("git", "init", "--bare", str(remote), cwd=tmp_path)
    _run("git", "init", "-b", "main", str(seed), cwd=tmp_path)
    _configure_identity(seed)
    (seed / "README.md").write_text("base\n", encoding="utf-8")
    _run("git", "add", "README.md", cwd=seed)
    _run("git", "commit", "-m", "base", cwd=seed)
    _run("git", "remote", "add", "origin", str(remote), cwd=seed)
    _run("git", "push", "-u", "origin", "main", cwd=seed)
    _run(
        "git",
        "symbolic-ref",
        "HEAD",
        "refs/heads/main",
        cwd=remote,
    )

    _run("git", "clone", str(remote), str(vault), cwd=tmp_path)
    _run("git", "clone", str(remote), str(publisher), cwd=tmp_path)
    _configure_identity(publisher)
    (publisher / "README.md").write_text(
        "base\nupdated\n",
        encoding="utf-8",
    )
    _run("git", "add", "README.md", cwd=publisher)
    _run("git", "commit", "-m", "update", cwd=publisher)
    _run("git", "push", "origin", "main", cwd=publisher)
    expected_head = _run("git", "rev-parse", "HEAD", cwd=publisher)
    _run("git", "fetch", "origin", "main", cwd=vault)

    assert _run("git", "rev-parse", "HEAD", cwd=vault) != expected_head

    synchronize_vault_checkout(
        vault,
        remote="origin",
        base_branch="main",
        expected_remote_head=expected_head,
        timeout_seconds=30,
    )

    assert _run("git", "rev-parse", "HEAD", cwd=vault) == expected_head
    assert _run("git", "status", "--short", cwd=vault) == ""
    assert _run("git", "branch", "--show-current", cwd=vault) == "main"


def test_prepare_proposal_commits_content_before_audit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    remote = tmp_path / "vault.git"
    _run("git", "init", "-b", "main", str(vault), cwd=tmp_path)
    _run("git", "init", "--bare", str(remote), cwd=tmp_path)
    _run("git", "config", "user.name", "Test", cwd=vault)
    _run(
        "git",
        "config",
        "user.email",
        "test@example.com",
        cwd=vault,
    )
    baseline = vault / "02-current-baseline" / "CURRENT_BASELINE.md"
    baseline.parent.mkdir(parents=True)
    baseline.write_text(
        "---\ntitle: Baseline\n---\n\n# Baseline\n\nPrevio.\n",
        encoding="utf-8",
    )
    audit_index = vault / "07-audits" / "AUDIT_INDEX.md"
    audit_index.parent.mkdir(parents=True)
    audit_index.write_text(
        "---\ntitle: Auditorías\n---\n\n# Auditorías\n",
        encoding="utf-8",
    )
    _run("git", "add", ".", cwd=vault)
    _run("git", "commit", "-m", "baseline", cwd=vault)
    _run("git", "remote", "add", "origin", str(remote), cwd=vault)
    _run("git", "push", "-u", "origin", "main", cwd=vault)
    vault_head = _run(
        "git",
        "rev-parse",
        "HEAD",
        cwd=vault,
    )

    evidence = _evidence(tmp_path)
    evidence = EvidenceManifest(
        schema_version=evidence.schema_version,
        execution=evidence.execution,
        source_snapshot=evidence.source_snapshot,
        vault_snapshot=RepositorySnapshot(
            repository_path=vault,
            branch="main",
            head=vault_head,
            remote_head=vault_head,
            origin_url=str(remote),
            is_clean=True,
        ),
        commit_range=evidence.commit_range,
        changed_files=evidence.changed_files,
    )
    candidate = _candidate()
    report = build_audit_report(
        evidence=evidence,
        evidence_reference=EvidenceReference(
            path="var/evidence/run",
            sha256="d" * 64,
        ),
        candidates=(candidate,),
        findings=(),
    )
    monkeypatch.setattr(
        writer_module,
        "_preflight_github_cli",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        writer_module,
        "_collect_source_projection",
        lambda *args, **kwargs: SourceProjection(
            sprint_document=None,
            sprint_title=None,
            sprint_status=None,
            sprint_as_of_commit=None,
            commit_summaries=(),
        ),
    )
    monkeypatch.setattr(
        writer_module,
        "_verify_source_and_vault_heads",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        writer_module,
        "_open_draft_pr",
        lambda *args, **kwargs: "https://github.com/example/pr/1",
    )
    validation_calls: list[tuple[str, ...]] = []
    original_validator = writer_module._validate_written_projections

    def record_validation(
        worktree: Path,
        modified_paths: tuple[str, ...],
    ) -> None:
        validation_calls.append(modified_paths)
        original_validator(worktree, modified_paths)

    monkeypatch.setattr(
        writer_module,
        "_validate_written_projections",
        record_validation,
    )

    proposal = prepare_vault_proposal(
        vault_root=vault,
        evidence=evidence,
        candidates=(candidate,),
        report=report,
        remote="origin",
        base_branch="main",
        branch_prefix="agent/vault-sync",
        github_cli="gh",
        timeout_seconds=30,
    )

    assert _run(
        "git",
        "rev-list",
        "--count",
        f"main..{proposal.audit_commit}",
        cwd=vault,
    ) == "2"
    assert _run(
        "git",
        "rev-parse",
        f"{proposal.audit_commit}^",
        cwd=vault,
    ) == proposal.content_commit
    report_content = _run(
        "git",
        "show",
        f"{proposal.audit_commit}:{proposal.report_path}",
        cwd=vault,
    )
    assert proposal.content_commit in report_content
    assert proposal.pull_request_url.endswith("/1")
    assert validation_calls == [
        (candidate.path,),
        (
            proposal.report_path,
            "07-audits/AUDIT_INDEX.md",
        ),
    ]
    assert _run(
        "git",
        "branch",
        "--list",
        proposal.branch,
        cwd=vault,
    ) == ""


def test_prepare_proposal_rolls_back_branch_when_pr_creation_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    remote = tmp_path / "vault.git"
    _run("git", "init", "-b", "main", str(vault), cwd=tmp_path)
    _run("git", "init", "--bare", str(remote), cwd=tmp_path)
    _configure_identity(vault)
    baseline = vault / "02-current-baseline" / "CURRENT_BASELINE.md"
    baseline.parent.mkdir(parents=True)
    baseline.write_text(
        "---\ntitle: Baseline\n---\n\n# Baseline\n\nPrevio.\n",
        encoding="utf-8",
    )
    audit_index = vault / "07-audits" / "AUDIT_INDEX.md"
    audit_index.parent.mkdir(parents=True)
    audit_index.write_text(
        "---\ntitle: Auditorías\n---\n\n# Auditorías\n",
        encoding="utf-8",
    )
    _run("git", "add", ".", cwd=vault)
    _run("git", "commit", "-m", "baseline", cwd=vault)
    _run("git", "remote", "add", "origin", str(remote), cwd=vault)
    _run("git", "push", "-u", "origin", "main", cwd=vault)
    vault_head = _run("git", "rev-parse", "HEAD", cwd=vault)

    evidence = _evidence(tmp_path)
    evidence = EvidenceManifest(
        schema_version=evidence.schema_version,
        execution=evidence.execution,
        source_snapshot=evidence.source_snapshot,
        vault_snapshot=RepositorySnapshot(
            repository_path=vault,
            branch="main",
            head=vault_head,
            remote_head=vault_head,
            origin_url=str(remote),
            is_clean=True,
        ),
        commit_range=evidence.commit_range,
        changed_files=evidence.changed_files,
    )
    candidate = _candidate()
    report = build_audit_report(
        evidence=evidence,
        evidence_reference=EvidenceReference(
            path="var/evidence/run",
            sha256="d" * 64,
        ),
        candidates=(candidate,),
        findings=(),
    )
    monkeypatch.setattr(
        writer_module,
        "_preflight_github_cli",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        writer_module,
        "_collect_source_projection",
        lambda *args, **kwargs: SourceProjection(
            sprint_document=None,
            sprint_title=None,
            sprint_status=None,
            sprint_as_of_commit=None,
            commit_summaries=(),
        ),
    )
    monkeypatch.setattr(
        writer_module,
        "_verify_source_and_vault_heads",
        lambda *args, **kwargs: None,
    )

    def fail_pr_creation(*args, **kwargs):
        raise VaultProposalError("simulated gh failure")

    monkeypatch.setattr(
        writer_module,
        "_open_draft_pr",
        fail_pr_creation,
    )
    branch = "agent/vault-sync-bbbbbbbb"

    with pytest.raises(
        VaultProposalError,
        match="published proposal branch was rolled back",
    ):
        prepare_vault_proposal(
            vault_root=vault,
            evidence=evidence,
            candidates=(candidate,),
            report=report,
            remote="origin",
            base_branch="main",
            branch_prefix="agent/vault-sync",
            github_cli="gh",
            timeout_seconds=30,
        )

    assert _run(
        "git",
        "ls-remote",
        "--heads",
        "origin",
        f"refs/heads/{branch}",
        cwd=vault,
    ) == ""
    assert _run("git", "branch", "--list", branch, cwd=vault) == ""


def _configure_identity(repository: Path) -> None:
    _run("git", "config", "user.name", "Test", cwd=repository)
    _run(
        "git",
        "config",
        "user.email",
        "test@example.com",
        cwd=repository,
    )


def _run(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return completed.stdout.strip()
