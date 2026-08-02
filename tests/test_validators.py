from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from malak_vault_sync.validators import (
    has_errors,
    validate_hash_manifest,
    validate_markdown,
    validate_markdown_frontmatter,
    validate_path,
    validate_relative_links,
    validate_yaml,
)


def test_validate_path_accepts_relative_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vault"
    root.mkdir()

    target = root / "docs" / "file.md"
    target.parent.mkdir()
    target.write_text("# Test\n", encoding="utf-8")

    assert validate_path(
        root,
        "docs/file.md",
    ) == ()


def test_validate_path_rejects_parent_traversal(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vault"
    root.mkdir()

    findings = validate_path(
        root,
        "../outside.md",
    )

    assert has_errors(findings)
    assert findings[0].code == "PATH_PARENT_TRAVERSAL"


def test_validate_path_rejects_outside_absolute_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vault"
    root.mkdir()

    outside = tmp_path / "outside.md"

    findings = validate_path(
        root,
        outside,
    )

    assert has_errors(findings)
    assert findings[0].code == "PATH_OUTSIDE_ROOT"


def test_validate_markdown_accepts_balanced_fences(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.md"
    path.write_text(
        "# Title\n\n```python\nprint('ok')\n```\n",
        encoding="utf-8",
    )

    assert validate_markdown(path) == ()


def test_validate_markdown_rejects_unbalanced_fence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.md"
    path.write_text(
        "# Title\n\n```python\nprint('broken')\n",
        encoding="utf-8",
    )

    findings = validate_markdown(path)

    assert has_errors(findings)
    assert findings[0].code == "MARKDOWN_UNBALANCED_FENCE"


def test_validate_markdown_rejects_null_byte(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.md"
    path.write_bytes(b"# Title\x00\n")

    findings = validate_markdown(path)

    assert has_errors(findings)
    assert findings[0].code == "MARKDOWN_NULL_BYTE"


def test_validate_markdown_frontmatter_accepts_mapping(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.md"
    path.write_text(
        "---\ntitle: Test\nstatus: active\n---\n\n# Test\n",
        encoding="utf-8",
    )

    assert validate_markdown_frontmatter(path) == ()


def test_validate_markdown_frontmatter_rejects_duplicate_keys(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.md"
    path.write_text(
        "---\ntitle: First\ntitle: Second\n---\n",
        encoding="utf-8",
    )

    findings = validate_markdown_frontmatter(path)

    assert has_errors(findings)
    assert findings[0].code == "MARKDOWN_FRONTMATTER_INVALID"


def test_validate_markdown_frontmatter_rejects_missing_delimiter(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.md"
    path.write_text("---\ntitle: Test\n", encoding="utf-8")

    findings = validate_markdown_frontmatter(path)

    assert has_errors(findings)
    assert findings[0].code == "MARKDOWN_FRONTMATTER_UNCLOSED"


def test_validate_markdown_frontmatter_rejects_missing_opening_delimiter(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.md"
    path.write_text(
        "title: Test\n---\n\n# Test\n",
        encoding="utf-8",
    )

    findings = validate_markdown_frontmatter(path)

    assert has_errors(findings)
    assert findings[0].code == "MARKDOWN_FRONTMATTER_MISSING"


def test_validate_yaml_accepts_valid_document(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "name: test\nvalue: 1\n",
        encoding="utf-8",
    )

    assert validate_yaml(path) == ()


def test_validate_yaml_rejects_duplicate_keys(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "name: first\nname: second\n",
        encoding="utf-8",
    )

    findings = validate_yaml(path)

    assert has_errors(findings)
    assert findings[0].code == "YAML_INVALID"


def test_validate_yaml_rejects_invalid_document(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "name: [broken\n",
        encoding="utf-8",
    )

    findings = validate_yaml(path)

    assert has_errors(findings)
    assert findings[0].code == "YAML_INVALID"


def test_validate_relative_links_accepts_existing_target(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vault"
    docs = root / "docs"
    docs.mkdir(parents=True)

    target = docs / "target.md"
    target.write_text("# Target\n", encoding="utf-8")

    source = docs / "source.md"
    source.write_text(
        "[Target](target.md)\n",
        encoding="utf-8",
    )

    assert validate_relative_links(
        source,
        root,
    ) == ()


def test_validate_relative_links_rejects_missing_target(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vault"
    docs = root / "docs"
    docs.mkdir(parents=True)

    source = docs / "source.md"
    source.write_text(
        "[Missing](missing.md)\n",
        encoding="utf-8",
    )

    findings = validate_relative_links(
        source,
        root,
    )

    assert has_errors(findings)
    assert findings[0].code == "LINK_TARGET_MISSING"


def test_validate_relative_links_ignores_external_links(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vault"
    root.mkdir()

    source = root / "source.md"
    source.write_text(
        "[OpenAI](https://openai.com)\n"
        "[Mail](mailto:test@example.com)\n"
        "[Anchor](#section)\n",
        encoding="utf-8",
    )

    assert validate_relative_links(
        source,
        root,
    ) == ()


def test_validate_relative_links_accepts_obsidian_wikilink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vault"
    target = root / "02-current-baseline" / "CURRENT_BASELINE.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Baseline\n", encoding="utf-8")
    source = root / "source.md"
    source.write_text(
        "[[02-current-baseline/CURRENT_BASELINE|Baseline]]\n",
        encoding="utf-8",
    )

    assert validate_relative_links(source, root) == ()


def test_validate_relative_links_accepts_extensionless_dotted_wikilink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vault"
    target = root / "04-sprints" / "SPRINT-7.4-CLOSURE.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Closure\n", encoding="utf-8")
    source = root / "source.md"
    source.write_text(
        "[[04-sprints/SPRINT-7.4-CLOSURE|Closure]]\n",
        encoding="utf-8",
    )

    assert validate_relative_links(source, root) == ()


def test_validate_relative_links_rejects_missing_wikilink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    source = root / "source.md"
    source.write_text("[[missing/document|Missing]]\n", encoding="utf-8")

    findings = validate_relative_links(source, root)

    assert has_errors(findings)
    assert findings[0].code == "WIKILINK_TARGET_MISSING"


def test_validate_hash_manifest_accepts_valid_hash(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text(
        '{"ok": true}\n',
        encoding="utf-8",
        newline="\n",
    )

    digest = hashlib.sha256(
        artifact.read_bytes()
    ).hexdigest()

    manifest = tmp_path / "hashes.sha256"
    manifest.write_text(
        f"{digest}  artifact.json\n",
        encoding="utf-8",
        newline="\n",
    )

    assert validate_hash_manifest(tmp_path) == ()


def test_validate_hash_manifest_detects_mismatch(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text(
        '{"ok": true}\n',
        encoding="utf-8",
        newline="\n",
    )

    manifest = tmp_path / "hashes.sha256"
    manifest.write_text(
        f"{'0' * 64}  artifact.json\n",
        encoding="utf-8",
        newline="\n",
    )

    findings = validate_hash_manifest(tmp_path)

    assert has_errors(findings)
    assert findings[0].code == "HASH_MISMATCH"


def test_validate_hash_manifest_detects_missing_artifact(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "hashes.sha256"
    manifest.write_text(
        f"{'0' * 64}  missing.json\n",
        encoding="utf-8",
        newline="\n",
    )

    findings = validate_hash_manifest(tmp_path)

    assert has_errors(findings)
    assert findings[0].code == "HASH_ARTIFACT_MISSING"


def test_missing_file_returns_finding(
    tmp_path: Path,
) -> None:
    findings = validate_markdown(
        tmp_path / "missing.md"
    )

    assert has_errors(findings)
    assert findings[0].code == "FILE_MISSING"


def test_non_utf8_file_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.md"
    path.write_bytes(b"\xff\xfe\x00\x00")

    findings = validate_markdown(path)

    assert has_errors(findings)
    assert findings[0].code == "FILE_NOT_UTF8"
