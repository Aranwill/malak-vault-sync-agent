from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitInspectionError(RuntimeError):
    """Raised when a read-only Git inspection command fails."""


@dataclass(frozen=True, slots=True)
class GitCommandResult:
    args: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True, slots=True)
class ChangedFile:
    status: str
    path: str


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    repository_path: Path
    branch: str
    head: str
    remote_head: str
    origin_url: str
    is_clean: bool


_ALLOWED_COMMANDS = {
    "rev-parse",
    "branch",
    "status",
    "remote",
    "diff",
}


def run_git_read_only(
    repository_path: str | Path,
    *git_args: str,
    timeout_seconds: int = 60,
) -> GitCommandResult:
    repo_path = Path(repository_path).resolve()

    if not git_args:
        raise GitInspectionError("A Git command is required.")

    command_name = git_args[0]

    if command_name not in _ALLOWED_COMMANDS:
        raise GitInspectionError(
            f"Git command is not allowed in Gate 2: {command_name}"
        )

    command = [
        "git",
        "-C",
        str(repo_path),
        *git_args,
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise GitInspectionError(
            "Git executable was not found."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GitInspectionError(
            f"Git command timed out after {timeout_seconds} seconds."
        ) from exc
    except OSError as exc:
        raise GitInspectionError(
            "Git command could not be executed."
        ) from exc

    result = GitCommandResult(
        args=tuple(git_args),
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
        returncode=completed.returncode,
    )

    if result.returncode != 0:
        detail = result.stderr or result.stdout or "unknown Git error"
        raise GitInspectionError(
            f"Git command failed: {detail}"
        )

    return result


def validate_git_repository(
    repository_path: str | Path,
) -> Path:
    repo_path = Path(repository_path).resolve()

    result = run_git_read_only(
        repo_path,
        "rev-parse",
        "--show-toplevel",
    )

    top_level = Path(result.stdout).resolve()

    if top_level != repo_path:
        raise GitInspectionError(
            "Configured path must be the repository root."
        )

    return repo_path


def get_current_branch(
    repository_path: str | Path,
) -> str:
    result = run_git_read_only(
        repository_path,
        "branch",
        "--show-current",
    )

    if not result.stdout:
        raise GitInspectionError(
            "Repository is in detached HEAD state."
        )

    return result.stdout


def get_head(
    repository_path: str | Path,
    ref: str = "HEAD",
) -> str:
    result = run_git_read_only(
        repository_path,
        "rev-parse",
        ref,
    )

    return result.stdout


def get_origin_url(
    repository_path: str | Path,
) -> str:
    result = run_git_read_only(
        repository_path,
        "remote",
        "get-url",
        "origin",
    )

    return result.stdout


def is_worktree_clean(
    repository_path: str | Path,
) -> bool:
    result = run_git_read_only(
        repository_path,
        "status",
        "--short",
    )

    return result.stdout == ""


def list_changed_files(
    repository_path: str | Path,
    base_ref: str,
    head_ref: str,
) -> tuple[ChangedFile, ...]:
    result = run_git_read_only(
        repository_path,
        "diff",
        "--name-status",
        f"{base_ref}..{head_ref}",
    )

    if not result.stdout:
        return ()

    changed_files: list[ChangedFile] = []

    for line in result.stdout.splitlines():
        parts = line.split("\t", maxsplit=1)

        if len(parts) != 2:
            raise GitInspectionError(
                f"Unexpected git diff output: {line}"
            )

        status, path = parts

        changed_files.append(
            ChangedFile(
                status=status,
                path=path,
            )
        )

    return tuple(changed_files)


def inspect_repository(
    repository_path: str | Path,
    remote_ref: str = "origin/main",
) -> RepositorySnapshot:
    repo_path = validate_git_repository(repository_path)

    return RepositorySnapshot(
        repository_path=repo_path,
        branch=get_current_branch(repo_path),
        head=get_head(repo_path),
        remote_head=get_head(repo_path, remote_ref),
        origin_url=get_origin_url(repo_path),
        is_clean=is_worktree_clean(repo_path),
    )