from pathlib import Path

import pytest

import malak_vault_sync.runner as runner_module
from malak_vault_sync.audit import AuditConclusion
from malak_vault_sync.audit_store import (
    AuditArtifact,
    AuditArtifacts,
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
from malak_vault_sync.models import (
    AgentConfig,
    LimitsConfig,
    OutputConfig,
    SecurityConfig,
    SourceConfig,
    StateConfig,
    VaultConfig,
)
from malak_vault_sync.runner import RunnerError, run_once
from malak_vault_sync.state_store import SyncState


SOURCE_HEAD = "a" * 40
BASE_COMMIT = "b" * 40
VAULT_HEAD = "c" * 40
RUN_ID = "20260722T120000Z-aaaaaaaa-bbbbbbbb"


def _make_config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(
        schema_version=1,
        mode="dry-run",
        source=SourceConfig(
            repository="Aranwill/jarvis",
            local_path=tmp_path / "jarvis",
            remote="origin",
            branch="main",
            fetch=False,
        ),
        vault=VaultConfig(
            repository="Aranwill/malak-project-vault",
            local_path=tmp_path / "vault",
            branch="main",
        ),
        state=StateConfig(
            path=tmp_path / "state" / "sync-state.json",
        ),
        output=OutputConfig(
            evidence_dir=tmp_path / "evidence",
            report_dir=tmp_path / "reports",
        ),
        limits=LimitsConfig(
            max_changed_files=200,
            max_evidence_bytes=10485760,
            max_file_bytes=1048576,
            command_timeout_seconds=60,
        ),
        security=SecurityConfig(
            require_clean_source_worktree=True,
            require_clean_vault_worktree=True,
            follow_symlinks=False,
            include_file_contents=False,
        ),
    )


def _make_snapshot(
    path: Path,
    *,
    head: str,
    is_clean: bool = True,
) -> RepositorySnapshot:
    return RepositorySnapshot(
        repository_path=path,
        branch="main",
        head=head,
        remote_head=head,
        origin_url="https://github.com/Aranwill/repository.git",
        is_clean=is_clean,
    )


def _make_manifest(
    source_snapshot: RepositorySnapshot,
    vault_snapshot: RepositorySnapshot,
    base_commit: str,
    head_commit: str,
    changed_files: tuple[ChangedFile, ...],
) -> EvidenceManifest:
    return EvidenceManifest(
        schema_version=1,
        execution=ExecutionMetadata(
            run_id=RUN_ID,
            generated_at="2026-07-22T12:00:00Z",
            python_version="3.12.0",
            platform="win32",
            mode="dry-run",
        ),
        source_snapshot=source_snapshot,
        vault_snapshot=vault_snapshot,
        commit_range=CommitRange(
            base_commit=base_commit,
            head_commit=head_commit,
        ),
        changed_files=changed_files,
    )


def _install_common_stubs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    state: SyncState,
    source_clean: bool = True,
) -> None:
    config = _make_config(tmp_path)

    source_snapshot = _make_snapshot(
        config.source.local_path,
        head=SOURCE_HEAD,
        is_clean=source_clean,
    )
    vault_snapshot = _make_snapshot(
        config.vault.local_path,
        head=VAULT_HEAD,
    )

    monkeypatch.setattr(
        runner_module,
        "load_state",
        lambda path: state,
    )

    def fake_inspect_repository(
        repository_path: Path,
        *,
        remote_ref: str,
    ) -> RepositorySnapshot:
        del remote_ref

        if repository_path == config.source.local_path:
            return source_snapshot

        return vault_snapshot

    monkeypatch.setattr(
        runner_module,
        "inspect_repository",
        fake_inspect_repository,
    )

    monkeypatch.setattr(
        runner_module,
        "build_manifest",
        lambda **kwargs: _make_manifest(**kwargs),
    )

    evidence_directory = tmp_path / "evidence" / RUN_ID
    evidence_directory.mkdir(parents=True)
    hashes_path = evidence_directory / "hashes.sha256"
    hashes_path.write_text(
        "evidence hashes\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        runner_module,
        "write_evidence_package",
        lambda output_root, manifest: evidence_directory,
    )
    monkeypatch.setattr(
        runner_module,
        "sha256_file",
        lambda path: "d" * 64,
    )
    monkeypatch.setattr(
        runner_module,
        "resolve_candidates",
        lambda changed_files: (),
    )

    audit_directory = tmp_path / "reports" / RUN_ID

    monkeypatch.setattr(
        runner_module,
        "write_audit_report_package",
        lambda output_root, report: AuditArtifacts(
            directory=audit_directory,
            json=AuditArtifact(
                filename="audit-report.json",
                sha256="e" * 64,
            ),
            markdown=AuditArtifact(
                filename="audit-report.md",
                sha256="f" * 64,
            ),
            hashes=AuditArtifact(
                filename="hashes.sha256",
                sha256="1" * 64,
            ),
        ),
    )


def test_run_once_bootstraps_without_changed_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)

    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError(
            "list_changed_files must not run during bootstrap."
        )

    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        fail_if_called,
    )

    result = run_once(config)

    assert result.bootstrap is True
    assert result.base_commit == SOURCE_HEAD
    assert result.head_commit == SOURCE_HEAD
    assert result.changed_files == ()
    assert result.conclusion is AuditConclusion.PASS


def test_run_once_compares_from_last_observed_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)

    state = SyncState.initial().with_successful_observation(
        observed_commit=BASE_COMMIT,
        vault_commit=VAULT_HEAD,
        run_id="previous-run",
    )

    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=state,
    )

    changed_files = (
        ChangedFile(
            status="M",
            path="README.md",
        ),
    )

    calls: list[tuple[Path, str, str]] = []

    def fake_list_changed_files(
        repository_path: Path,
        base_ref: str,
        head_ref: str,
    ) -> tuple[ChangedFile, ...]:
        calls.append(
            (
                repository_path,
                base_ref,
                head_ref,
            )
        )
        return changed_files

    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        fake_list_changed_files,
    )

    result = run_once(config)

    assert result.bootstrap is False
    assert result.base_commit == BASE_COMMIT
    assert result.head_commit == SOURCE_HEAD
    assert result.changed_files == changed_files
    assert calls == [
        (
            config.source.local_path,
            BASE_COMMIT,
            SOURCE_HEAD,
        ),
    ]


def test_run_once_rejects_dirty_source_worktree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)

    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=SyncState.initial(),
        source_clean=False,
    )

    with pytest.raises(
        RunnerError,
        match="Source working tree must be clean",
    ):
        run_once(config)


def test_run_once_rejects_changed_file_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_config(tmp_path)

    state = SyncState.initial().with_successful_observation(
        observed_commit=BASE_COMMIT,
        vault_commit=VAULT_HEAD,
        run_id="previous-run",
    )

    _install_common_stubs(
        monkeypatch,
        tmp_path,
        state=state,
    )

    changed_files = tuple(
        ChangedFile(
            status="M",
            path=f"file-{index}.md",
        )
        for index in range(
            config.limits.max_changed_files + 1
        )
    )

    monkeypatch.setattr(
        runner_module,
        "list_changed_files",
        lambda repository_path, base_ref, head_ref: changed_files,
    )

    with pytest.raises(
        RunnerError,
        match="Changed file limit exceeded",
    ):
        run_once(config)
