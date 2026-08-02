# Propuestas controladas del Vault

## Propósito

El modo `controlled-proposal` extiende la observación read-only sin
conceder autoridad de decisión ni merge al agente.

Ante un cambio publicado en `Aranwill/jarvis/main`, el agente:

1. actualiza las referencias remotas y, si el clon limpio del Vault quedó
   detrás, avanza su `main` local únicamente mediante `fast-forward`;
2. compara el nuevo HEAD con el último commit reconciliado;
3. resuelve únicamente documentos candidatos allowlisted;
4. genera evidencia e informe local;
5. crea un worktree temporal desde `origin/main` del Vault;
6. incorpora en cada candidato una proyección determinista del estado
   oficial, los commits observados y la ficha de sprint más reciente;
7. valida nuevamente el contenido final, su frontmatter YAML, enlaces y
   wikilinks, y solo entonces crea el commit documental;
8. genera un informe auditable que referencia ese commit;
9. valida el informe final y su entrada en el índice, y crea el segundo
   commit únicamente cuando ambos documentos son válidos;
10. ejecuta `push` sobre una rama `agent/vault-sync-<SHA8>`;
11. abre una PR draft mediante GitHub CLI;
12. guarda en estado v3 el rango y la identidad exacta de la propuesta
    pendiente únicamente después de completar el circuito.

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
el HEAD observado como primer cursor reconciliado y no crea una propuesta
retrospectiva.

```powershell
malak-vault-sync run-once `
  --config .\config\vault-sync.yaml
```

Las ejecuciones posteriores solo crean una PR cuando:

- cambió `Aranwill/jarvis/main`;
- existen candidatos documentales allowlisted;
- no hay errores de validación;
- no existe otra PR de sincronización abierta.

`dry-run` y `controlled-proposal` mantienen responsabilidades separadas.
El primero puede avanzar `last_observed_commit` sin consumir el rango
todavía no reconciliado. El segundo parte de `last_reconciled_commit`,
genera evidencia y auditoría y registra una propuesta pendiente con:

- `pending_proposal_base_commit`;
- `pending_proposal_commit`;
- `pending_proposal_vault_commit`;
- `pending_proposal_pull_request_url`.

Mientras cualquiera de esos rangos permanezca pendiente, `run-once` no
puede crear otra propuesta.

Si el `push` de una propuesta funciona pero GitHub CLI no puede crear la
PR draft, el agente elimina únicamente la rama remota de esa ejecución y
no persiste el nuevo estado observado. La siguiente corrida puede
reintentarlo sin reutilizar una rama huérfana.

Si la PR draft se crea pero falla la persistencia local posterior, la
siguiente ejecución revisa las ramas deterministas
`agent/vault-sync-<SHA8>`. La identidad del cuerpo conserva tanto la base
reconciliada como el HEAD propuesto de Malāk, por lo que la recuperación
sigue siendo posible aunque `main` avance después del fallo. Solo recupera
la propuesta cuando existe una coincidencia unívoca y concuerdan
repositorio, rama, base del Vault, HEAD remoto, cuerpo, estado y condición
de borrador. Después persiste el rango original y su identidad, y se
detiene; nunca crea una segunda propuesta.

## Ejecución manual vigente

La operación aprobada es `manual-on-demand`. El propietario ejecuta
`run-once` de forma explícita y conserva control sobre cuándo se observa
Malāk y cuándo puede generarse una PR draft.

El script `scripts/install-scheduled-task.ps1` permanece versionado como
capacidad opcional e histórica, pero no está activo ni autorizado como
modo operativo vigente. Su activación requiere una aprobación humana nueva.

Ejemplo manual:

```powershell
malak-vault-sync run-once `
  --config .\config\vault-sync.yaml
```

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

## Reconciliación v3 ordinaria

Después del merge humano de una PR pendiente:

```powershell
malak-vault-sync accept-proposal `
  --config .\config\vault-sync.yaml `
  --expected-commit <SHA_MALAK>
```

El agente verifica que la URL y el commit de cabecera coincidan con el
estado persistido y que GitHub informe la PR como mergeada. Solo entonces
avanza `last_reconciled_commit`.

Después de cerrar una PR sin merge:

```powershell
malak-vault-sync reject-proposal `
  --config .\config\vault-sync.yaml `
  --expected-commit <SHA_MALAK>
```

El rechazo conserva el cursor reconciliado anterior y elimina únicamente
la propuesta pendiente.

## Migración gobernada v1/v2

La lectura de un archivo v1 o v2 recupera el rango histórico y lo
representa en memoria como v3, pero no inventa la URL ni el commit de la
PR. Por eso no persiste una migración automática y bloquea la operación
controlada hasta que el propietario aporte la evidencia.

La única ruta soportada es:

```powershell
malak-vault-sync reconcile-migrated-proposal `
  --config .\config\vault-sync.yaml `
  --decision <accept|reject> `
  --expected-base-commit <SHA_BASE_MALAK> `
  --expected-commit <SHA_PROPUESTO_MALAK> `
  --proposal-vault-commit <SHA_CABECERA_PR_VAULT> `
  --pull-request-url <URL_PR_VAULT>
```

El comando:

1. adquiere `agent.lock`;
2. exige que el archivo original sea v1 o v2;
3. verifica base, extremo, repositorio, URL y commit de cabecera;
4. exige PR mergeada para aceptar o cerrada sin merge para rechazar;
5. guarda v3 atómicamente y conserva el archivo original en `.prev`;
6. mantiene `last_applied_commit` en `null`.

No admite PR abierta, identidad incompleta, rango diferente, timeout,
respuesta ambigua de GitHub, lock ocupado ni un archivo v3 ordinario.
Ante cualquier fallo anterior a la persistencia, el estado no cambia.

La secuencia completa, los códigos de salida y el rollback están en
`STATE_V3_MIGRATION_AND_RECONCILIATION.md`.

## Rollback

Para detener nuevas detecciones manuales, no ejecutar `run-once`.

Si existiera una tarea heredada, deshabilitarla explícitamente:

```powershell
Disable-ScheduledTask -TaskName MalakVaultSyncAgent
```

Para revertir una propuesta no aprobada, cerrar la PR sin merge. Malāk y
`main` del Vault permanecen intactos.

Para revertir una reconciliación local recién persistida, detener el
scheduler, conservar ambos archivos y restaurar
`sync-state.json.prev` únicamente después de verificar su hash y bajo
decisión humana. No editar campos individuales del JSON.
