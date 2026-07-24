from __future__ import annotations

import re
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
    previous_path: str | None = None


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    repository_path: Path
    branch: str
    head: str
    remote_head: str
    origin_url: str
    is_clean: bool


_SAFE_REF_PATTERN = re.compile(
    r"^(?:[0-9a-f]{40}|[A-Za-z0-9][A-Za-z0-9._/-]*)$"
)
_SAFE_REMOTE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_FETCH_REFSPEC_PATTERN = re.compile(
    r"^\+refs/heads/(?P<branch>[A-Za-z0-9][A-Za-z0-9._/-]*):"
    r"refs/remotes/(?P<remote>[A-Za-z0-9][A-Za-z0-9._-]*)/"
    r"(?P=branch)$"
)
_GITHUB_ORIGIN_PATTERN = re.compile(
    r"^(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)"
    r"(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def run_git_read_only(
    repository_path: str | Path,
    *git_args: str,
    timeout_seconds: int = 60,
) -> GitCommandResult:
    repo_path = Path(repository_path).resolve()

    if not git_args:
        raise GitInspectionError("A Git command is required.")

    _validate_git_arguments(git_args)

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
    *,
    timeout_seconds: int = 60,
) -> Path:
    repo_path = Path(repository_path).resolve()

    result = run_git_read_only(
        repo_path,
        "rev-parse",
        "--show-toplevel",
        timeout_seconds=timeout_seconds,
    )

    top_level = Path(result.stdout).resolve()

    if top_level != repo_path:
        raise GitInspectionError(
            "Configured path must be the repository root."
        )

    return repo_path


def get_current_branch(
    repository_path: str | Path,
    *,
    timeout_seconds: int = 60,
) -> str:
    result = run_git_read_only(
        repository_path,
        "branch",
        "--show-current",
        timeout_seconds=timeout_seconds,
    )

    if not result.stdout:
        raise GitInspectionError(
            "Repository is in detached HEAD state."
        )

    return result.stdout


def get_head(
    repository_path: str | Path,
    ref: str = "HEAD",
    *,
    timeout_seconds: int = 60,
) -> str:
    result = run_git_read_only(
        repository_path,
        "rev-parse",
        ref,
        timeout_seconds=timeout_seconds,
    )

    return result.stdout


def get_origin_url(
    repository_path: str | Path,
    *,
    timeout_seconds: int = 60,
) -> str:
    result = run_git_read_only(
        repository_path,
        "remote",
        "get-url",
        "origin",
        timeout_seconds=timeout_seconds,
    )

    return result.stdout


def is_worktree_clean(
    repository_path: str | Path,
    *,
    timeout_seconds: int = 60,
) -> bool:
    result = run_git_read_only(
        repository_path,
        "status",
        "--short",
        timeout_seconds=timeout_seconds,
    )

    return result.stdout == ""


def list_changed_files(
    repository_path: str | Path,
    base_ref: str,
    head_ref: str,
    *,
    timeout_seconds: int = 60,
) -> tuple[ChangedFile, ...]:
    result = run_git_read_only(
        repository_path,
        "diff",
        "--name-status",
        "--find-renames",
        f"{base_ref}..{head_ref}",
        timeout_seconds=timeout_seconds,
    )

    if not result.stdout:
        return ()

    changed_files: list[ChangedFile] = []

    for line in result.stdout.splitlines():
        parts = line.split("\t")

        if len(parts) == 2:
            status, path = parts
            previous_path = None
        elif (
            len(parts) == 3
            and parts[0].startswith(("R", "C"))
        ):
            status, previous_path, path = parts
        else:
            raise GitInspectionError(
                f"Unexpected git diff output: {line}"
            )

        changed_files.append(
            ChangedFile(
                status=status,
                path=path,
                previous_path=previous_path,
            )
        )

    return tuple(changed_files)


def inspect_repository(
    repository_path: str | Path,
    remote_ref: str = "origin/main",
    *,
    timeout_seconds: int = 60,
) -> RepositorySnapshot:
    repo_path = validate_git_repository(
        repository_path,
        timeout_seconds=timeout_seconds,
    )

    return RepositorySnapshot(
        repository_path=repo_path,
        branch=get_current_branch(
            repo_path,
            timeout_seconds=timeout_seconds,
        ),
        head=get_head(
            repo_path,
            timeout_seconds=timeout_seconds,
        ),
        remote_head=get_head(
            repo_path,
            remote_ref,
            timeout_seconds=timeout_seconds,
        ),
        origin_url=get_origin_url(
            repo_path,
            timeout_seconds=timeout_seconds,
        ),
        is_clean=is_worktree_clean(
            repo_path,
            timeout_seconds=timeout_seconds,
        ),
    )


def fetch_remote_branch(
    repository_path: str | Path,
    *,
    remote: str,
    branch: str,
    timeout_seconds: int = 60,
) -> None:
    """Refresh one configured remote branch without touching the worktree."""

    run_git_read_only(
        repository_path,
        "fetch",
        "--quiet",
        "--no-tags",
        remote,
        (
            f"+refs/heads/{branch}:"
            f"refs/remotes/{remote}/{branch}"
        ),
        timeout_seconds=timeout_seconds,
    )


def validate_origin_repository(
    origin_url: str,
    expected_repository: str,
) -> None:
    """Require an origin URL for exactly one allowlisted GitHub repository."""

    match = _GITHUB_ORIGIN_PATTERN.fullmatch(origin_url.strip())

    if match is None:
        raise GitInspectionError(
            "Origin URL must use an allowed GitHub HTTPS or SSH form."
        )

    actual = match.group("repository").lower()
    expected = expected_repository.strip().lower()

    if actual != expected:
        raise GitInspectionError(
            "Origin repository mismatch: "
            f"{actual!r}; expected {expected!r}."
        )


def _validate_git_arguments(git_args: tuple[str, ...]) -> None:
    command = git_args[0]

    if command == "rev-parse":
        if (
            len(git_args) == 2
            and (
                git_args[1] == "--show-toplevel"
                or _is_safe_ref(git_args[1])
            )
        ):
            return
    elif command == "branch":
        if git_args == ("branch", "--show-current"):
            return
    elif command == "status":
        if git_args == ("status", "--short"):
            return
    elif command == "remote":
        if git_args == ("remote", "get-url", "origin"):
            return
    elif command == "diff":
        if (
            len(git_args) == 4
            and git_args[1:3]
            == ("--name-status", "--find-renames")
            and _is_safe_commit_range(git_args[3])
        ):
            return
    elif command == "fetch":
        refspec_match = (
            _FETCH_REFSPEC_PATTERN.fullmatch(git_args[4])
            if len(git_args) == 5
            else None
        )
        if (
            len(git_args) == 5
            and git_args[1:3] == ("--quiet", "--no-tags")
            and _SAFE_REMOTE_PATTERN.fullmatch(git_args[3])
            and refspec_match is not None
            and refspec_match.group("remote") == git_args[3]
            and ".."
            not in refspec_match.group("branch").split("/")
        ):
            return

    raise GitInspectionError(
        "Git argument combination is not allowed for read-only operation: "
        + " ".join(git_args)
    )


def _is_safe_ref(value: str) -> bool:
    return (
        _SAFE_REF_PATTERN.fullmatch(value) is not None
        and ".." not in value.split("/")
        and not value.endswith(("/", ".lock"))
    )


def _is_safe_commit_range(value: str) -> bool:
    parts = value.split("..")
    return (
        len(parts) == 2
        and all(_is_safe_ref(part) for part in parts)
    )
