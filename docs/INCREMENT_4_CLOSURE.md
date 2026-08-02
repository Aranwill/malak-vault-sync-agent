# Incremento 4 — Cierre de reconciliación y estado v3

## Estado

```text
Incremento: 4
Estado: cerrado
Fecha de cierre: 2026-08-01
Autoridad de cierre: propietario humano
Autoridad operativa del agente: none
```

## Propósito

Este documento registra el cierre técnico y operativo del Incremento 4
del Malāk Vault Synchronization Agent.

El incremento completa la transición gobernada al esquema de estado v3 y
demuestra que una propuesta histórica puede reconciliarse mediante una
decisión humana explícita, evidencia remota verificable, persistencia
atómica y recuperación controlada.

## Baselines verificados

| Componente | Rama | HEAD |
|---|---|---|
| Malāk | `main` | `b4d1d512fe953d593608391390f82ab500fdc9d6` |
| Project Vault | `main` | `f433b9efc426ba52141a1a3daed81795fc666e6f` |
| Vault Sync Agent | `main` | `1c60eac417f14e7c95e16598266effb9453c7c2d` |

El HEAD del agente corresponde al merge de la PR #5:

```text
feat(agent): add governed v3 state reconciliation
```

La implementación fue validada con:

```text
230 passed
python -m compileall src tests: aprobado
git diff --check: aprobado
```

## Alcance completado

El Incremento 4 incorporó y validó:

- esquema persistente v3;
- separación entre observación y reconciliación;
- identidad completa de la propuesta pendiente;
- comandos ordinarios de aceptación y rechazo;
- reconciliación explícita de propuestas heredadas v1/v2;
- verificación del rango histórico de Malāk;
- verificación remota de URL, cabecera y estado de la PR;
- lock de ejecución;
- persistencia atómica;
- backup del estado anterior;
- bloqueo seguro ante evidencia incompleta o contradictoria;
- mantenimiento permanente de `last_applied_commit: null`.

## Evidencia de implementación

La PR #5 del agente fue integrada en `main`.

Evidencia publicada:

- commit validado de la rama:
  `ab9610a6e76237ac120db865c5667b02e7ab816b`;
- árbol validado:
  `af5a73bdcf453690527131c3c1cf0a5fcefb5fc2`;
- merge commit:
  `1c60eac417f14e7c95e16598266effb9453c7c2d`;
- suite completa: `230 passed`;
- `compileall`: aprobado;
- `git diff --check`: aprobado.

El merge incorporó la capacidad al agente, pero no autorizó por sí solo
la migración del estado operativo.

## Validación nativa de aceptación

La ruta de aceptación se ejecutó de forma aislada utilizando la PR
histórica #18 del Vault.

Resultado verificado:

```text
decision: accept
pull request state: MERGED
pull request head: 63f3b981e8f3dc5efd0c61c12b649511d0ac749a
schema_version: 3
last_reconciled_commit: b4d1d512fe953d593608391390f82ab500fdc9d6
pending_proposal_*: null
last_applied_commit: null
```

El backup generado fue idéntico al estado v2 aislado de entrada. La
prueba no modificó el estado operativo real ni ningún repositorio remoto.

## Validación nativa de rechazo

La ruta de rechazo se validó mediante la PR temporal #19 del Vault.

Resultado verificado:

```text
decision: reject
pull request state: CLOSED
mergedAt: null
last_reconciled_commit: 38b0917c5b8dba5c5a4ef4db157e78ac428ab4bc
pending_proposal_*: null
last_applied_commit: null
```

La PR se cerró sin merge, la rama remota temporal fue eliminada y el
Vault `main` permaneció intacto en `f433b9ef`.

## Migración operativa v2 → v3

Después de aprobar separadamente las dos rutas aisladas, el propietario
autorizó la escritura local del estado operativo real.

Se ejecutó una única reconciliación con:

```text
decision: accept
base: 38b0917c5b8dba5c5a4ef4db157e78ac428ab4bc
commit: b4d1d512fe953d593608391390f82ab500fdc9d6
pull request: https://github.com/Aranwill/malak-project-vault/pull/18
pull request head: 63f3b981e8f3dc5efd0c61c12b649511d0ac749a
```

Estado operativo resultante:

```text
schema_version: 3
last_observed_commit: b4d1d512fe953d593608391390f82ab500fdc9d6
last_reconciled_commit: b4d1d512fe953d593608391390f82ab500fdc9d6
pending_proposal_base_commit: null
pending_proposal_commit: null
pending_proposal_vault_commit: null
pending_proposal_pull_request_url: null
last_applied_commit: null
agent.lock: ausente
```

SHA-256 del estado v2 de entrada y del backup generado:

```text
2ba6a074986a1d40772fe1d948c8784a5d8ea4ec669b956fb2fa403665f5d71a
```

SHA-256 del backup histórico preservado separadamente:

```text
c6bb309f33662cdf06ebe8b6db11adb31fd65f4e334fb65e565681cb06e5fd8c
```

La evidencia temporal de aceptación, rechazo, migración y recuperación
fue conservada fuera del estado operativo.

## Criterios de cierre

| Criterio | Resultado |
|---|---|
| Implementación integrada | Aprobado |
| Suite completa | `230 passed` |
| Validación nativa de aceptación | Aprobada |
| Validación nativa de rechazo | Aprobada |
| PR de rechazo cerrada sin merge | Aprobado |
| Rama temporal de rechazo eliminada | Aprobado |
| Migración operativa a v3 | Aprobada |
| Backup v2 verificable | Aprobado |
| Campos pendientes nulos | Aprobado |
| `last_applied_commit` nulo | Aprobado |
| `agent.lock` ausente | Aprobado |
| Repositorios remotos intactos | Aprobado |
| Kernel y runtime intactos | Aprobado |

## Invariantes preservadas

El cierre no modifica los límites de autoridad:

- Malāk permanece en modo de solo lectura para el agente;
- el agente no escribe directamente en `main` del Vault;
- cada propuesta continúa requiriendo revisión humana;
- aceptar o rechazar exige una decisión humana explícita;
- el agente no aprueba ni fusiona PR;
- no existe auto-merge;
- no existe scheduler activo;
- el modo operativo continúa siendo `manual-on-demand`;
- no se utiliza LLM;
- `last_applied_commit` permanece en `null`;
- `operational_authority` permanece en `none`;
- el agente continúa fuera del Kernel y del runtime de Malāk.

## Rollback y recuperación

No existe cambio remoto que revertir.

Ante un incidente con el estado local:

1. detener cualquier ejecución;
2. conservar `sync-state.json` y `sync-state.json.prev`;
3. conservar la evidencia externa y sus hashes;
4. no editar campos individuales;
5. no reintentar automáticamente;
6. restaurar únicamente después de una decisión humana explícita y una
   verificación de identidad.

## Cuatro preguntas de ley

1. **Blueprint:** aprobado. El agente permanece como tooling externo.
2. **Constitución Cognitiva:** aprobado. Ninguna decisión se infiere.
3. **Gobernanza:** aprobado. La reconciliación exige decisión y evidencia.
4. **Simplicidad del Kernel:** aprobado. El Kernel permanece intacto.

## Conclusión

El Incremento 4 queda cerrado técnica y operativamente.

Este cierre no autoriza:

- una Fase 2;
- un nuevo incremento del agente;
- una ampliación de permisos;
- ejecución programada;
- merge automático;
- modificación directa del Vault;
- modificación de Malāk;
- inicio o cierre de un sprint de Malāk.

La actualización derivada del Project Vault deberá realizarse
posteriormente mediante una propuesta documental gobernada y una nueva
aprobación humana.

## Validación de la rama documental de cierre

Después de preparar este documento se ejecutó:

```text
python -m pytest -q: 230 passed
python -m compileall -q src tests: aprobado
git diff --check: aprobado
```

La validación no modificó código operativo ni el estado local del agente.
