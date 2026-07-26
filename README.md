# Malāk Vault Synchronization Agent

Agente externo y determinista para detectar y auditar cambios entre el
repositorio oficial de Malāk y el Malāk Project Vault.

## Estado

```text
Fase 1 read-only — cerrada
Controlled Vault Proposals — implementado
Modos — dry-run / controlled-proposal
```

El agente puede actualizar referencias remotas, detectar cambios nuevos en
`Aranwill/jarvis/main`, generar evidencia verificable, resolver documentos
candidatos y validar el Vault.

En `controlled-proposal` también puede preparar una actualización
determinista del Vault en una rama aislada, crear primero el commit
documental, generar después el informe auditable, crear el commit de
auditoría, ejecutar push y abrir una PR draft.

## Autoridad

```text
Agente:
observa, compara, valida, registra estado y propone cambios documentales

LLM:
no utilizado

Humano:
revisa el diff y conserva toda autoridad de aprobación y merge
```

El agente no puede:

- modificar `Aranwill/jarvis`;
- escribir directamente en `main` del Vault;
- aprobar o fusionar pull requests;
- modificar snapshots históricos;
- cerrar decisiones;
- utilizar LLM;
- integrarse con el Kernel o runtime de Malāk.

## Repositorios observados

| Rol | Repositorio | Rama | Acceso |
|---|---|---|---|
| Fuente operativa | `Aranwill/jarvis` | `main` | fetch e inspección |
| Vault derivado | `Aranwill/malak-project-vault` | `main` | lectura; propuesta en rama aislada cuando se habilita |

`fetch` actualiza únicamente referencias remotas de Git. El modo
`controlled-proposal` puede avanzar el `main` local y limpio del Vault
solo mediante `fast-forward`; las propuestas se crean en un worktree
temporal y nunca escriben directamente en `main` remoto.

## Requisitos

- Python 3.12 o superior;
- Git disponible localmente;
- clones locales de ambos repositorios;
- acceso de lectura a ambos remotos;
- GitHub CLI autenticado y permisos de propuesta sobre el Vault para
  `controlled-proposal`;
- working trees en `main` y limpios;
- historial local del Vault compatible con un `fast-forward` hacia
  `origin/main`.

## Instalación de desarrollo

```powershell
cd D:\Ollama\malak-vault-sync-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Configuración local

Copiar el ejemplo sin publicarlo:

```powershell
Copy-Item `
  .\config\vault-sync.example.yaml `
  .\config\vault-sync.yaml
```

Revisar especialmente:

```yaml
source:
  local_path: D:/Ollama/jarvis
  remote: origin
  branch: main
  fetch: true

vault:
  local_path: D:/Ollama/malak-project-vault
  remote: origin
  branch: main
  fetch: true
```

`config/vault-sync.yaml` y `var/` están excluidos de Git.

## Validar configuración

```powershell
malak-vault-sync validate-config `
  --config .\config\vault-sync.yaml
```

Código de salida:

- `0`: configuración válida;
- `2`: configuración inválida.

## Ejecutar una observación

```powershell
malak-vault-sync run-once `
  --config .\config\vault-sync.yaml
```

La primera ejecución crea un baseline local:

```text
bootstrap: true
changed_files: 0
```

Las ejecuciones posteriores:

1. actualizan `origin/main` de ambos repositorios;
2. verifican identidad, rama, limpieza y alineación;
3. comparan el cursor correspondiente al modo con el HEAD remoto de
   Malāk;
4. detectan modificaciones, altas, bajas y renombres;
5. resuelven documentos candidatos del Vault;
6. validan rutas, Markdown, YAML y enlaces;
7. generan evidencia e informe con SHA-256;
8. en `dry-run`, finalizan sin modificar el Vault;
9. en `controlled-proposal`, crean el commit documental, el informe y
   commit de auditoría, realizan push y abren una PR draft;
10. guardan el nuevo estado solo después de completar el circuito.

El estado separa dos cursores:

- `last_observed_commit` registra el último HEAD auditado por
  `dry-run`;
- `last_proposed_commit` registra hasta qué commit se evaluó
  correctamente una propuesta controlada.

Por esa separación, una previsualización `dry-run` no consume el rango
pendiente. Una ejecución posterior en `controlled-proposal` vuelve a
evaluar ese mismo rango y solo avanza su cursor cuando termina sin una
conclusión `fail`. Los estados de esquema 1 se migran automáticamente al
esquema 2; si existe el backup atómico `.prev`, se usa para recuperar el
inicio pendiente de la última previsualización.

Salidas locales:

```text
var/state/sync-state.json
var/state/sync-state.json.prev
var/evidence/<run_id>/
var/reports/<run_id>/
```

Códigos de salida:

- `0`: ejecución completada con `pass` o `pass_with_findings`;
- `1`: auditoría completada con conclusión `fail`;
- `2`: error operativo o de seguridad; el estado no avanza.

## Controles operativos

- comandos Git y combinaciones de argumentos allowlisted;
- identidad exacta de ambos remotos;
- timeout aplicado a todas las operaciones Git;
- límite de archivos modificados;
- límite total del paquete de evidencia;
- límite de tamaño por documento candidato;
- lock de ejecución;
- estado escrito de forma atómica con backup;
- identificadores de ejecución con microsegundos;
- credenciales sanitizadas en evidencia e informes;
- snapshots históricos del Vault fuera del allowlist.

## Automatización

El comando `run-once` puede ser invocado por el Programador de tareas de
Windows. El script `scripts/install-scheduled-task.ps1` instala una
invocación periódica sin mantener un daemon o servicio residente.

El scheduler no concede autoridad adicional. En `controlled-proposal`,
cada cambio relevante produce una PR draft y el merge continúa reservado
al propietario.

La especificación operativa completa se encuentra en
`docs/CONTROLLED_VAULT_PROPOSALS.md`.

## Pruebas

```powershell
python -m pytest
python -m compileall .\src .\tests
git diff --check
```

GitHub Actions repite estas validaciones en cada pull request y en cada cambio
integrado a `main`.

## Historial de Gates

```text
Gate 0 — relevamiento de solo lectura
Gate 1 — workspace y configuración
Gate 2 — inspección Git de solo lectura
Gate 3 — estado persistente local
Gate 4 — paquete de evidencia
Gate 5 — resolución de documentos candidatos
Gate 6 — validadores deterministas
Gate 7 — informe de auditoría
Gate 8 — runner, lock y polling externo
Gate 9 — validación final de Fase 1
Operational Gate 1 — CLI run-once
Operational Gate 2 — detección remota segura
Operational Gate 3 — persistencia y límites
Operational Gate 4 — reglas y renombres
Operational Gate 5 — validación end-to-end
```
