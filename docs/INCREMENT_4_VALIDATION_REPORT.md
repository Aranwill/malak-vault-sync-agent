# Incremento 4 — Informe de implementación y validación local

## Estado del informe

```text
Implementación local: completa
Validación hermética: completa
Validación remota read-only: completa con adaptador de proceso
Validación nativa mediante gh: pendiente en el equipo Windows
Validación remota de rechazo: pendiente de autorización separada
Publicación como PR draft: autorizada, pendiente al emitir este informe
Merge: no autorizado
Cierre del Incremento 4: no declarado
```

Fecha: 2026-08-01.

## Baseline y aislamiento

- repositorio: `Aranwill/malak-vault-sync-agent`;
- rama base: `main`;
- baseline: `5f5c12935757283fb121fbefe5850c25b8bceb31`;
- rama local: `feature/increment-4-state-v3-reconciliation`;
- Malāk no fue modificado;
- el Vault no fue modificado;
- el estado operativo real no fue leído, migrado ni escrito;
- no se ejecutó `run-once`, `accept-proposal` ni `reject-proposal`;
- no se crearon ramas, commits o PR remotos.

## Implementación

Se incorporó `reconcile-migrated-proposal` con evidencia obligatoria:

- decisión explícita `accept` o `reject`;
- base esperada de Malāk;
- extremo esperado de Malāk;
- commit exacto de cabecera de la PR del Vault;
- URL exacta de la PR del Vault.

La operación:

1. exige modo `controlled-proposal`;
2. adquiere `agent.lock`;
3. conserva el esquema original detectado durante la carga;
4. admite únicamente archivos originales v1 o v2;
5. recupera y verifica el rango histórico;
6. consulta GitHub sin `shell` y con timeout;
7. verifica repositorio, URL, commit de cabecera y estado de la PR;
8. acepta únicamente una PR mergeada;
9. rechaza únicamente una PR cerrada sin merge;
10. persiste v3 mediante la escritura atómica y el backup existentes;
11. mantiene `last_applied_commit` en `null`.

En aceptación, `last_reconciled_commit` avanza al extremo propuesto. En
rechazo, queda en la base explícitamente confirmada.

## Documentación

Se actualizaron:

- `README.md`;
- `docs/CONTROLLED_VAULT_PROPOSALS.md`.

Se creó:

- `docs/STATE_V3_MIGRATION_AND_RECONCILIATION.md`.

La documentación diferencia observación, propuesta y reconciliación;
describe los bloqueos seguros, códigos de salida, backup, validación sobre
copia, rollback y la prohibición de editar manualmente el estado.

## Validación automatizada

Resultado local:

```text
230 pruebas aprobadas
python -m compileall -q src tests: aprobado
git diff --check: aprobado
```

La suite cubre, entre otros casos:

- aceptación de estado v2 migrado;
- rechazo de estado v2 preservando la base;
- detección del esquema original antes de migrar;
- rechazo de un estado v3 ordinario;
- base o extremo inesperados;
- identidad inválida o diferente;
- PR abierta, cerrada o mergeada según la decisión;
- fallo y timeout de GitHub CLI;
- lock ocupado;
- estado sin cambios ante fallos previos a la persistencia;
- fallo de reemplazo atómico sin alterar el estado activo;
- backup idéntico al estado heredado original;
- bloqueo de `run-once` ante un rango migrado pendiente;
- CLI end-to-end con configuración real y doble hermético de GitHub.

## Validaciones remotas

### Aceptación read-only contra la PR histórica #18

La identidad y el estado de la PR histórica se consultaron en GitHub sin
realizar escrituras remotas. La evidencia verificada fue:

- base de Malāk: `38b0917c5b8dba5c5a4ef4db157e78ac428ab4bc`;
- extremo de Malāk: `b4d1d512fe953d593608391390f82ab500fdc9d6`;
- cabecera histórica de la PR:
  `63f3b981e8f3dc5efd0c61c12b649511d0ac749a`;
- merge del Vault: `f433b9efc426ba52141a1a3daed81795fc666e6f`;
- PR histórica: `https://github.com/Aranwill/malak-project-vault/pull/18`;
- estado remoto: `MERGED`;
- fecha de merge: `2026-07-30T21:51:26Z`.

El archivo operativo de Windows no estaba disponible en el entorno. Para
evitar leerlo o modificarlo, se reconstruyó un estado v2 aislado usando los
dos informes auditables versionados de los runs `38b0917c` y `b4d1d512`.
Esta reproducción no se presenta como copia byte a byte del archivo
operativo.

El entorno tampoco incluía el ejecutable `gh`. La metadata recién leída de
GitHub se entregó mediante un adaptador local al mismo límite de proceso
`subprocess` que usa el agente. No se instaló software y no se sustituyó el
resultado por un estado inventado.

Resultado de `reconcile-migrated-proposal --decision accept`:

```text
Código de salida: 0
Mensaje: Migrated proposal accepted.
schema_version: 3
last_reconciled_commit: b4d1d512fe953d593608391390f82ab500fdc9d6
pending_proposal_*: null
last_applied_commit: null
agent.lock residual: no
```

Hashes SHA-256:

```text
estado v2 de entrada:
4890c2650e924ab6545f699abfc7b67415b30589e41847cced16d4abdc87ec1c

estado v3 resultante:
46a208a2266f12bbd4e5bf430228eaab9be266f31a06dbb3bfe0dd9ba2c53071

backup generado:
4890c2650e924ab6545f699abfc7b67415b30589e41847cced16d4abdc87ec1c
```

El hash del backup coincide exactamente con el estado v2 de entrada. Malāk
permaneció limpio en `b4d1d512` y el Vault permaneció limpio en `f433b9ef`.

La prueba valida la decisión, el rango, la identidad remota, la transición
v2 a v3 y la persistencia local. Queda pendiente una ejecución nativa con
`gh` sobre una copia del estado operativo antes de migrar ese archivo real.

Esta validación no autoriza la migración del estado operativo.

### Rechazo real

Requiere crear una rama y una PR descartables en el Vault, cerrarla sin
merge y eliminar después la rama temporal. Es una acción remota separada
y no está autorizada por este informe.

## Rollback actual

Como no existe commit ni publicación remota, el rollback consiste en
descartar los cambios de la rama local. No hay efectos que revertir en
Malāk, el Vault, GitHub o el estado operativo.

## Cuatro preguntas de ley

1. **Blueprint:** la capacidad permanece en tooling externo y desacoplado.
2. **Constitución Cognitiva:** ninguna decisión se infiere o automatiza.
3. **Gobernanza:** se exige evidencia explícita, lock, verificación remota,
   persistencia trazable y rollback.
4. **Simplicidad del Kernel:** el Kernel no fue modificado ni conoce esta
   operación.

## Conclusión

El código y la documentación del Incremento 4 están preparados y validados
localmente. La aceptación read-only contra la PR #18 pasó con evidencia
remota real y un adaptador de proceso, pero la ejecución nativa mediante
`gh` y la validación remota de rechazo continúan pendientes.

El propietario autorizó publicar este corte mediante una PR draft para
trasladarlo al equipo Windows y completar la validación nativa. Esta
autorización no permite mergear, migrar el estado operativo real ni declarar
cerrado el Incremento 4.

## Epílogo de cierre — 2026-08-01

Este epílogo conserva intacto el informe anterior como evidencia del
estado existente cuando se publicó la implementación. Las acciones
pendientes allí registradas fueron completadas posteriormente mediante
validaciones gobernadas y autorizaciones humanas separadas.

Estado posterior verificado:

```text
PR #5 del agente: integrada
Agente main: 1c60eac417f14e7c95e16598266effb9453c7c2d
Suite de implementación: 230 passed
Validación nativa de aceptación: completa
Validación nativa de rechazo: completa
Migración operativa v2 → v3: completa
Cierre del Incremento 4: aprobado
```

### Validación nativa de aceptación

La ruta de aceptación fue ejecutada de forma aislada contra la PR
histórica #18 del Vault:

- decisión explícita: `accept`;
- PR: `MERGED`;
- cabecera:
  `63f3b981e8f3dc5efd0c61c12b649511d0ac749a`;
- `last_reconciled_commit` resultante:
  `b4d1d512fe953d593608391390f82ab500fdc9d6`;
- campos de propuesta pendientes: `null`;
- `last_applied_commit`: `null`;
- estado operativo real: intacto durante esta prueba.

### Validación nativa de rechazo

La ruta de rechazo fue validada mediante la PR descartable #19:

- decisión explícita: `reject`;
- PR cerrada sin merge;
- `mergedAt`: `null`;
- rama remota temporal eliminada;
- Vault `main` preservado en
  `f433b9efc426ba52141a1a3daed81795fc666e6f`;
- `last_reconciled_commit` temporal preservado en
  `38b0917c5b8dba5c5a4ef4db157e78ac428ab4bc`;
- estado operativo real: intacto durante esta prueba.

### Migración del estado operativo real

Después de aprobar ambas rutas aisladas, el propietario autorizó y
ejecutó una única reconciliación real con decisión `accept`.

Resultado:

```text
schema_version: 3
last_observed_commit: b4d1d512fe953d593608391390f82ab500fdc9d6
last_reconciled_commit: b4d1d512fe953d593608391390f82ab500fdc9d6
pending_proposal_*: null
last_applied_commit: null
working tree: limpio
agent.lock: ausente
```

El backup generado conserva exactamente el estado v2 de entrada, cuyo
SHA-256 es:

```text
2ba6a074986a1d40772fe1d948c8784a5d8ea4ec669b956fb2fa403665f5d71a
```

El backup histórico anterior, con SHA-256
`c6bb309f33662cdf06ebe8b6db11adb31fd65f4e334fb65e565681cb06e5fd8c`,
fue preservado separadamente dentro de la evidencia de recuperación.

La migración no modificó Malāk, el Vault, el Kernel ni ningún repositorio
remoto.

### Resultado

Las validaciones nativas de aceptación y rechazo, la persistencia segura,
el backup, los bloqueos, la identidad remota y la migración del estado
operativo quedaron demostrados.

El cierre definitivo se registra en
`docs/INCREMENT_4_CLOSURE.md`.
