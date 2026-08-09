# Incremento Correctivo Integral 5 — Cierre operativo

## Estado

```text
Implementación: completada
Validación automatizada: completada
Validación nativa Windows: completada
Validación GitHub CLI real: completada
Recovery negativo real: completado
Recovery positivo real: completado
Cleanup de certificación: completado
Cierre técnico: candidato a aprobación humana
Cierre operativo: candidato a aprobación humana
```

Fecha de validación: 2026-08-09.

---

## 1. Propósito

Este documento registra el cierre técnico y operativo del Incremento
Correctivo Integral 5 del Malāk Vault Synchronization Agent.

Su objetivo es consolidar la evidencia obtenida durante la validación final
del baseline `0.3.0`, incluyendo la ejecución real en Windows, integración
con GitHub CLI autenticado, recuperación remota de propuestas y verificación
de invariantes de gobernanza.

Este documento no modifica la autoridad del agente, no aprueba fases
posteriores y no concede permisos adicionales.

El agente continúa siendo tooling documental externo, gobernado,
determinista y sin autoridad operativa propia.

---

## 2. Baseline validado

### 2.1 Malāk

```text
Repositorio: Aranwill/jarvis
Rama: main
HEAD: b4d1d512fe953d593608391390f82ab500fdc9d6
Working tree: limpio
```

Malāk permaneció sin modificaciones durante todo el proceso de
certificación.

El agente mantuvo exclusivamente acceso de lectura sobre este repositorio.

### 2.2 Project Vault

```text
Repositorio: Aranwill/malak-project-vault
Rama: main
HEAD: 46672bcb971dbcdfcf25b1a4c7359aec9f047980
Working tree: limpio
```

El `main` del Vault permaneció sin modificaciones directas durante la
certificación.

Las operaciones de prueba se realizaron exclusivamente mediante una rama
temporal y una PR draft descartable.

### 2.3 Vault Synchronization Agent

```text
Repositorio: Aranwill/malak-vault-sync-agent
Rama base: main
Baseline previo: 77840274cf7361517381b938f142426dabe81a52
Rama correctiva: agent/normalize-pr-body-line-endings
Commit correctivo: fc2ebbb
Versión: 0.3.0
```

El hash completo del commit correctivo deberá registrarse después de su
publicación e integración gobernada.

---

## 3. Estado previo al cierre

El Incremento Correctivo Integral 5 había incorporado:

- validación final de documentos generados;
- validación de frontmatter YAML;
- validación de wikilinks;
- protección explícita de snapshots;
- corrección del bootstrap de `controlled-proposal`;
- recuperación de propuestas tras fallo de persistencia;
- separación entre observación y reconciliación;
- estado persistente v3;
- validación multiplataforma en CI;
- operación vigente `manual-on-demand`;
- preservación de `last_applied_commit = null`;
- eliminación del scheduler como modo operativo activo.

El baseline previo había sido validado mediante:

```text
259 tests passed
compileall: PASS
git diff --check: PASS
CI Linux: PASS
CI Windows: PASS
```

Sin embargo, permanecía pendiente la validación nativa real de GitHub CLI
en Windows.

---

## 4. Hallazgo durante la certificación operativa

Durante la validación nativa en Windows con GitHub CLI autenticado se
detectó una incompatibilidad real entre los finales de línea retornados
por `gh` y el parser de identidad de propuestas remotas.

GitHub CLI devolvió el campo `body` de las PR utilizando finales de línea:

```text
CRLF
\r\n
```

La función de recuperación analizaba el contenido mediante expresiones
regulares ancladas por línea.

La presencia del carácter `\r` impedía reconocer correctamente los campos
gobernados:

```text
Malāk base
Malāk HEAD
Vault base
```

El resultado previo a la corrección fue:

```text
discover_remote_proposal(): None
```

aunque la PR remota era válida y cumplía la identidad esperada.

---

## 5. Causa raíz

La causa raíz fue:

```text
GitHub CLI real en Windows
        ↓
body JSON con CRLF
        ↓
parser basado en líneas
        ↓
carácter \r antes de \n
        ↓
regex no coincide
        ↓
propuesta válida no identificada
```

La suite automatizada anterior no reproducía el problema porque los
fixtures utilizaban finales de línea LF (`\n`).

No se identificaron problemas de Unicode, codificación UTF-8 ni identidad
de los campos `Malāk`.

---

## 6. Corrección aplicada

La corrección normaliza los finales de línea del cuerpo remoto antes de
interpretar su identidad:

```python
body = body.replace("\r\n", "\n").replace("\r", "\n")
```

La normalización se aplica en los dos puntos donde
`discover_remote_proposal()` consume el cuerpo remoto:

1. clasificación inicial de propuestas candidatas;
2. validación completa de la propuesta seleccionada.

La corrección preserva el diseño original.

No se modificó:

- `_body_commit()`;
- modelo de identidad;
- estado v3;
- lógica de aceptación;
- lógica de rechazo;
- lógica de migración;
- runner;
- Vault Writer;
- candidate resolver;
- CLI;
- configuración;
- scheduler;
- Kernel;
- Planner;
- runtime de Malāk.

---

## 7. Regresión automatizada añadida

Se incorporó el test:

```text
test_discovers_remote_proposal_with_crlf_body
```

El test transforma explícitamente el cuerpo de una propuesta simulada de LF a CRLF y verifica que `discover_remote_proposal()` recupere correctamente:

- `source_commit`;
- branch determinista;
- estado `OPEN`;
- condición draft.

La prueba específica finalizó correctamente.

---

## 8. Validación automatizada posterior

Después de aplicar la corrección:

```text
260 passed
compileall: PASS
git diff --check: PASS
```

La suite completa fue ejecutada bajo:

```text
Python 3.12.10
Windows
virtual environment del proyecto
```

No se registraron regresiones.

---

## 9. Validación nativa de GitHub CLI

La validación operativa se ejecutó utilizando:

```text
GitHub CLI 2.97.0
GitHub autenticado como Aranwill
Windows
repositorios reales
Python 3.12.10
Vault Sync Agent 0.3.0
```

Se verificó el acceso real mediante GitHub CLI a:

```text
Aranwill/jarvis
Aranwill/malak-project-vault
Aranwill/malak-vault-sync-agent
```

Los tres repositorios utilizaron `main` como rama oficial.

---

## 10. Validación de inspección remota

Se verificó la función `inspect_pull_request()` contra una PR histórica real del Vault.

La inspección obtuvo correctamente:

- URL;
- `head_commit`;
- estado;
- `merged_at`.

Esto validó el circuito:

```text
Python
→ subprocess
→ gh
→ GitHub
→ JSON
→ parser
→ PullRequestSnapshot
```

sin modificar repositorios ni estado persistente.

---

## 11. Recovery negativo real

Se ejecutó `discover_remote_proposal()` sobre el estado operativo real sin propuesta pendiente.

El resultado fue:

```text
None
```

Esto confirmó que el agente no identificó erróneamente propuestas históricas como pendientes actuales.

La operación fue fail-safe y no produjo persistencia.

---

## 12. Fixture de certificación controlada

Para validar el recovery positivo se creó una fixture temporal y descartable en el Project Vault.

La fixture utilizó:

```text
PR: Aranwill/malak-project-vault#22
Branch: agent/vault-sync-b4d1d512
Estado inicial: OPEN
Draft: true
Merge permitido: no
```

La rama temporal fue creada desde:

```text
Vault base:
46672bcb971dbcdfcf25b1a4c7359aec9f047980
```

La identidad declarada de Malāk fue:

```text
Malāk base:
b4d1d512fe953d593608391390f82ab500fdc9d6

Malāk HEAD:
b4d1d512fe953d593608391390f82ab500fdc9d6
```

La fixture tenía exclusivamente propósito de certificación y no debía ser mergeada.

---

## 13. Resultado previo a la corrección

Antes de normalizar los finales de línea, la misma PR real produjo:

```text
discover_remote_proposal(): None
```

La inspección manual confirmó que el body remoto contenía CRLF y que el parser no reconocía los campos gobernados.

La normalización experimental demostró que el mismo contenido se interpretaba correctamente tras convertir los finales de línea a LF.

---

## 14. Recovery positivo real posterior a la corrección

Después de aplicar la corrección, se ejecutó nuevamente `discover_remote_proposal()` contra la PR real #22.

El resultado fue un `RecoverableProposal` con:

```text
url:
https://github.com/Aranwill/malak-project-vault/pull/22

branch:
agent/vault-sync-b4d1d512

source_commit:
b4d1d512fe953d593608391390f82ab500fdc9d6

state:
OPEN

is_draft:
True

merged_at:
None
```

La recuperación positiva quedó validada de extremo a extremo.

---

## 15. Circuito end-to-end certificado

```text
Windows
  ↓
Python 3.12
  ↓
Vault Sync Agent
  ↓
discover_remote_proposal()
  ↓
subprocess.run()
  ↓
GitHub CLI
  ↓
GitHub.com
  ↓
PR draft real
  ↓
JSON remoto
  ↓
normalización CRLF
  ↓
parser de identidad
  ↓
validación de branch
  ↓
validación de Vault base
  ↓
validación de Malāk base
  ↓
validación de Malāk HEAD
  ↓
RecoverableProposal
```

La operación fue determinista y no requirió intervención de LLM.

---

## 16. Cleanup gobernado de la certificación

Después de completar la validación positiva:

- la PR #22 fue cerrada sin merge;
- `mergedAt` permaneció en `null`;
- la rama remota `agent/vault-sync-b4d1d512` fue eliminada;
- el worktree temporal fue eliminado;
- la rama local temporal fue eliminada;
- no quedaron PR abiertas asociadas a la fixture;
- Malāk permaneció intacto;
- Vault `main` permaneció intacto;
- el repositorio del agente permaneció gobernado.

Estado final de la PR:

```text
state: CLOSED
mergedAt: null
```

---

## 17. Estado persistente posterior

El archivo operativo `var/state/sync-state.json` permaneció en esquema v3.

Estado verificado:

```text
schema_version: 3
last_applied_commit: null
pending_proposal_base_commit: null
pending_proposal_commit: null
pending_proposal_pull_request_url: null
pending_proposal_vault_commit: null
```

Los cursores permanecieron:

```text
last_observed_commit:
b4d1d512fe953d593608391390f82ab500fdc9d6

last_reconciled_commit:
b4d1d512fe953d593608391390f82ab500fdc9d6
```

No se produjo escritura operacional ni aplicación automática.

---

## 18. Invariantes preservados

Durante todo el incremento se verificaron los siguientes invariantes:

- `Aranwill/jarvis` permaneció de solo lectura.
- Malāk no fue modificado.
- Kernel no fue modificado.
- Planner no fue modificado.
- runtimes no fueron modificados.
- el agente permaneció fuera del runtime de Malāk.
- el agente no escribió directamente en `Vault/main`.
- las propuestas continuaron utilizando ramas aisladas.
- la PR de certificación permaneció draft durante la prueba.
- la PR no fue mergeada.
- no se habilitó auto-merge.
- no se modificaron snapshots.
- no se cerraron decisiones automáticamente.
- no se cerraron sprints automáticamente.
- no se incorporó LLM.
- no se activó scheduler.
- no se introdujo daemon.
- `operational_authority` permaneció `none`.
- `last_applied_commit` permaneció `null`.
- Human in Control permaneció vigente.

---

## 19. Modo operativo vigente

El modo operativo continúa siendo:

```text
manual-on-demand
```

No existe:

```text
scheduler activo
daemon
servicio residente
ejecución autónoma
auto-merge
autoridad decisoria
```

El propietario humano conserva exclusivamente la autoridad para ejecutar el agente, revisar propuestas, aceptar o rechazar propuestas, aprobar y mergear PR, modificar políticas, ampliar alcance y aprobar nuevas fases.

---

## 20. Autoridad

El estado de autoridad del agente permanece:

```text
operational_authority: none
document_authority: none
merge_authority: none
security_authority: none
```

La generación de evidencia no constituye aprobación.

Una propuesta no constituye aplicación.

Una PR draft no constituye decisión.

---

## 21. Seguridad

La corrección preserva los principios de:

- Zero Trust;
- Defense in Depth;
- Human in Control;
- mínimo privilegio;
- fail-closed;
- trazabilidad;
- separación de responsabilidades;
- no autoelevación.

La normalización de finales de línea no amplía el conjunto de entradas aceptadas semánticamente.

Solo convierte representaciones equivalentes de texto remoto a una forma canónica antes de validar los mismos invariantes existentes.

---

## 22. Riesgos residuales

Persisten los siguientes riesgos conocidos:

### Dependencia de GitHub CLI

`controlled-proposal` continúa dependiendo de GitHub CLI para operaciones remotas gobernadas.

Cambios incompatibles en el esquema JSON de `gh` deberán producir fallo seguro.

### Cambios futuros de plataforma

Actualizaciones futuras de Windows, GitHub CLI, GitHub o Python podrían introducir diferencias de representación que requieran nuevas validaciones.

### Cobertura automatizada

Las pruebas unitarias reducen riesgo, pero no sustituyen completamente la validación nativa cuando cambien dependencias externas.

### Automatización residente

Scheduler, daemon y ejecución permanente continúan deliberadamente fuera del baseline aprobado.

---

## 23. Rollback

El rollback del cambio funcional consiste en revertir el commit:

```text
fc2ebbb
```

o su hash completo una vez publicado.

El rollback:

- no requiere modificar Malāk;
- no requiere modificar Vault `main`;
- no requiere migrar estado v3;
- no modifica `last_applied_commit`;
- no afecta Kernel ni runtime.

Después del rollback deberá repetirse la suite completa antes de considerar el baseline estable.

---

## 24. Cuatro preguntas obligatorias de Malāk

### 24.1 ¿Respeta el Blueprint?

Sí.

El agente continúa desacoplado del Kernel, Planner, runtime y Capability Registry.

La corrección pertenece exclusivamente a la frontera de integración externa con GitHub CLI.

### 24.2 ¿Respeta la Constitución Cognitiva?

Sí.

No se utiliza LLM para decidir, autorizar, interpretar autoridad, aceptar propuestas, rechazarlas, mergear o modificar políticas.

### 24.3 ¿Respeta la Gobernanza?

Sí.

La prueba fue controlada, reversible, auditable y bajo autoridad humana.

La fixture fue cerrada sin merge y eliminada después de la validación.

### 24.4 ¿Hace al Kernel más simple o más complejo?

Neutro.

El Kernel no fue modificado.

---

## 25. Validaciones finales

```text
Versión: 0.3.0
Tests: 260 passed
compileall: PASS
git diff --check: PASS
Windows nativo: PASS
GitHub CLI real: PASS
GitHub authentication: PASS
PR inspection: PASS
Recovery negativo: PASS
Recovery positivo: PASS
CRLF regression: PASS
Cleanup: PASS
Malāk intacto: PASS
Vault main intacto: PASS
Snapshots intactos: PASS
Estado v3 intacto: PASS
last_applied_commit: null
Scheduler: disabled
LLM: not used
```

---

## 26. Resultado de cierre

El Incremento Correctivo Integral 5 queda técnicamente validado.

La brecha detectada durante la certificación nativa fue reproducida, diagnosticada, corregida, cubierta por regresión automatizada y validada contra una PR real mediante GitHub CLI en Windows.

No permanecen pendientes técnicos conocidos dentro del alcance aprobado del Incremento Correctivo Integral 5.

El agente queda listo para cierre operativo bajo las siguientes condiciones permanentes:

```text
modo: manual-on-demand
scheduler: disabled
operational_authority: none
last_applied_commit: null
human_review_required: true
merge_authority: human only
```

---

## 27. Aprobación

Este documento registra evidencia técnica.

No constituye por sí mismo aprobación de cierre.

La aprobación final corresponde exclusivamente al propietario humano.

Estado propuesto:

```text
technical_closure: PASS
operational_closure: READY_FOR_HUMAN_APPROVAL
phase_2: NOT_APPROVED
scheduler: NOT_APPROVED
additional_authority: NOT_GRANTED
```
