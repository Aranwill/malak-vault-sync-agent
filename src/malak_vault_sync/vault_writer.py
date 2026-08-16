from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from malak_vault_sync import __version__
from malak_vault_sync.audit import AuditReport
from malak_vault_sync.candidate_resolver import (
    DocumentCandidate,
    is_allowed_vault_path,
)
from malak_vault_sync.evidence import EvidenceManifest, sanitize_text
from malak_vault_sync.validators import (
    ValidationFinding,
    has_errors,
    validate_markdown,
    validate_markdown_frontmatter,
    validate_relative_links,
)


class VaultProposalError(RuntimeError):
    """Raised when a governed Vault proposal cannot be prepared safely."""


@dataclass(frozen=True, slots=True)
class VaultProposal:
    branch: str
    content_commit: str
    audit_commit: str
    report_path: str
    pull_request_url: str
    modified_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceProjection:
    sprint_document: str | None
    sprint_title: str | None
    sprint_status: str | None
    sprint_as_of_commit: str | None
    commit_summaries: tuple[str, ...]


_MANAGED_START = "<!-- MALAK_VAULT_SYNC:START -->"
_MANAGED_END = "<!-- MALAK_VAULT_SYNC:END -->"
_BRANCH_PATTERN = re.compile(
    r"^agent/vault-sync-[0-9a-f]{8}$"
)
_REPORT_PATTERN = re.compile(
    r"^07-audits/vault-synchronization/"
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}_VAULT_SYNC_"
    r"[0-9A-Za-z_-]+\.md$"
)


def prepare_vault_proposal(
    *,
    vault_root: Path,
    evidence: EvidenceManifest,
    candidates: tuple[DocumentCandidate, ...],
    report: AuditReport,
    remote: str,
    base_branch: str,
    branch_prefix: str,
    github_cli: str,
    timeout_seconds: int,
) -> VaultProposal:
    """Create two commits, push them and open a human-reviewed draft PR."""

    if not candidates:
        raise VaultProposalError(
            "A Vault proposal requires at least one document candidate."
        )

    _validate_candidates(candidates)
    branch = f"{branch_prefix}-{evidence.commit_range.head_commit[:8]}"

    if _BRANCH_PATTERN.fullmatch(branch) is None:
        raise VaultProposalError(
            f"Unsafe proposal branch name: {branch}"
        )

    _preflight_github_cli(
        vault_root,
        github_cli=github_cli,
        branch_prefix=branch_prefix,
        timeout_seconds=timeout_seconds,
    )
    source_projection = _collect_source_projection(
        evidence,
        timeout_seconds=timeout_seconds,
    )

    remote_ref = f"{remote}/{base_branch}"
    expected_vault_head = evidence.vault_snapshot.remote_head
    current_remote_head = _git(
        vault_root,
        "rev-parse",
        remote_ref,
        timeout_seconds=timeout_seconds,
    )

    if current_remote_head != expected_vault_head:
        raise VaultProposalError(
            "Vault remote HEAD changed after evidence generation."
        )

    branch_created = False
    with tempfile.TemporaryDirectory(
        prefix="malak-vault-proposal-"
    ) as temporary_directory:
        worktree = Path(temporary_directory) / "vault"
        _git(
            vault_root,
            "worktree",
            "add",
            "--detach",
            str(worktree),
            remote_ref,
            timeout_seconds=timeout_seconds,
        )

        try:
            _git(
                worktree,
                "switch",
                "-c",
                branch,
                timeout_seconds=timeout_seconds,
            )
            branch_created = True

            modified_paths = _write_candidate_projections(
                worktree,
                evidence,
                candidates,
                source_projection,
            )
            _validate_written_projections(worktree, modified_paths)
            _validate_projection_consistency(
                worktree,
                candidates,
                evidence,
                source_projection,
            )
            _git(worktree, "diff", "--check", timeout_seconds=timeout_seconds)
            _git(
                worktree,
                "add",
                "--",
                *modified_paths,
                timeout_seconds=timeout_seconds,
            )
            _git(
                worktree,
                "commit",
                "-m",
                "docs(vault): project verified Malak change",
                timeout_seconds=timeout_seconds,
            )
            content_commit = _git(
                worktree,
                "rev-parse",
                "HEAD",
                timeout_seconds=timeout_seconds,
            )

            report_path = _write_audit_report(
                worktree,
                evidence=evidence,
                report=report,
                candidates=candidates,
                branch=branch,
                content_commit=content_commit,
                modified_paths=modified_paths,
            )
            index_path = _update_audit_index(
                worktree,
                report_path=report_path,
                run_id=evidence.execution.run_id,
            )
            _validate_written_projections(
                worktree,
                (report_path, index_path),
            )
            _git(worktree, "diff", "--check", timeout_seconds=timeout_seconds)
            _git(
                worktree,
                "add",
                "--",
                report_path,
                index_path,
                timeout_seconds=timeout_seconds,
            )
            _git(
                worktree,
                "commit",
                "-m",
                "docs(audit): record governed vault proposal",
                timeout_seconds=timeout_seconds,
            )
            audit_commit = _git(
                worktree,
                "rev-parse",
                "HEAD",
                timeout_seconds=timeout_seconds,
            )

            _verify_source_and_vault_heads(
                evidence,
                timeout_seconds=timeout_seconds,
            )
            _git(
                worktree,
                "push",
                "--set-upstream",
                remote,
                branch,
                timeout_seconds=timeout_seconds,
            )

            try:
                pull_request_url = _open_draft_pr(
                    worktree,
                    github_cli=github_cli,
                    branch=branch,
                    base_branch=base_branch,
                    evidence=evidence,
                    content_commit=content_commit,
                    report_path=report_path,
                    timeout_seconds=timeout_seconds,
                )
            except VaultProposalError as exc:
                _rollback_published_branch(
                    worktree,
                    remote=remote,
                    branch=branch,
                    timeout_seconds=timeout_seconds,
                )
                raise VaultProposalError(
                    "Draft PR creation failed; the published proposal "
                    "branch was rolled back."
                ) from exc
        finally:
            _git(
                vault_root,
                "worktree",
                "remove",
                "--force",
                str(worktree),
                timeout_seconds=timeout_seconds,
            )
            if branch_created:
                _delete_local_branch(
                    vault_root,
                    branch=branch,
                    timeout_seconds=timeout_seconds,
                )

    return VaultProposal(
        branch=branch,
        content_commit=content_commit,
        audit_commit=audit_commit,
        report_path=report_path,
        pull_request_url=pull_request_url,
        modified_paths=modified_paths,
    )


def synchronize_vault_checkout(
    vault_root: Path,
    *,
    remote: str,
    base_branch: str,
    expected_remote_head: str,
    timeout_seconds: int,
) -> None:
    """Fast-forward a clean Vault checkout to its verified remote HEAD."""

    branch = _git(
        vault_root,
        "branch",
        "--show-current",
        timeout_seconds=timeout_seconds,
    )
    if branch != base_branch:
        raise VaultProposalError(
            f"Vault checkout branch changed before synchronization: {branch}."
        )

    status = _git(
        vault_root,
        "status",
        "--short",
        timeout_seconds=timeout_seconds,
    )
    if status:
        raise VaultProposalError(
            "Vault checkout must be clean before synchronization."
        )

    remote_ref = f"{remote}/{base_branch}"
    remote_head = _git(
        vault_root,
        "rev-parse",
        remote_ref,
        timeout_seconds=timeout_seconds,
    )
    if remote_head != expected_remote_head:
        raise VaultProposalError(
            "Vault remote HEAD changed before local synchronization."
        )

    local_head = _git(
        vault_root,
        "rev-parse",
        "HEAD",
        timeout_seconds=timeout_seconds,
    )
    if local_head == remote_head:
        return

    _git(
        vault_root,
        "merge",
        "--ff-only",
        "--quiet",
        remote_ref,
        timeout_seconds=timeout_seconds,
    )
    synchronized_head = _git(
        vault_root,
        "rev-parse",
        "HEAD",
        timeout_seconds=timeout_seconds,
    )
    if synchronized_head != expected_remote_head:
        raise VaultProposalError(
            "Vault checkout did not reach the verified remote HEAD."
        )


def _write_candidate_projections(
    worktree: Path,
    evidence: EvidenceManifest,
    candidates: tuple[DocumentCandidate, ...],
    source_projection: SourceProjection,
) -> tuple[str, ...]:
    modified: list[str] = []

    for candidate in candidates:
        path = worktree / candidate.path

        if not path.is_file():
            raise VaultProposalError(
                f"Candidate document does not exist: {candidate.path}"
            )

        content = path.read_text(encoding="utf-8-sig")
        block = _render_projection(
            evidence,
            candidate,
            source_projection,
        )
        updated = _upsert_managed_block(content, block)
        path.write_text(updated, encoding="utf-8", newline="\n")
        modified.append(candidate.path)

    return tuple(sorted(modified))


def _render_projection(
    evidence: EvidenceManifest,
    candidate: DocumentCandidate,
    source_projection: SourceProjection | None = None,
) -> str:
    reasons = "\n".join(
        (
            f"- `{reason.rule_id}` por "
            f"`{sanitize_text(reason.source_path)}`"
        )
        for reason in candidate.reasons
    )

    lines = [
            _MANAGED_START,
            "## Proyección automática de sincronización",
            "",
            "> [!warning] Estado derivado pendiente de revisión",
            "> Este bloque fue generado de forma determinista a partir de",
            "> `Aranwill/jarvis/main`. No aprueba decisiones, no cierra",
            "> sprints y no reemplaza la revisión humana del documento.",
            "",
            f"- **Run ID:** `{evidence.execution.run_id}`",
            (
                "- **HEAD oficial observado:** "
                f"`{evidence.commit_range.head_commit}`"
            ),
            (
                "- **Commit previamente observado:** "
                f"`{evidence.commit_range.base_commit}`"
            ),
            f"- **Generado:** `{evidence.execution.generated_at}`",
            f"- **Prioridad:** `{candidate.priority}`",
            "- **Disposición:** `review_required`",
    ]

    if source_projection is not None:
        lines.extend(
            [
                "",
                "### Estado estructurado de la fuente oficial",
                "",
                (
                    "- **Ficha de sprint más reciente:** "
                    f"`{source_projection.sprint_document}`"
                    if source_projection.sprint_document
                    else "- **Ficha de sprint más reciente:** no detectada"
                ),
                (
                    "- **Título declarado:** "
                    f"{source_projection.sprint_title}"
                    if source_projection.sprint_title
                    else "- **Título declarado:** no disponible"
                ),
                (
                    "- **Estado declarado:** "
                    f"`{source_projection.sprint_status}`"
                    if source_projection.sprint_status
                    else "- **Estado declarado:** no disponible"
                ),
                (
                    "- **`as_of_commit` declarado:** "
                    f"`{source_projection.sprint_as_of_commit}`"
                    if source_projection.sprint_as_of_commit
                    else "- **`as_of_commit` declarado:** no disponible"
                ),
                "",
                "### Commits oficiales observados",
                "",
            ]
        )
        lines.extend(
            f"- {summary}"
            for summary in source_projection.commit_summaries
        )

    lines.extend(
        [
            "",
            "### Evidencia que originó esta proyección",
            "",
            reasons or "- Sin razones registradas.",
            _MANAGED_END,
        ]
    )
    return "\n".join(lines)


def _collect_source_projection(
    evidence: EvidenceManifest,
    *,
    timeout_seconds: int,
) -> SourceProjection:
    source_root = evidence.source_snapshot.repository_path
    head = evidence.commit_range.head_commit
    base = evidence.commit_range.base_commit
    tree = _git(
        source_root,
        "ls-tree",
        "-r",
        "--name-only",
        head,
        "--",
        "docs/project/sprints",
        timeout_seconds=timeout_seconds,
    )
    sprint_paths = [
        path
        for path in tree.splitlines()
        if re.fullmatch(
            r"docs/project/sprints/SPRINT-[0-9]+(?:\.[0-9]+)?\.md",
            path,
        )
    ]
    sprint_records: list[
        tuple[str, str | None, str | None, str | None]
    ] = []
    for path in sprint_paths:
        sprint_content = _git(
            source_root,
            "show",
            f"{head}:{path}",
            timeout_seconds=timeout_seconds,
        )
        sprint_records.append(
            (
                path,
                _frontmatter_value(sprint_content, "title"),
                _frontmatter_value(sprint_content, "status"),
                _frontmatter_value(
                    sprint_content,
                    "as_of_commit",
                ),
            )
        )

    selected = (
        max(sprint_records, key=_sprint_record_sort_key)
        if sprint_records
        else None
    )
    if selected is None:
        sprint_path = title = status = as_of_commit = None
    else:
        sprint_path, title, status, as_of_commit = selected

    log_output = _git(
        source_root,
        "log",
        "--format=%H%x09%s",
        f"{base}..{head}",
        timeout_seconds=timeout_seconds,
    )
    commit_summaries = tuple(
        sanitize_text(line)[:500]
        for line in log_output.splitlines()
        if line.strip()
    )

    return SourceProjection(
        sprint_document=sprint_path,
        sprint_title=title,
        sprint_status=status,
        sprint_as_of_commit=as_of_commit,
        commit_summaries=commit_summaries,
    )


def _sprint_sort_key(path: str) -> tuple[int, int]:
    match = re.search(r"SPRINT-([0-9]+)(?:\.([0-9]+))?\.md$", path)
    if match is None:
        return (-1, -1)
    return (int(match.group(1)), int(match.group(2) or 0))


def _sprint_record_sort_key(
    record: tuple[str, str | None, str | None, str | None],
) -> tuple[int, int, int]:
    path, _, status, _ = record
    normalized = (status or "").strip().casefold()

    if normalized in {
        "en progreso",
        "active",
        "activo",
        "in_progress",
    }:
        status_rank = 3
    elif normalized in {
        "approved",
        "aprobado",
        "aprobada",
    }:
        status_rank = 2
    elif normalized in {
        "closed",
        "cerrado",
        "cerrada",
        "completed",
        "completado",
        "completada",
    }:
        status_rank = 1
    else:
        status_rank = 0

    major, minor = _sprint_sort_key(path)
    return (status_rank, major, minor)


def _frontmatter_value(content: str, key: str) -> str | None:
    content = content.removeprefix("\ufeff")
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---", 4)
    if end == -1:
        return None
    pattern = re.compile(
        rf"^{re.escape(key)}:\s*(?P<value>.+?)\s*$",
        re.MULTILINE,
    )
    match = pattern.search(content[4:end])
    if match is None:
        return None
    return sanitize_text(
        match.group("value").strip().strip("'\"")
    )[:500]


def _upsert_managed_block(content: str, block: str) -> str:
    start = content.find(_MANAGED_START)
    end = content.find(_MANAGED_END)

    if (start == -1) != (end == -1):
        raise VaultProposalError(
            "Malformed managed synchronization block."
        )

    if start != -1:
        end += len(_MANAGED_END)
        return content[:start] + block + content[end:]

    heading = content.find("\n# ")

    if heading == -1:
        raise VaultProposalError(
            "Candidate document has no top-level heading."
        )

    heading_end = content.find("\n", heading + 1)
    if heading_end == -1:
        heading_end = len(content)

    return (
        content[: heading_end + 1]
        + "\n"
        + block
        + "\n"
        + content[heading_end + 1 :]
    )


def _write_audit_report(
    worktree: Path,
    *,
    evidence: EvidenceManifest,
    report: AuditReport,
    candidates: tuple[DocumentCandidate, ...],
    branch: str,
    content_commit: str,
    modified_paths: tuple[str, ...],
) -> str:
    generated = datetime.fromisoformat(
        evidence.execution.generated_at.replace("Z", "+00:00")
    )
    report_path = (
        "07-audits/vault-synchronization/"
        f"{generated:%Y-%m-%d}_VAULT_SYNC_"
        f"{evidence.execution.run_id}.md"
    )

    if _REPORT_PATTERN.fullmatch(report_path) is None:
        raise VaultProposalError("Unsafe audit report path.")

    path = worktree / report_path
    if path.exists():
        raise VaultProposalError(
            f"Audit report already exists: {report_path}"
        )

    changed = "\n".join(
        (
            f"- `{item.status}` — `{sanitize_text(item.path)}`"
            + (
                f" (antes `{sanitize_text(item.previous_path)}`)"
                if item.previous_path
                else ""
            )
        )
        for item in evidence.changed_files
    )
    files = "\n".join(f"- `{item}`" for item in modified_paths)
    candidate_lines = "\n".join(
        f"- `{candidate.path}` — `{candidate.priority}`"
        for candidate in candidates
    )

    payload = "\n".join(
        [
            "---",
            f"id: {evidence.execution.run_id}",
            "title: Informe auditable de propuesta de sincronización",
            "type: synchronization-audit-report",
            "status: proposed",
            f"created: {generated:%Y-%m-%d}",
            f"agent_version: {__version__}",
            "policy_version: 1.1",
            "execution_mode: controlled-proposal",
            "official_repository: Aranwill/jarvis",
            "official_branch: main",
            f"official_previous_head: {evidence.commit_range.base_commit}",
            f"official_current_head: {evidence.commit_range.head_commit}",
            "vault_repository: Aranwill/malak-project-vault",
            "vault_base_branch: main",
            f"vault_base_head: {evidence.vault_snapshot.remote_head}",
            f"vault_work_branch: {branch}",
            f"vault_content_commit: {content_commit}",
            "triggered_by: manual-on-demand",
            "operational_authority: none",
            "human_review_required: true",
            "merge_allowed: false",
            f"result: {report.conclusion.value}",
            "risk_level: low",
            "---",
            "",
            "# Informe auditable de propuesta de sincronización",
            "",
            "## Resumen ejecutivo",
            "",
            "El agente detectó un cambio publicado en `Aranwill/jarvis/main`,",
            "preparó una proyección documental en una rama aislada del Vault",
            "y creó primero el commit de contenido indicado en este informe.",
            "La propuesta permanece pendiente de revisión y merge humano.",
            "",
            "## Evidencia fuente",
            "",
            f"- Run ID: `{evidence.execution.run_id}`",
            f"- Generado: `{evidence.execution.generated_at}`",
            f"- Commit base: `{evidence.commit_range.base_commit}`",
            f"- Commit observado: `{evidence.commit_range.head_commit}`",
            f"- Vault base: `{evidence.vault_snapshot.remote_head}`",
            f"- Commit de contenido: `{content_commit}`",
            "",
            "## Cambios detectados en Malāk",
            "",
            changed or "- Ninguno.",
            "",
            "## Documentos candidatos",
            "",
            candidate_lines,
            "",
            "## Archivos modificados por la propuesta",
            "",
            files,
            "",
            "## Archivos deliberadamente no modificados",
            "",
            "- `Aranwill/jarvis`: todo el repositorio.",
            "- `Aranwill/malak-project-vault/main`: sin escritura directa.",
            "- `09-repository-snapshots/`: snapshots históricos intactos.",
            "- Documentos normativos y decisiones: intactos.",
            "",
            "## Cambios bloqueados",
            "",
            "- Cierre automático de decisiones o sprints: `BLOCKED`.",
            "- Modificación de snapshots existentes: `BLOCKED`.",
            "- Aprobación, auto-merge o merge de la PR: `BLOCKED`.",
            "",
            "## Validaciones",
            "",
            "- repositorios, ramas y remotos esperados: `PASS`;",
            "- alineación del Vault con `origin/main`: `PASS`;",
            "- allowlist de documentos candidatos: `PASS`;",
            "- `git diff --check`: `PASS`;",
            f"- conclusión de validación previa: `{report.conclusion.value}`.",
            "",
            "## Riesgos",
            "",
            "- La proyección es derivada y puede requerir ajustes humanos.",
            "- El informe no constituye aprobación ni autoridad operativa.",
            "",
            "## Rollback",
            "",
            "Cerrar la PR sin merge y eliminar su rama restaura el estado",
            "anterior; `main` del Vault y Malāk permanecen intactos.",
            "",
            "## Checklist de revisión humana",
            "",
            "- [ ] Revisar el diff completo.",
            "- [ ] Confirmar los HEAD y el commit de contenido.",
            "- [ ] Verificar que no se cierre ninguna decisión por inferencia.",
            "- [ ] Verificar la inmutabilidad de snapshots.",
            "- [ ] Aprobar o rechazar la PR manualmente.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8", newline="\n")
    return report_path


def _update_audit_index(
    worktree: Path,
    *,
    report_path: str,
    run_id: str,
) -> str:
    index_path = "07-audits/AUDIT_INDEX.md"
    path = worktree / index_path
    content = path.read_text(encoding="utf-8-sig")
    link_target = report_path.removesuffix(".md")
    entry = (
        f"- [[{link_target}|Sincronización {run_id}]]"
    )

    if entry not in content:
        content = content.rstrip() + "\n\n" + entry + "\n"
        path.write_text(content, encoding="utf-8", newline="\n")

    return index_path


def _validate_candidates(
    candidates: tuple[DocumentCandidate, ...],
) -> None:
    for candidate in candidates:
        if not is_allowed_vault_path(candidate.path):
            raise VaultProposalError(
                f"Candidate path is not allowlisted: {candidate.path}"
            )


def _validate_projection_consistency(
    worktree: Path,
    candidates: tuple[DocumentCandidate, ...],
    evidence: EvidenceManifest,
    source_projection: SourceProjection,
) -> None:
    for candidate in candidates:
        path = worktree / candidate.path
        content = path.read_text(encoding="utf-8-sig")

        start = content.find(_MANAGED_START)
        end = content.find(_MANAGED_END)

        if start == -1 or end == -1 or end < start:
            raise VaultProposalError(
                "Projection consistency check failed: managed block missing "
                f"for {candidate.path}."
            )

        actual_block = content[start : end + len(_MANAGED_END)]
        expected_block = _render_projection(
            evidence,
            candidate,
            source_projection,
        )

        if actual_block != expected_block:
            raise VaultProposalError(
                "Projection consistency check failed for "
                f"{candidate.path}."
            )


def _validate_written_projections(
    worktree: Path,
    modified_paths: tuple[str, ...],
) -> None:
    findings: list[ValidationFinding] = []

    for relative_path in modified_paths:
        path = worktree / relative_path
        findings.extend(validate_markdown(path))
        findings.extend(validate_markdown_frontmatter(path))
        findings.extend(validate_relative_links(path, worktree))

    final_findings = tuple(findings)
    if not has_errors(final_findings):
        return

    details = "; ".join(
        f"{finding.code}: {finding.path or 'unknown'}"
        for finding in final_findings
        if finding.severity == "error"
    )
    raise VaultProposalError(
        "Generated Vault projection failed final validation: " + details
    )


def _preflight_github_cli(
    vault_root: Path,
    *,
    github_cli: str,
    branch_prefix: str,
    timeout_seconds: int,
) -> None:
    if shutil.which(github_cli) is None:
        raise VaultProposalError(
            "GitHub CLI was not found. Install and authenticate gh "
            "before enabling controlled proposals."
        )

    _run(
        [github_cli, "auth", "status"],
        cwd=vault_root,
        timeout_seconds=timeout_seconds,
    )
    output = _run(
        [
            github_cli,
            "pr",
            "list",
            "--state",
            "open",
            "--json",
            "headRefName,url",
        ],
        cwd=vault_root,
        timeout_seconds=timeout_seconds,
    )

    try:
        open_prs = json.loads(output)
    except json.JSONDecodeError as exc:
        raise VaultProposalError(
            "GitHub CLI returned invalid PR metadata."
        ) from exc

    pending = [
        item
        for item in open_prs
        if str(item.get("headRefName", "")).startswith(
            f"{branch_prefix}-"
        )
    ]
    if pending:
        raise VaultProposalError(
            "An earlier Vault synchronization PR is still open."
        )


def _verify_source_and_vault_heads(
    evidence: EvidenceManifest,
    *,
    timeout_seconds: int,
) -> None:
    _git(
        evidence.source_snapshot.repository_path,
        "fetch",
        "--quiet",
        "--no-tags",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        timeout_seconds=timeout_seconds,
    )
    _git(
        evidence.vault_snapshot.repository_path,
        "fetch",
        "--quiet",
        "--no-tags",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        timeout_seconds=timeout_seconds,
    )
    source_head = _git(
        evidence.source_snapshot.repository_path,
        "rev-parse",
        "origin/main",
        timeout_seconds=timeout_seconds,
    )
    vault_head = _git(
        evidence.vault_snapshot.repository_path,
        "rev-parse",
        "origin/main",
        timeout_seconds=timeout_seconds,
    )

    if source_head != evidence.commit_range.head_commit:
        raise VaultProposalError(
            "Malak source HEAD changed before proposal publication."
        )
    if vault_head != evidence.vault_snapshot.remote_head:
        raise VaultProposalError(
            "Vault HEAD changed before proposal publication."
        )


def _open_draft_pr(
    worktree: Path,
    *,
    github_cli: str,
    branch: str,
    base_branch: str,
    evidence: EvidenceManifest,
    content_commit: str,
    report_path: str,
    timeout_seconds: int,
) -> str:
    title = (
        "docs(vault): synchronize Malak "
        f"{evidence.commit_range.head_commit[:8]}"
    )
    body = "\n".join(
        [
            "## Propósito",
            "",
            "Proponer una actualización gobernada del Vault a partir de "
            "`Aranwill/jarvis/main`.",
            "",
            "## Evidencia",
            "",
            f"- Run ID: `{evidence.execution.run_id}`",
            f"- Malāk base: `{evidence.commit_range.base_commit}`",
            f"- Malāk HEAD: `{evidence.commit_range.head_commit}`",
            f"- Vault base: `{evidence.vault_snapshot.remote_head}`",
            f"- Commit de contenido: `{content_commit}`",
            f"- Informe: `{report_path}`",
            "",
            "## Gobernanza",
            "",
            "- PR creada como draft.",
            "- Revisión y merge exclusivamente humanos.",
            "- Malāk y `main` del Vault no fueron modificados directamente.",
        ]
    )

    return _run(
        [
            github_cli,
            "pr",
            "create",
            "--draft",
            "--base",
            base_branch,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ],
        cwd=worktree,
        timeout_seconds=timeout_seconds,
    )


def _rollback_published_branch(
    worktree: Path,
    *,
    remote: str,
    branch: str,
    timeout_seconds: int,
) -> None:
    if _BRANCH_PATTERN.fullmatch(branch) is None:
        raise VaultProposalError(
            f"Refusing to roll back an unsafe branch name: {branch}"
        )

    try:
        _git(
            worktree,
            "push",
            remote,
            "--delete",
            branch,
            timeout_seconds=timeout_seconds,
        )
    except VaultProposalError as exc:
        raise VaultProposalError(
            "Draft PR creation failed and the published proposal branch "
            f"could not be rolled back: {branch}."
        ) from exc


def _delete_local_branch(
    vault_root: Path,
    *,
    branch: str,
    timeout_seconds: int,
) -> None:
    if _BRANCH_PATTERN.fullmatch(branch) is None:
        return

    try:
        _git(
            vault_root,
            "branch",
            "--delete",
            "--force",
            branch,
            timeout_seconds=timeout_seconds,
        )
    except VaultProposalError:
        # The proposal result is authoritative even if local housekeeping
        # cannot remove an already detached, agent-owned branch.
        return


def _git(
    cwd: Path,
    *args: str,
    timeout_seconds: int,
) -> str:
    return _run(
        ["git", "-C", str(cwd), *args],
        cwd=cwd,
        timeout_seconds=timeout_seconds,
    )


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> str:
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
        raise VaultProposalError(
            f"Command could not be executed: {command[0]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise VaultProposalError(
            f"Command timed out: {command[0]}"
        ) from exc

    if completed.returncode != 0:
        detail = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "unknown command error"
        )
        raise VaultProposalError(
            f"Command failed: {sanitize_text(detail)}"
        )

    return completed.stdout.strip()
