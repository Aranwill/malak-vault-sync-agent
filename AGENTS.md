# AGENTS.md — Instrucciones del Malāk Vault Synchronization Agent

## Propósito

Este archivo define las reglas operativas que deben seguir asistentes, agentes,
scripts y herramientas al trabajar en el repositorio
`malak-vault-sync-agent`.

Estas instrucciones gobiernan el desarrollo, revisión y mantenimiento del Sync
Agent. No reemplazan ni reinterpretan las fuentes normativas de Malāk ni la
gobernanza del Project Vault.

## Regla persistente de idioma

- Todas las respuestas al propietario del proyecto deben estar en español.
- Toda documentación nueva debe redactarse en español.
- Los análisis, planes, findings, informes y propuestas deben estar en español.
- Los identificadores técnicos, rutas, nombres de clases, funciones, comandos y
  APIs existentes pueden mantenerse en inglés.
- No se deben traducir identificadores cuando hacerlo reduzca trazabilidad o
  consistencia.
- Cuando una fuente esté en inglés, su contenido debe explicarse en español.

## Raíz del repositorio

La raíz Git efectiva del Sync Agent es:

```text
D:\Ollama\malak-vault-sync-agent
```

Ejecuta Git, tests y validaciones desde este directorio salvo que una tarea
aprobada requiera explícitamente otra ubicación.

## Identidad y rol

- Repositorio: `Aranwill/malak-vault-sync-agent`
- Rama base permanente: `main`
- Fuente observada: `Aranwill/jarvis/main`
- Destino derivado: `Aranwill/malak-project-vault/main`
- Operación vigente: `manual-on-demand`
- Modos: `dry-run` y `controlled-proposal`
- LLM dentro del Sync Agent: no autorizado / no utilizado
- Autoridad de aprobación o merge: ninguna

Principio rector:

> **El Sync Agent observa, compara, valida, documenta y propone. No decide por
> la fuente, no gobierna el Vault y no sustituye al Owner.**

## Modelo de autoridad

La relación de autoridad es:

```text
Malāk / Aranwill/jarvis/main
        ↓
source of truth
        ↓
Sync Agent
        ↓
deterministic observation / mapping / validation / proposal
        ↓
Project Vault
        ↓
derived projection
        ↓
Owner review and decision
```

El Sync Agent no puede:

- modificar `Aranwill/jarvis`;
- alterar la autoridad documental de Malāk;
- escribir directamente en `main` remoto del Vault;
- aprobar Pull Requests;
- mergear Pull Requests;
- promover Pull Requests a `Ready for Review`;
- modificar snapshots históricos;
- cerrar decisiones de arquitectura o gobernanza;
- utilizar LLM para decidir mappings o contenido;
- integrarse con Kernel, Planner, runtime o Cognitive Core de Malāk;
- convertir una detección en autorización.

## Fuentes obligatorias antes de cambios materiales

Antes de modificar comportamiento, mappings, estado, propuestas o validadores,
lee según aplicabilidad:

```text
README.md
docs/CONTROLLED_VAULT_PROPOSALS.md
docs/STATE_V3_MIGRATION_AND_RECONCILIATION.md
config/vault-sync.example.yaml
src/malak_vault_sync/candidate_resolver.py
src/malak_vault_sync/runner.py
src/malak_vault_sync/proposal_reconciliation.py
src/malak_vault_sync/git_inspector.py
src/malak_vault_sync/evidence.py
tests/**
```

Cuando la tarea dependa de la semántica de una fuente de Malāk o del Vault,
consulta también los repositorios correspondientes.

## Revisión integral del Sync Agent

Cuando la tarea solicite revisar el estado del agente, validar cobertura,
detectar drift, reconciliar repositorios o determinar próximos pasos, la
revisión no deberá limitarse a `README.md`.

### Minimum Review Set

Salvo que el alcance solicitado sea explícitamente menor, una revisión integral
deberá considerar, según aplicabilidad:

```text
Sync Agent
├── AGENTS.md
├── README.md
├── config/**
├── docs/**
├── src/malak_vault_sync/**
├── tests/**
├── pyproject.toml
├── .github/**
└── HEAD / estado Git

Malāk — source of truth
├── AGENTS.md
├── fuentes normativas aplicables
├── baseline vigente
├── docs/project/concepts/**
├── documents/projects/jarvis/ideas.md cuando corresponda
├── ADR / decisiones aplicables
└── rutas nuevas o modificadas desde el último rango reconciliado

Project Vault — destino derivado
├── AGENTS.md
├── 00-governance/**
├── 02-current-baseline/**
├── 08-session-context/**
├── 10-knowledge-index/**
├── mappings/proyecciones afectadas
└── HEAD / estado Git
```

La profundidad de lectura debe ser proporcional al problema. No es obligatorio
leer todos los archivos completos si evidencia suficiente puede obtenerse de
secciones concretas, pero ninguna fuente relevante puede omitirse
silenciosamente.

## Comportamiento vigente del agente

El modo `dry-run`:

- observa;
- actualiza referencias remotas autorizadas;
- compara commits;
- detecta cambios;
- resuelve candidatos;
- valida;
- genera evidencia;
- genera informe;
- no modifica el Vault.

El modo `controlled-proposal` puede, dentro de sus límites aprobados:

- actualizar `main` local limpio del Vault únicamente mediante fast-forward;
- crear un worktree temporal desde `origin/main`;
- preparar cambios deterministas en candidatos allowlisted;
- validar la proyección final;
- crear commits documentales y de auditoría;
- hacer push a una rama `agent/vault-sync-<SHA8>`;
- abrir una Pull Request en estado `Draft`;
- persistir estado v3 únicamente después de completar el circuito.

Ninguno de esos comportamientos concede autoridad de decisión.

## Estado v3 y propuestas pendientes

La semántica del estado v3 debe preservarse.

Campos relevantes:

```text
last_observed_commit
last_reconciled_commit
pending_proposal_base_commit
pending_proposal_commit
pending_proposal_vault_commit
pending_proposal_pull_request_url
```

Reglas:

- `dry-run` puede avanzar observación sin consumir el rango todavía no
  reconciliado;
- `controlled-proposal` debe partir del último commit reconciliado;
- una propuesta pendiente bloquea nuevas propuestas;
- una PR creada pero no persistida debe recuperarse solo mediante identidad
  unívoca y verificable;
- estados v1/v2 no deben migrarse inventando evidencia;
- no se edita `sync-state.json` manualmente para forzar reconciliación.

## Discovery de nuevas rutas y cobertura

La incorporación de archivos, carpetas o familias documentales nuevas en Malāk
debe considerarse un evento de cobertura.

Principio:

> **La ausencia de una ruta en las reglas actuales de mapping no implica que la
> ruta sea irrelevante.**

Cuando aparezca una nueva ruta de Malāk que no sea reconocida por ninguna regla
vigente, deberá evaluarse explícitamente.

Flujo conceptual:

```text
new source path
      ↓
known by existing mapping?
  ├── yes
  │    ↓
  │ apply existing rule
  │
  └── no
       ↓
   classify relevance
       ↓
   determine disposition
       ├── explicitly ignored
       ├── protected
       ├── already represented elsewhere
       ├── not applicable
       └── mapping candidate
                ↓
          COVERAGE_DRIFT
                ↓
          document evidence
                ↓
          propose mapping
                ↓
          HUMAN_REVIEW_REQUIRED
```

### Información mínima para una ruta nueva

Cuando una ruta nueva sea relevante, la evaluación deberá documentar como
mínimo:

```text
source_path
change_type
classification
existing_mapping
coverage_status
source_authority
affected_projection
proposed_mapping
proposed_vault_target
reason
evidence
risk
human_review_required
```

Ejemplo conceptual:

```text
source_path:
docs/project/concepts/NEW_ENGINEERING_REFERENCE.md

classification:
conceptual_reference

existing_mapping:
NONE

coverage_status:
COVERAGE_DRIFT

proposed_mapping:
docs/project/concepts/**
→ 10-knowledge-index/CONCEPTUAL_FOUNDATIONS.md

proposed_vault_target:
10-knowledge-index/CONCEPTUAL_FOUNDATIONS.md
10-knowledge-index/KNOWLEDGE_INDEX.md

decision:
HUMAN_REVIEW_REQUIRED
```

## Frontera entre discovery y modificación del mapping

El Sync Agent o una revisión del Sync Agent puede:

```text
detectar nueva ruta                     YES
reconocer naturaleza                    YES
evaluar autoridad y relevancia          YES
detectar falta de cobertura             YES
formular mapping candidato              YES
documentar evidencia                    YES
proponer destino derivado               YES
reportar COVERAGE_DRIFT                 YES
```

No puede:

```text
ampliar mapping silenciosamente          NO
autoaprobar nueva cobertura              NO
inventar destino sin evidencia           NO
crear nueva autoridad documental         NO
reescribir Malāk para ajustar mapping    NO
ocultar finding agregando una regla      NO
```

Toda ampliación material de `_DEFAULT_RULES`, `_ALLOWED_VAULT_PATHS`, patrones
ignorados o reglas equivalentes debe tratarse como cambio de comportamiento del
Sync Agent y requiere alcance, tests, revisión y aprobación humana.

## Importante: AGENTS.md no implementa discovery automático

Estas instrucciones establecen la obligación de detectar y evaluar cobertura
durante el desarrollo, revisión y evolución del Sync Agent.

Por sí solas no convierten el runtime actual en un detector automático de rutas
no mapeadas.

Si se desea que `run-once` emita programáticamente `COVERAGE_DRIFT` para toda
ruta nueva no reconocida, esa capacidad deberá implementarse en un cambio
separado y aprobado, con especificación, tests y evidencia.

No se debe presentar una regla documental como si ya fuese una capability
implementada.

## Candidate Resolver y mappings

`src/malak_vault_sync/candidate_resolver.py` contiene reglas deterministas que
relacionan familias de rutas fuente con candidatos allowlisted del Vault.

Al revisar cambios en mappings, comprobar como mínimo:

```text
source pattern
rule_id
priority
vault candidate
allowlist
denylist
ignored patterns
rename handling
determinism
tests
```

El mapping deberá ser:

- explícito;
- determinista;
- trazable;
- estable;
- mínimo;
- consistente con autoridad;
- compatible con la estructura real del Vault.

No se debe usar similitud semántica o una decisión probabilística para determinar
qué archivo del Vault puede ser modificado.

## Rutas conceptuales

La familia:

```text
docs/project/concepts/**
```

debe mantenerse reconocida como fuente conceptual.

Su proyección derivada vigente incluye:

```text
10-knowledge-index/CONCEPTUAL_FOUNDATIONS.md
10-knowledge-index/KNOWLEDGE_INDEX.md
```

Una referencia conceptual:

```text
NO es baseline
NO autoriza implementación
NO autoriza sprint
NO adquiere autoridad normativa por ser proyectada
```

El mapping debe preservar esta naturaleza.

## Taxonomía mínima de drift

Cuando sea posible, clasifica findings mediante:

```text
SYNC_DRIFT
COVERAGE_DRIFT
PROJECTION_DRIFT
BASELINE_DRIFT
DOCUMENTATION_DRIFT
CONCEPTUAL_DRIFT
AUTHORITY_DRIFT
ENCODING_DRIFT
STATE_DRIFT
```

Definiciones:

```text
SYNC_DRIFT
→ el comportamiento del Sync Agent no representa correctamente el cambio que
  sus reglas deberían detectar o proyectar.

COVERAGE_DRIFT
→ existe una ruta o familia documental relevante sin una regla de mapping
  aplicable ni una exclusión explícita justificada.

PROJECTION_DRIFT
→ el candidato del Vault no representa correctamente la fuente observada.

BASELINE_DRIFT
→ una proyección o estado describe un baseline distinto del oficial vigente.

DOCUMENTATION_DRIFT
→ documentación del agente, de Malāk o del Vault no coincide con el
  comportamiento o estado verificable aplicable.

CONCEPTUAL_DRIFT
→ una referencia conceptual no está cubierta o está representada de forma
  incorrecta.

AUTHORITY_DRIFT
→ un artefacto derivado o una propuesta recibe autoridad superior a la que
  corresponde.

ENCODING_DRIFT
→ contenido textual presenta corrupción o transformación inesperada de
  caracteres o line endings con impacto observable.

STATE_DRIFT
→ estado persistido, propuesta pendiente, PR remota o cursores no representan
  de forma coherente la realidad verificable.
```

Todo finding debería incluir:

```text
type
source
observed_state
expected_state
evidence
impact
recommended_action
human_review_required
```

Detectar drift no concede autorización para corregirlo.

## No ampliar mappings para silenciar findings

Una ruta nueva no debe añadirse automáticamente a un patrón amplio solo para
eliminar `COVERAGE_DRIFT`.

Antes de ampliar una regla, evaluar:

1. naturaleza de la fuente;
2. autoridad;
3. relación con el Vault;
4. destino apropiado;
5. riesgo de capturar rutas no relacionadas;
6. prioridad;
7. tests;
8. impacto sobre evidencia y propuestas futuras.

Preferir patrones específicos sobre comodines excesivamente amplios.

## Paths protegidos y denylist

La denylist y los paths fuera del allowlist deben tratarse como límites de
seguridad.

En particular:

```text
09-repository-snapshots/**
.git/**
var/**
.env
secret material
credentials
private keys
```

no deben transformarse en candidatos de escritura por conveniencia.

Modificar allowlists o denylists requiere revisión explícita.

## Propuestas controladas y worktree efímero

`controlled-proposal` debe mantener separación entre:

```text
source repository
        ↓
read / inspect only

temporary Vault worktree
        ↓
candidate edits and validation

remote proposal branch
        ↓
Draft PR

Owner
        ↓
review / decision
```

El worktree temporal no concede autoridad sobre `main`.

Una falla durante una propuesta debe preservar rollback y no dejar un estado
ambiguo que permita duplicar propuestas.

## Pull Requests siempre en Draft

Todo Pull Request creado por el Sync Agent, asistentes o automatizaciones debe
nacer en estado `Draft`.

El agente puede abrir Draft PR cuando su modo aprobado lo permita.

La transición:

```text
Draft
→ Ready for Review
```

es exclusivamente humana y manual desde la interfaz de GitHub.

El Sync Agent, asistentes y automatizaciones:

- no pueden promover el PR;
- no pueden ejecutar CLI, API o connector para promoverlo;
- no pueden inferir permiso de una expresión verbal de conformidad;
- no pueden sustituir la revisión visual del Owner.

Principio:

> **Author != Reviewer != Authority.**

## Reconciliación humana

`accept-proposal` o `reject-proposal` no deben inferir una decisión humana.

Antes de avanzar o limpiar estado pendiente, deben verificar la evidencia remota
definida por el protocolo vigente.

Una PR abierta no equivale a aceptación.

Una PR `Ready for Review` no equivale a aceptación.

Tests verdes no equivalen a aceptación.

Solo el estado remoto verificable y la decisión humana correspondiente pueden
habilitar la reconciliación prevista.

## Git y operaciones sensibles

No realizar sin autorización explícita:

- crear, cambiar o eliminar ramas del repositorio del Sync Agent;
- commit;
- push;
- merge;
- rebase;
- reset;
- tags;
- stash;
- crear o actualizar materialmente Pull Requests del repositorio del agente;
- eliminar archivos;
- reescribir historial.

No utilizar operaciones destructivas para limpiar trabajo preexistente.

Preservar modificaciones locales y untracked no relacionados.

## Cambios que afectan el comportamiento del agente

Se consideran cambios materiales, entre otros:

- `_DEFAULT_RULES`;
- `_ALLOWED_VAULT_PATHS`;
- `_DENIED_VAULT_PATTERNS`;
- `_EXPLICITLY_IGNORED_SOURCE_PATTERNS`;
- lógica de candidate resolution;
- Git allowlists;
- límites operativos;
- validación de repositorios/remotos;
- estado v3;
- reconciliación;
- recuperación de propuestas;
- worktree;
- push;
- PR creation;
- sanitización de evidencia;
- locking;
- permisos;
- scheduler.

Estos cambios requieren especificación y tests proporcionales antes de
considerarse aceptables.

## Testing

Cuando se modifique código Python, ejecutar como base:

```powershell
python -m pytest
python -m compileall .\src .\tests
git diff --check
```

Agregar pruebas específicas cuando se modifiquen mappings o discovery.

Para un nuevo mapping, probar como mínimo:

```text
matching positive case
non-matching negative case
rename case when applicable
priority
candidate allowlist
denied path rejection
deterministic ordering
no unrelated candidate expansion
```

Para una futura implementación automática de `COVERAGE_DRIFT`, probar además:

```text
unmapped relevant path → finding
explicitly ignored path → no false positive
mapped path → no coverage finding
protected path → protected classification
rename old/new path handling
deterministic evidence
no automatic rule mutation
```

## Validación proporcional sin loops

La validación se organiza en gates.

### Gate 1 — después de editar

Solo cuando el contenido cambió:

```text
revisión del diff
git diff --check
UTF-8 / caracteres especiales
tests específicos cuando corresponda
```

### Gate 2 — después de staging

Una vez por contenido staged:

```text
git diff --cached --check
scope / changed files
working tree == staged blob
```

### Gate 3 — antes de push

Una vez por el commit que será publicado:

```text
working tree esperado
scope final
UTF-8 de archivos afectados
diff final
tests aplicables si el commit cambió desde el último gate
```

Regla antirredundancia:

> **Si un artefacto no cambió desde un gate que ya pasó, no repitas la misma
> validación únicamente por rutina.**

Repite un gate únicamente cuando:

- cambió el archivo;
- cambió el staged blob;
- cambió el commit;
- cambió el entorno de validación de forma relevante;
- nueva evidencia invalida la validación previa.

## Disciplina UTF-8

Todos los archivos textuales creados o modificados deben conservar UTF-8 y
caracteres especiales correctos.

PowerShell:

```powershell
Get-Content <archivo> -Raw -Encoding UTF8
```

Detección de indicadores comunes de mojibake:

```powershell
$mojibakePattern = '{0}|{1}|{2}' -f [char]0x00C3, [char]0x00C2, [char]0xFFFD

Get-Content <archivo> -Raw -Encoding UTF8 |
    Select-String -Pattern $mojibakePattern
```

La salida esperada es vacía.

`git diff --check` no sustituye la validación de encoding.

## Line endings y ruido de metadata

Una advertencia LF/CRLF no demuestra por sí sola corrupción.

Si Git marca un archivo como modificado pero no existe diff de contenido:

1. comparar working tree e index por hash;
2. inspeccionar `git ls-files --eol`;
3. revisar atributos;
4. distinguir contenido de metadata/stat noise.

No descartar un archivo para limpiar un `M` antes de probar identidad de
contenido.

Cambios a `.gitattributes` o política global EOL requieren un alcance separado.

## Scope discipline

No aprovechar una tarea documental para modificar:

- mappings;
- Python;
- configuración;
- estado persistido;
- scripts;
- CI;
- scheduler;
- allowlists;
- denylists.

Si la revisión revela un cambio necesario fuera de scope, documentarlo y
proponerlo por separado.

## Regla de no auto-evolución

El Sync Agent puede detectar que sus mappings son insuficientes.

Puede documentar:

```text
current rule
missing coverage
candidate rule
candidate destination
evidence
expected tests
risk
```

Pero no debe modificar automáticamente su propio código o configuración para
resolver esa deficiencia.

Una futura capability de autoevaluación deberá conservar esta separación:

```text
observe
→ detect gap
→ propose
→ human authorization
→ implementation
→ validation
```

Nunca:

```text
observe
→ silently rewrite mapping
```

## Finalización

Todo cambio material debe informar:

- archivos modificados;
- comportamiento afectado;
- fuentes consultadas;
- mappings afectados;
- cobertura;
- findings de drift;
- tests;
- encoding;
- estado Git;
- riesgo;
- rollback;
- incertidumbre restante.

## Rollback

El rollback debe limitarse al alcance aprobado.

No modificar Malāk para corregir un error del Sync Agent.

No modificar `main` del Vault para ocultar una propuesta defectuosa.

No borrar evidencia necesaria para reconstruir una ejecución.

## Regla final

> **El Sync Agent puede descubrir que no sabe mapear algo. Esa incertidumbre debe
> convertirse en evidencia y propuesta, no en una decisión automática.**
