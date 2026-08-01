# Estado v3: migración y reconciliación gobernada

## Propósito

Esta guía define la transición segura de un estado local original v1 o
v2 al esquema v3 cuando existe una propuesta histórica pendiente. La
transición no concede autoridad adicional al agente y no modifica Malāk,
el Kernel ni `main` remoto del Vault.

## Modelo operativo

| Concepto | Campo v3 | Autoridad |
|---|---|---|
| Último HEAD auditado | `last_observed_commit` | Observación determinista |
| Cursor gobernado | `last_reconciled_commit` | Decisión humana verificada |
| Rango pendiente | `pending_proposal_base_commit` / `pending_proposal_commit` | Evidencia local |
| Identidad de la PR | `pending_proposal_vault_commit` / `pending_proposal_pull_request_url` | GitHub verificado |
| Aplicación automática | `last_applied_commit` | Siempre `null` |

Observar no equivale a proponer. Proponer no equivale a aceptar. El
cursor reconciliado cambia únicamente después de una decisión humana
compatible con el estado verificable de la PR.

## Por qué la migración se bloquea

Los esquemas v1 y v2 pueden recuperar el rango de Malāk usando el estado
actual y `sync-state.json.prev`, pero no contienen la identidad completa
de la PR del Vault. El agente no puede inferir de forma segura:

- cuál PR representa ese rango;
- cuál era su commit exacto de cabecera;
- si el propietario decidió aceptar o rechazar.

Por lo tanto, la lectura migra solo en memoria. No guarda v3 y no permite
otra propuesta hasta reconciliar el rango histórico.

## Precondiciones

Antes de operar:

1. deshabilitar temporalmente cualquier tarea programada;
2. confirmar que no existe `agent.lock`;
3. conservar `sync-state.json` y `sync-state.json.prev`;
4. verificar la base y el extremo de Malāk;
5. verificar la URL y el commit de cabecera de la PR del Vault;
6. confirmar la decisión humana: `accept` o `reject`;
7. usar configuración `controlled-proposal` válida.

No abrir el JSON para completar campos manualmente.

## Aceptación

La aceptación requiere que GitHub informe la PR como mergeada y que la
URL y el commit de cabecera coincidan exactamente:

```powershell
malak-vault-sync reconcile-migrated-proposal `
  --config .\config\vault-sync.yaml `
  --decision accept `
  --expected-base-commit <SHA_BASE_MALAK> `
  --expected-commit <SHA_PROPUESTO_MALAK> `
  --proposal-vault-commit <SHA_CABECERA_PR_VAULT> `
  --pull-request-url <URL_PR_VAULT>
```

Resultado:

- `last_reconciled_commit` avanza a `expected-commit`;
- los cuatro campos pendientes quedan en `null`;
- `last_applied_commit` permanece en `null`;
- el archivo persistido pasa a esquema v3;
- el archivo heredado queda en `sync-state.json.prev`.

## Rechazo

El rechazo requiere que GitHub informe la PR como cerrada sin merge:

```powershell
malak-vault-sync reconcile-migrated-proposal `
  --config .\config\vault-sync.yaml `
  --decision reject `
  --expected-base-commit <SHA_BASE_MALAK> `
  --expected-commit <SHA_PROPUESTO_MALAK> `
  --proposal-vault-commit <SHA_CABECERA_PR_VAULT> `
  --pull-request-url <URL_PR_VAULT>
```

Resultado:

- `last_reconciled_commit` queda en `expected-base-commit`;
- los cuatro campos pendientes quedan en `null`;
- `last_applied_commit` permanece en `null`;
- el archivo persistido pasa a esquema v3;
- el archivo heredado queda en `sync-state.json.prev`.

## Bloqueos seguros

La reconciliación termina con código `2` y no persiste cambios cuando:

- el archivo original no es v1 o v2;
- falta el rango pendiente;
- la base o el extremo no coinciden;
- el SHA o la URL tienen formato inválido;
- la URL pertenece a otro repositorio;
- GitHub devuelve otra URL o commit de cabecera;
- la PR continúa abierta;
- se intenta aceptar una PR no mergeada;
- se intenta rechazar una PR mergeada;
- `gh` falla, expira el timeout o devuelve datos ambiguos;
- `agent.lock` ya existe;
- falla la lectura o la escritura local.

Los códigos de salida son:

- `0`: reconciliación persistida;
- `2`: error operativo o de seguridad; no continuar con `run-once`.

## Validación previa sobre una copia

Antes de tocar el estado operativo, copiar ambos archivos a un directorio
temporal, apuntar una configuración privada a esa copia y ejecutar la
reconciliación allí. Verificar:

1. esquema v3 resultante;
2. cursor reconciliado esperado;
3. campos pendientes en `null`;
4. `last_applied_commit` en `null`;
5. backup `.prev` idéntico al estado heredado original;
6. ausencia de cambios en Malāk y en `main` del Vault.

Esta validación sobre copia no autoriza la migración del estado operativo.

## Rollback

Si se necesita revertir una reconciliación local recién persistida:

1. detener el scheduler;
2. no ejecutar `run-once`;
3. calcular y registrar SHA-256 de ambos archivos;
4. confirmar que `.prev` es el estado heredado esperado;
5. copiar ambos archivos a un directorio de resguardo;
6. restaurar `.prev` como archivo activo mediante una operación atómica;
7. volver a validar los hashes;
8. registrar la decisión y el resultado.

El rollback es local. No revierte PR, commit ni merge alguno y requiere
una decisión humana separada.

## Prohibiciones

- no editar campos individuales del estado;
- no inferir una PR por fecha, nombre de rama o similitud de contenido;
- no aceptar ni rechazar automáticamente;
- no ejecutar la reconciliación sobre un estado v3 ordinario;
- no modificar snapshots históricos;
- no usar esta operación para escribir en Malāk o en `main` del Vault.
