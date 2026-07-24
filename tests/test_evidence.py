from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from malak_vault_sync.evidence import (
    EvidenceError,
    build_manifest,
    build_run_id,
    sanitize_text,
    sha256_file,
    validate_run_id,
    write_evidence_package,
)
from malak_vault_sync.git_inspector import (
    ChangedFile,
    RepositorySnapshot,
)


SOURCE_COMMIT = "a" * 40
VAULT_COMMIT = "b" * 40
BASE_COMMIT = "c" * 40
HEAD_COMMIT = "d" * 40
GENERATED_AT = datetime(
    2026,
    7,
    22,
    19,
    30,
    tzinfo=UTC,
)


def build_snapshot(
    *,
    path: Path,
    head: str,
    remote_head: str,
    origin_url: str,
) -> RepositorySnapshot:
    return RepositorySnapshot(
        repository_path=path,
        branch="main",
        head=head,
        remote_head=remote_head,
        origin_url=origin_url,
        is_clean=True,
    )


def build_test_manifest(
    tmp_path: Path,
):
    source_snapshot = build_snapshot(
        path=tmp_path / "jarvis",
        head=SOURCE_COMMIT,
        remote_head=SOURCE_COMMIT,
        origin_url=(
            "https://user:secret@example.com/"
            "Aranwill/jarvis.git"
        ),
    )

    vault_snapshot = build_snapshot(
        path=tmp_path / "vault",
        head=VAULT_COMMIT,
        remote_head=VAULT_COMMIT,
        origin_url=(
            "https://github.com/"
            "Aranwill/malak-project-vault.git"
        ),
    )

    return build_manifest(
        source_snapshot=source_snapshot,
        vault_snapshot=vault_snapshot,
        base_commit=BASE_COMMIT,
        head_commit=HEAD_COMMIT,
        changed_files=(
            ChangedFile(
                status="M",
                path="zeta.txt",
            ),
            ChangedFile(
                status="A",
                path="alpha.txt",
            ),
        ),
        generated_at=GENERATED_AT,
    )


def test_build_run_id_is_deterministic() -> None:
    run_id = build_run_id(
        SOURCE_COMMIT,
        VAULT_COMMIT,
        generated_at=GENERATED_AT,
    )

    assert run_id == (
        "20260722T193000Z_aaaaaaaa_bbbbbbbb"
    )


def test_build_run_id_matches_canonical_validation_contract() -> None:
    run_id = build_run_id(
        SOURCE_COMMIT,
        VAULT_COMMIT,
        generated_at=GENERATED_AT,
    )

    assert run_id == "20260722T193000Z_aaaaaaaa_bbbbbbbb"
    assert validate_run_id(run_id) == run_id


def test_build_run_id_uses_microseconds_to_avoid_collisions() -> None:
    generated_at = GENERATED_AT.replace(microsecond=123456)

    run_id = build_run_id(
        SOURCE_COMMIT,
        VAULT_COMMIT,
        generated_at=generated_at,
    )

    assert run_id == (
        "20260722T193000123456Z_aaaaaaaa_bbbbbbbb"
    )
    assert validate_run_id(run_id) == run_id


@pytest.mark.parametrize(
    "run_id",
    [
        "20260722T193000Z-aaaaaaaa-bbbbbbbb",
        "invalid",
        "",
    ],
)
def test_validate_run_id_rejects_noncanonical_values(
    run_id: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="Invalid run_id",
    ):
        validate_run_id(run_id)


def test_build_run_id_rejects_invalid_sha() -> None:
    with pytest.raises(
        EvidenceError,
        match="40-character commit SHA",
    ):
        build_run_id(
            "abc",
            VAULT_COMMIT,
            generated_at=GENERATED_AT,
        )


def test_build_manifest_sorts_changed_files(
    tmp_path: Path,
) -> None:
    manifest = build_test_manifest(tmp_path)

    assert manifest.schema_version == 1
    assert manifest.execution.mode == "dry-run"
    assert manifest.execution.run_id == (
        "20260722T193000Z_dddddddd_bbbbbbbb"
    )
    assert manifest.commit_range.base_commit == BASE_COMMIT
    assert manifest.commit_range.head_commit == HEAD_COMMIT
    assert [item.path for item in manifest.changed_files] == [
        "alpha.txt",
        "zeta.txt",
    ]


def test_sanitize_text_redacts_credentials() -> None:
    value = (
        "token=abc123 "
        "password:secret "
        "https://user:pass@example.com/repo.git"
    )

    sanitized = sanitize_text(value)

    assert "abc123" not in sanitized
    assert "secret" not in sanitized
    assert "user:pass@" not in sanitized
    assert "[REDACTED]" in sanitized


def test_write_evidence_package_creates_expected_files(
    tmp_path: Path,
) -> None:
    manifest = build_test_manifest(tmp_path)

    run_path = write_evidence_package(
        tmp_path / "evidence",
        manifest,
    )

    assert run_path.is_dir()

    assert sorted(
        item.name
        for item in run_path.iterdir()
    ) == [
        "changed-files.json",
        "commit-range.json",
        "hashes.sha256",
        "manifest.json",
        "source-repository.json",
        "vault-repository.json",
    ]


def test_written_manifest_is_deterministic(
    tmp_path: Path,
) -> None:
    manifest = build_test_manifest(tmp_path)

    run_path = write_evidence_package(
        tmp_path / "evidence",
        manifest,
    )

    payload = (
        run_path / "manifest.json"
    ).read_text(encoding="utf-8")

    raw_data = json.loads(payload)

    assert payload.endswith("\n")
    assert raw_data["schema_version"] == 1
    assert raw_data["execution"]["mode"] == "dry-run"
    assert raw_data["changed_files"][0]["path"] == "alpha.txt"


def test_origin_url_is_sanitized_in_evidence(
    tmp_path: Path,
) -> None:
    manifest = build_test_manifest(tmp_path)

    run_path = write_evidence_package(
        tmp_path / "evidence",
        manifest,
    )

    raw_data = json.loads(
        (
            run_path / "source-repository.json"
        ).read_text(encoding="utf-8")
    )

    assert "secret" not in raw_data["origin_url"]
    assert "user:" not in raw_data["origin_url"]
    assert "[REDACTED]" in raw_data["origin_url"]


def test_hash_manifest_matches_artifacts(
    tmp_path: Path,
) -> None:
    manifest = build_test_manifest(tmp_path)

    run_path = write_evidence_package(
        tmp_path / "evidence",
        manifest,
    )

    lines = (
        run_path / "hashes.sha256"
    ).read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(lines) == 5

    for line in lines:
        digest, filename = line.split(
            "  ",
            maxsplit=1,
        )

        assert sha256_file(
            run_path / filename
        ) == digest


def test_existing_run_directory_is_rejected(
    tmp_path: Path,
) -> None:
    manifest = build_test_manifest(tmp_path)

    output_root = tmp_path / "evidence"

    write_evidence_package(
        output_root,
        manifest,
    )

    with pytest.raises(
        EvidenceError,
        match="already exists",
    ):
        write_evidence_package(
            output_root,
            manifest,
        )


def test_evidence_package_size_limit_is_enforced(
    tmp_path: Path,
) -> None:
    manifest = build_test_manifest(tmp_path)

    with pytest.raises(
        EvidenceError,
        match="size limit exceeded",
    ):
        write_evidence_package(
            tmp_path / "evidence",
            manifest,
            max_bytes=1,
        )

    assert not any((tmp_path / "evidence").iterdir())


def test_sha256_file_is_stable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sample.txt"
    path.write_text(
        "sample\n",
        encoding="utf-8",
    )

    assert sha256_file(path) == (
        "aaf9ff488e0767da5ea1d56118e6f65"
        "a16c5633b0cefc1fa089bd3ab1810613d"
    )
