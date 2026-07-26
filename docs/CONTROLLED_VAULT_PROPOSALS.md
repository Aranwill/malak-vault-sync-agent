# Propuestas controladas del Vault

## Propósito

El modo `controlled-proposal` extiende la observación read-only sin
conceder autoridad de decisión ni merge al agente.

Ante un cambio publicado en `Aranwill/jarvis/main`, el agente:

1. actualiza las referencias remotas y, si el clon limpio del Vault quedó
   detrás, avanza su `main` local únicamente mediante `fast-forward`;
2. compara el nuevo HEAD con el último commit observado;
3. resuelve únicamente documentos candidatos allowlisted;
4. genera evidencia e informe local;
5. crea un worktree temporal desde `origin/main` del Vault;
6. incorpora en cada candidato una proyección determinista del estado
   oficial, los commits observados y la ficha de sprint más reciente;
7. crea el commit documental;
8. genera un informe auditable que referencia ese commit;
9. crea un segundo commit con el informe y su entrada en el índice;
10. ejecuta `push` sobre una rama `agent/vault-sync-<SHA8>`;
11. abre una PR draft mediante GitHub CLI;
12. guarda el nuevo estado local únicamente después de completar el
    circuito.

El agente nunca escribe en `Aranwill/jarvis`, nunca escribe
directamente en `main` del Vault y nunca aprueba o mergea la PR.

## Requisitos

- Python 3.12 o superior;
- Git;
- GitHub CLI (`gh`) instalado y autenticado;
- permisos de lectura sobre `Aranwill/jarvis`;
- permisos para crear ramas, commits, push y PR draft en
  `Aranwill/malak-project-vault`;
- clones locales limpios y ubicados en `main`;
- historial local del Vault compatible con un `fast-forward` hacia
  `origin/main`.

Validar GitHub CLI:

```powershell
gh --version
gh auth status
```

## Configuración

En el archivo privado `config/vault-sync.yaml`:

```yaml
schema_version: 1
mode: controlled-proposal

proposal:
  branch_prefix: agent/vault-sync
  push: true
  open_draft_pr: true
  github_cli: gh
```

Los demás campos permanecen iguales al ejemplo versionado.

La configuración rechaza:

- escritura sin push;
- propuestas sin PR draft;
- otro prefijo de rama;
- otro ejecutable para GitHub;
- cualquier repositorio o rama fuera de la allowlist.

## Primera ejecución

La primera ejecución conserva el comportamiento de bootstrap: registra
el HEAD observado y no crea una propuesta retrospectiva.

```powershell
malak-vault-sync run-once `
  --config .\config\vault-sync.yaml
```

Las ejecuciones posteriores solo crean una PR cuando:

- cambió `Aranwill/jarvis/main`;
- existen candidatos documentales allowlisted;
- no hay errores de validación;
- no existe otra PR de sincronización abierta.

Si el `push` de una propuesta funciona pero GitHub CLI no puede crear la
PR draft, el agente elimina únicamente la rama remota de esa ejecución y
no persiste el nuevo estado observado. La siguiente corrida puede
reintentarlo sin reutilizar una rama huérfana.

## Detección programada

El script `scripts/install-scheduled-task.ps1` instala una tarea del
Programador de tareas de Windows para invocar `run-once` periódicamente.
La tarea no ejecuta un daemon y no mantiene procesos residentes.

Ejemplo:

```powershell
.\scripts\install-scheduled-task.ps1 `
  -ProjectPath D:\Ollama\malak-vault-sync-agent `
  -ConfigPath D:\Ollama\malak-vault-sync-agent\config\vault-sync.yaml `
  -PythonPath D:\Ollama\malak-vault-sync-agent\.venv\Scripts\python.exe `
  -IntervalMinutes 15
```

La instalación falla si ya existe una tarea con el mismo nombre. Esto
impide reemplazar silenciosamente una configuración operativa.

## Human in Control

Cada PR permanece en estado draft. El propietario debe revisar:

- ambos commits;
- el informe auditable;
- los HEAD registrados;
- las proyecciones incorporadas;
- el diff completo;
- los cambios bloqueados;
- los riesgos y el rollback.

Solo el propietario puede aprobar y mergear.

## Rollback

Para detener nuevas detecciones:

```powershell
Disable-ScheduledTask -TaskName MalakVaultSyncAgent
```

Para revertir una propuesta no aprobada, cerrar la PR sin merge. Malāk y
`main` del Vault permanecen intactos.
