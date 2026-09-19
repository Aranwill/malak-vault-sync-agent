# Malāk Vault Synchronization Agent

Agente externo y determinista para detectar y auditar cambios entre el
repositorio oficial de Malāk y el Malāk Project Vault.

## Estado

```text
Fase 1 read-only — cerrada
Controlled Vault Proposals — implementado
Modos — dry-run / controlled-proposal
Estado persistente — esquema v3 con reconciliación humana
Incremento 4 — cierre histórico aprobado; no certifica el baseline actual
Incremento Correctivo Integral 5 - validación técnica y operativa completada; cierre documentado pendiente de integración humana
Operación vigente — manual-on-demand, sin scheduler activo
```

El cierre gobernado del Incremento 4 se documenta en
[docs/INCREMENT_4_CLOSURE.md](docs/INCREMENT_4_CLOSURE.md).

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

## Frontera externa respecto de Malāk

El Sync Agent y el Project Vault son infraestructura auxiliar **externa** a
Malāk. No forman parte de su arquitectura, runtime, memoria, knowledge,
Kernel, capabilities ni contratos internos.

La dirección permitida es exclusivamente:

```text
Malāk repository
      ↓ observed externally
Sync Agent
      ↓ maintains
Project Vault
      ↓ supports
assistant context
```

No existe dependencia inversa.

Invariantes:

- Malāk no importa, invoca ni consulta al Sync Agent;
- Malāk no importa, invoca ni consulta al Project Vault;
- el Project Vault no es memoria de Malāk;
- el Project Vault no es una fuente de knowledge de Malāk;
- el Sync Agent no es una capability, tool, agent interno ni componente del
  runtime de Malāk;
- ninguna función nueva del Sync Agent debe requerir cambios en Malāk para que
  Malāk "conozca" al Agent o al Vault;
- la observación del repositorio de Malāk es externa y unilateral;
- cualquier mención histórica en artefactos de desarrollo/auditoría no
  constituye dependencia arquitectónica ni autoridad vigente.

Esta frontera es obligatoria para futuras ampliaciones del Agent.

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
6. validan rutas, Markdown, frontmatter YAML, enlaces Markdown y wikilinks;
7. generan evidencia e informe con SHA-256;
8. en `dry-run`, finalizan sin modificar el Vault;
9. en `controlled-proposal`, validan nuevamente la proyección final,
   crean el commit documental, el informe y commit de auditoría, realizan
   push y abren una PR draft;
10. guardan el nuevo estado solo después de completar el circuito.

El estado v3 separa observación, reconciliación y propuesta pendiente:

- `last_observed_commit` registra el último HEAD auditado por
  `dry-run`;
- `last_reconciled_commit` registra el último commit de Malāk cuya
  propuesta fue aceptada o cuya base fue preservada tras un rechazo;
- `pending_proposal_base_commit` y `pending_proposal_commit` delimitan
  el rango sujeto a decisión humana;
- `pending_proposal_vault_commit` y
  `pending_proposal_pull_request_url` fijan la identidad original de la
  propuesta (HEAD del Vault publicado por el agente + URL), no una identidad
  de contenido del resultado final mergeado.

Por esa separación, una previsualización `dry-run` no consume el rango
pendiente. Una ejecución posterior en `controlled-proposal` vuelve a
evaluar ese mismo rango. Una propuesta creada queda pendiente y bloquea
nuevas propuestas hasta que el humano la acepte o rechace.

El bootstrap de `controlled-proposal` establece el primer cursor
reconciliado sin crear una propuesta retrospectiva. Si una PR draft fue
creada pero la persistencia local falló, la siguiente ejecución recupera
su identidad únicamente cuando rama, base, HEAD, cuerpo y estado remoto
coinciden de forma unívoca; después se detiene para exigir reconciliación
humana.

Los estados v1 y v2 se interpretan como v3 sin escritura automática. Si
contienen una propuesta histórica, `run-once`, `accept-proposal` y
`reject-proposal` permanecen bloqueados hasta completar la reconciliación
migrada explícita. No se debe editar el JSON manualmente.

## Trigger de reconciliación post-merge

El modo operativo continúa siendo `manual-on-demand`, pero un merge en
`Aranwill/jarvis/main` que afecte rutas observadas o mapeadas constituye un
trigger explícito para evaluar sincronización.

Flujo esperado:

```text
merge en jarvis/main
        ↓
evaluar rutas modificadas
        ↓
dry-run
        ↓
review de findings / candidatos
        ↓
controlled-proposal cuando corresponda
        ↓
revisión humana
        ↓
reconciliación de estado
```

La existencia del trigger:

- no convierte al Sync Agent en scheduler;
- no ejecuta sincronización automáticamente;
- no reabre un Sprint ya cerrado;
- no convierte al Vault en fuente de verdad;
- no concede autoridad al Sync Agent;
- no permite ocultar un fallo como reconciliación exitosa.

Si la sincronización falla, `Aranwill/jarvis/main` continúa siendo la fuente
oficial y el drift debe permanecer visible y clasificable.

Cuando la proyección derivada vaya a utilizarse para una nueva admission review
de Malāk, los `BASELINE_DRIFT`, `PROJECTION_DRIFT`, `STATE_DRIFT` o drifts
semánticos relevantes conocidos deben estar reconciliados, resueltos o
aceptados explícitamente como riesgo documentado. Esta condición pertenece a
la disciplina de planificación de Malāk; el Sync Agent no la autoimpone como
autoridad sobre el proyecto.

## Reconciliar una propuesta

Para una propuesta v3 ordinaria, después de revisar su PR:

```powershell
malak-vault-sync accept-proposal `
  --config .\config\vault-sync.yaml `
  --expected-commit <SHA_MALAK>
```

o, tras cerrar la PR sin merge:

```powershell
malak-vault-sync reject-proposal `
  --config .\config\vault-sync.yaml `
  --expected-commit <SHA_MALAK>
```

Para una propuesta recuperada desde un archivo original v1 o v2, usar
únicamente el comando gobernado de migración:

```powershell
malak-vault-sync reconcile-migrated-proposal `
  --config .\config\vault-sync.yaml `
  --decision accept `
  --expected-base-commit <SHA_BASE_MALAK> `
  --expected-commit <SHA_PROPUESTO_MALAK> `
  --proposal-vault-commit <SHA_CABECERA_PR_VAULT> `
  --pull-request-url <URL_PR_VAULT>
```

El comando exige una decisión humana y evidencia completa, consulta
GitHub bajo lock y persiste v3 solo si la identidad remota satisface las
reglas de reconciliación. El commit original de propuesta debe coincidir con
el HEAD observado o, si el HEAD final cambió, ser ancestro del HEAD final de
una PR mergeada.

Esta comprobación demuestra identidad y lineage de la propuesta. No compara
el árbol, el diff ni el contenido final mergeado contra una identidad de
contenido previamente revisada y no debe interpretarse como certificación de
equivalencia semántica o byte-a-byte.

La guía de migración y rollback está en
`docs/STATE_V3_MIGRATION_AND_RECONCILIATION.md`.

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
- reconciliación v1/v2 explícita, sin inferir decisión ni identidad;
- recuperación unívoca de una PR creada antes de un fallo de persistencia;
- identificadores de ejecución con microsegundos;
- credenciales sanitizadas en evidencia e informes;
- `09-repository-snapshots/` fuera del allowlist y de toda escritura.

## Operación manual

El modo operativo aprobado es `manual-on-demand`: el propietario invoca
`run-once` después de una sesión de trabajo, después de un merge relevante o
cuando decide auditar un cambio publicado. No existe scheduler activo ni
ejecución residente.

El script `scripts/install-scheduled-task.ps1` se conserva solo como
artefacto histórico y capacidad opcional no habilitada. Activarlo requiere
una decisión humana nueva y explícita; no forma parte del baseline vigente.

La especificación operativa completa se encuentra en
`docs/CONTROLLED_VAULT_PROPOSALS.md`.

## Pruebas

```powershell
python -m pytest
python -m compileall .\src .\tests
git diff --check
```

GitHub Actions repite estas validaciones en Linux y Windows en cada pull
request y en cada cambio integrado a `main`.

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