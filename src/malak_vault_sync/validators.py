from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import yaml


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    severity: str
    code: str
    message: str
    path: str | None = None


_ALLOWED_SEVERITIES = {
    "info",
    "warning",
    "error",
}

_MARKDOWN_LINK_PATTERN = re.compile(
    r"(?<!!)\[[^\]]*]\(([^)]+)\)"
)

_WIKILINK_PATTERN = re.compile(
    r"!?\[\[([^\]]+)]]"
)

_FENCE_PATTERN = re.compile(
    r"^\s*(```|~~~)",
    re.MULTILINE,
)

_SHA256_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}

    for key_node, value_node in node.value:
        key = loader.construct_object(
            key_node,
            deep=deep,
        )

        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key: {key}",
                key_node.start_mark,
            )

        mapping[key] = loader.construct_object(
            value_node,
            deep=deep,
        )

    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def validate_path(
    root: str | Path,
    candidate: str | Path,
    *,
    follow_symlinks: bool = False,
) -> tuple[ValidationFinding, ...]:
    root_path = Path(root).resolve()
    candidate_path = Path(candidate)

    if candidate_path.is_absolute():
        absolute_path = candidate_path
    else:
        absolute_path = root_path / candidate_path

    findings: list[ValidationFinding] = []

    if ".." in candidate_path.parts:
        findings.append(
            ValidationFinding(
                severity="error",
                code="PATH_PARENT_TRAVERSAL",
                message=(
                    "Parent path traversal is not allowed."
                ),
                path=str(candidate),
            )
        )

        return tuple(findings)

    resolved_path = absolute_path.resolve(
        strict=False,
    )

    if not _is_within_root(
        root_path,
        resolved_path,
    ):
        findings.append(
            ValidationFinding(
                severity="error",
                code="PATH_OUTSIDE_ROOT",
                message=(
                    "Resolved path escapes the configured root."
                ),
                path=str(candidate),
            )
        )

        return tuple(findings)

    if not follow_symlinks:
        symlink = _first_symlink_component(
            root_path,
            absolute_path,
        )

        if symlink is not None:
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="PATH_SYMLINK_DENIED",
                    message=(
                        "Symbolic links are not allowed."
                    ),
                    path=str(symlink),
                )
            )

    return tuple(findings)


def validate_markdown(
    path: str | Path,
) -> tuple[ValidationFinding, ...]:
    file_path = Path(path)
    findings: list[ValidationFinding] = []

    text = _read_utf8_text(
        file_path,
        findings,
    )

    if text is None:
        return tuple(findings)

    if "\x00" in text:
        findings.append(
            ValidationFinding(
                severity="error",
                code="MARKDOWN_NULL_BYTE",
                message=(
                    "Markdown contains a null byte."
                ),
                path=str(file_path),
            )
        )

    fences = _FENCE_PATTERN.findall(text)

    if len(fences) % 2 != 0:
        findings.append(
            ValidationFinding(
                severity="error",
                code="MARKDOWN_UNBALANCED_FENCE",
                message=(
                    "Markdown code fences are not balanced."
                ),
                path=str(file_path),
            )
        )

    return tuple(findings)


def validate_markdown_frontmatter(
    path: str | Path,
) -> tuple[ValidationFinding, ...]:
    """Validate YAML frontmatter when a Markdown document declares it."""

    file_path = Path(path)
    findings: list[ValidationFinding] = []
    text = _read_utf8_text(file_path, findings)

    if text is None:
        return tuple(findings)

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ()

    closing_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        ),
        None,
    )

    if closing_index is None:
        return (
            ValidationFinding(
                severity="error",
                code="MARKDOWN_FRONTMATTER_UNCLOSED",
                message="Markdown YAML frontmatter is not closed.",
                path=str(file_path),
            ),
        )

    frontmatter = "\n".join(lines[1:closing_index])

    try:
        payload = yaml.load(
            frontmatter,
            Loader=_UniqueKeyLoader,
        )
    except yaml.YAMLError as exc:
        return (
            ValidationFinding(
                severity="error",
                code="MARKDOWN_FRONTMATTER_INVALID",
                message=_single_line_message(exc),
                path=str(file_path),
            ),
        )

    if not isinstance(payload, dict):
        return (
            ValidationFinding(
                severity="error",
                code="MARKDOWN_FRONTMATTER_NOT_MAPPING",
                message="Markdown YAML frontmatter must be a mapping.",
                path=str(file_path),
            ),
        )

    return ()


def validate_yaml(
    path: str | Path,
) -> tuple[ValidationFinding, ...]:
    file_path = Path(path)
    findings: list[ValidationFinding] = []

    text = _read_utf8_text(
        file_path,
        findings,
    )

    if text is None:
        return tuple(findings)

    try:
        yaml.load(
            text,
            Loader=_UniqueKeyLoader,
        )
    except yaml.YAMLError as exc:
        findings.append(
            ValidationFinding(
                severity="error",
                code="YAML_INVALID",
                message=_single_line_message(exc),
                path=str(file_path),
            )
        )

    return tuple(findings)


def validate_relative_links(
    markdown_path: str | Path,
    vault_root: str | Path,
) -> tuple[ValidationFinding, ...]:
    file_path = Path(markdown_path)
    root_path = Path(vault_root).resolve()
    findings: list[ValidationFinding] = []

    text = _read_utf8_text(
        file_path,
        findings,
    )

    if text is None:
        return tuple(findings)

    for raw_target in _MARKDOWN_LINK_PATTERN.findall(
        text
    ):
        target = raw_target.strip().strip("<>")

        if _is_external_or_internal_anchor(target):
            continue

        normalized_target = unquote(
            target.split("#", maxsplit=1)[0]
            .split("?", maxsplit=1)[0]
        ).strip()

        if not normalized_target:
            continue

        target_path = (
            file_path.parent
            / normalized_target
        )

        path_findings = validate_path(
            root_path,
            target_path,
            follow_symlinks=False,
        )

        findings.extend(path_findings)

        if any(
            finding.severity == "error"
            for finding in path_findings
        ):
            continue

        if not target_path.exists():
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="LINK_TARGET_MISSING",
                    message=(
                        "Relative link target does not exist."
                    ),
                    path=normalized_target,
                )
            )

    for raw_target in _WIKILINK_PATTERN.findall(text):
        target = raw_target.split("|", maxsplit=1)[0].strip()
        normalized_target = unquote(
            target.split("#", maxsplit=1)[0]
        ).strip()

        if not normalized_target:
            continue

        target_path = root_path / normalized_target
        markdown_target = Path(f"{target_path}.md")
        if (
            not target_path.is_file()
            and (
                markdown_target.is_file()
                or target_path.suffix == ""
            )
        ):
            target_path = markdown_target

        path_findings = validate_path(
            root_path,
            target_path,
            follow_symlinks=False,
        )
        findings.extend(path_findings)

        if any(
            finding.severity == "error"
            for finding in path_findings
        ):
            continue

        if not target_path.is_file():
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="WIKILINK_TARGET_MISSING",
                    message="Obsidian wikilink target does not exist.",
                    path=normalized_target,
                )
            )

    return tuple(findings)


def validate_hash_manifest(
    run_path: str | Path,
) -> tuple[ValidationFinding, ...]:
    directory = Path(run_path)
    manifest_path = directory / "hashes.sha256"
    findings: list[ValidationFinding] = []

    text = _read_utf8_text(
        manifest_path,
        findings,
    )

    if text is None:
        return tuple(findings)

    for line_number, line in enumerate(
        text.splitlines(),
        start=1,
    ):
        if not line.strip():
            continue

        parts = line.split(
            "  ",
            maxsplit=1,
        )

        if len(parts) != 2:
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="HASH_LINE_INVALID",
                    message=(
                        "Hash manifest line must use "
                        "'<sha256>  <filename>'."
                    ),
                    path=f"{manifest_path}:{line_number}",
                )
            )

            continue

        expected_hash, filename = parts
        expected_hash = expected_hash.strip().lower()
        filename = filename.strip()

        if not _SHA256_PATTERN.fullmatch(
            expected_hash
        ):
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="HASH_FORMAT_INVALID",
                    message=(
                        "Expected a lowercase SHA-256 digest."
                    ),
                    path=f"{manifest_path}:{line_number}",
                )
            )

            continue

        path_findings = validate_path(
            directory,
            filename,
            follow_symlinks=False,
        )

        findings.extend(path_findings)

        if any(
            finding.severity == "error"
            for finding in path_findings
        ):
            continue

        artifact_path = directory / filename

        if not artifact_path.is_file():
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="HASH_ARTIFACT_MISSING",
                    message=(
                        "Hashed artifact does not exist."
                    ),
                    path=filename,
                )
            )

            continue

        actual_hash = _sha256_file(
            artifact_path
        )

        if actual_hash != expected_hash:
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="HASH_MISMATCH",
                    message=(
                        "Artifact SHA-256 does not match "
                        "the manifest."
                    ),
                    path=filename,
                )
            )

    return tuple(findings)


def has_errors(
    findings: tuple[ValidationFinding, ...],
) -> bool:
    return any(
        finding.severity == "error"
        for finding in findings
    )


def _read_utf8_text(
    path: Path,
    findings: list[ValidationFinding],
) -> str | None:
    if not path.is_file():
        findings.append(
            ValidationFinding(
                severity="error",
                code="FILE_MISSING",
                message="File does not exist.",
                path=str(path),
            )
        )

        return None

    try:
        return path.read_text(
            encoding="utf-8",
        )
    except UnicodeDecodeError:
        findings.append(
            ValidationFinding(
                severity="error",
                code="FILE_NOT_UTF8",
                message=(
                    "File is not valid UTF-8."
                ),
                path=str(path),
            )
        )
    except OSError as exc:
        findings.append(
            ValidationFinding(
                severity="error",
                code="FILE_READ_ERROR",
                message=_single_line_message(exc),
                path=str(path),
            )
        )

    return None


def _is_within_root(
    root: Path,
    candidate: Path,
) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False

    return True


def _first_symlink_component(
    root: Path,
    candidate: Path,
) -> Path | None:
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return candidate

    current = root

    for part in relative.parts:
        current = current / part

        if current.exists() and current.is_symlink():
            return current

    return None


def _is_external_or_internal_anchor(
    target: str,
) -> bool:
    lowered = target.lower()

    return (
        target.startswith("#")
        or lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("mailto:")
        or lowered.startswith("tel:")
    )


def _sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        for chunk in iter(
            lambda: file_handle.read(65536),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _single_line_message(
    value: object,
) -> str:
    return " ".join(
        str(value).splitlines()
    )
