from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from malak_vault_sync.git_inspector import (
    GitInspectionError,
    get_current_branch,
    get_head,
    get_origin_url,
    inspect_repository,
    is_worktree_clean,
    list_changed_files,
    run_git_read_only,
    validate_git_repository,
)


def run_git(
    repository_path: Path,
    *args: str,
) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repository_path),
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        shell=False,
    )

    return completed.stdout.strip()


@pytest.fixture
def git_repository(tmp_path: Path) -> Path:
    repository_path = tmp_path / "repository"
    repository_path.mkdir()

    run_git(repository_path, "init", "-b", "main")
    run_git(repository_path, "config", "user.name", "Test User")
    run_git(
        repository_path,
        "config",
        "user.email",
        "test@example.com",
    )

    file_path = repository_path / "example.txt"
    file_path.write_text("first\n", encoding="utf-8")

    run_git(repository_path, "add", "example.txt")
    run_git(repository_path, "commit", "-m", "initial commit")

    return repository_path


def test_validate_git_repository_accepts_root(
    git_repository: Path,
) -> None:
    result = validate_git_repository(git_repository)

    assert result == git_repository.resolve()


def test_validate_git_repository_rejects_subdirectory(
    git_repository: Path,
) -> None:
    subdirectory = git_repository / "nested"
    subdirectory.mkdir()

    with pytest.raises(
        GitInspectionError,
        match="repository root",
    ):
        validate_git_repository(subdirectory)


def test_get_current_branch_returns_main(
    git_repository: Path,
) -> None:
    assert get_current_branch(git_repository) == "main"


def test_get_head_returns_commit_sha(
    git_repository: Path,
) -> None:
    head = get_head(git_repository)

    assert len(head) == 40
    assert all(character in "0123456789abcdef" for character in head)


def test_get_origin_url_returns_configured_remote(
    git_repository: Path,
) -> None:
    run_git(
        git_repository,
        "remote",
        "add",
        "origin",
        "https://example.com/repository.git",
    )

    assert (
        get_origin_url(git_repository)
        == "https://example.com/repository.git"
    )


def test_is_worktree_clean_detects_changes(
    git_repository: Path,
) -> None:
    assert is_worktree_clean(git_repository) is True

    file_path = git_repository / "example.txt"
    file_path.write_text("changed\n", encoding="utf-8")

    assert is_worktree_clean(git_repository) is False


def test_list_changed_files_returns_name_status(
    git_repository: Path,
) -> None:
    base_ref = get_head(git_repository)

    file_path = git_repository / "second.txt"
    file_path.write_text("second\n", encoding="utf-8")

    run_git(git_repository, "add", "second.txt")
    run_git(git_repository, "commit", "-m", "add second file")

    head_ref = get_head(git_repository)

    changed_files = list_changed_files(
        git_repository,
        base_ref,
        head_ref,
    )

    assert len(changed_files) == 1
    assert changed_files[0].status == "A"
    assert changed_files[0].path == "second.txt"


def test_list_changed_files_returns_empty_tuple(
    git_repository: Path,
) -> None:
    head = get_head(git_repository)

    assert list_changed_files(
        git_repository,
        head,
        head,
    ) == ()


def test_disallowed_command_is_rejected(
    git_repository: Path,
) -> None:
    with pytest.raises(
        GitInspectionError,
        match="not allowed",
    ):
        run_git_read_only(
            git_repository,
            "commit",
            "-m",
            "forbidden",
        )


def test_missing_git_command_is_rejected(
    git_repository: Path,
) -> None:
    with pytest.raises(
        GitInspectionError,
        match="required",
    ):
        run_git_read_only(git_repository)


def test_inspect_repository_returns_snapshot(
    git_repository: Path,
) -> None:
    head = get_head(git_repository)

    run_git(
        git_repository,
        "remote",
        "add",
        "origin",
        str(git_repository),
    )

    run_git(
        git_repository,
        "update-ref",
        "refs/remotes/origin/main",
        head,
    )

    snapshot = inspect_repository(git_repository)

    assert snapshot.repository_path == git_repository.resolve()
    assert snapshot.branch == "main"
    assert snapshot.head == head
    assert snapshot.remote_head == head
    assert snapshot.origin_url == str(git_repository)
    assert snapshot.is_clean is True