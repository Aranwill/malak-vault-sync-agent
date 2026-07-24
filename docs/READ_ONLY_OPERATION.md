# Read-only Operation

## Propósito

Este documento define el circuito operativo de solo lectura del Malāk Vault
Synchronization Agent.

## Flujo

```text
fetch remoto controlado
→ inspección de repositorios
→ comparación del rango observado
→ resolución de candidatos
→ validación del Vault
→ evidencia e informe
→ persistencia de estado
```

## Fronteras de seguridad

El agente actualiza únicamente referencias Git remotas:

```text
refs/remotes/origin/main
```

No ejecuta:

```text
pull
checkout
switch
reset
merge
commit
push
```

La fuente de Malāk puede tener un `HEAD` local anterior al remoto; el agente
compara contra `origin/main` sin alterar el working tree.

El Vault debe estar alineado:

```text
HEAD == origin/main
```

Esto garantiza que los validadores examinen el mismo baseline documental que
el remoto observado.

## Estado

`last_observed_commit` significa que el cambio fue observado y auditado. No
significa que se haya aplicado al Vault.

La siguiente propiedad permanece obligatoriamente nula:

```json
"last_applied_commit": null
```

El estado solo se persiste después de crear y verificar:

1. el paquete de evidencia;
2. el informe JSON;
3. el informe Markdown;
4. los manifiestos SHA-256.

## Bootstrap

Si no existe estado previo, la primera ejecución registra el HEAD remoto
actual y no infiere cambios históricos.

## Fallos

Un error operativo devuelve código `2` y no avanza el estado. Una auditoría
completada con hallazgos de severidad `error` devuelve código `1`, conserva el
informe y registra que el commit fue observado.

## Scheduler

La unidad programable es:

```powershell
malak-vault-sync run-once --config .\config\vault-sync.yaml
```

La programación, frecuencia, retención y notificación son políticas
operativas externas. No forman parte de la autoridad del agente.
