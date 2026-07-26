from pathlib import Path
import subprocess

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
    _write_audit_report,
    prepare_vault_proposal,
    SourceProjection,
)
import malak_vault_sync.vault_writer as writer_module


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
    audit_index.write_text("# Auditorías\n", encoding="utf-8")
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
        f"main..{proposal.branch}",
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
