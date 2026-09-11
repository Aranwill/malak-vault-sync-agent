# Lifecycle de ramas remotas bajo control exclusivo del Owner

## Propósito

Este documento preserva una frontera operativa explícita para
`malak-vault-sync-agent`:

> **El Sync Agent puede crear una rama de propuesta para abrir una Pull Request
> Draft, pero no puede ni debe eliminar ramas remotas de GitHub.**

La eliminación de una rama remota es una decisión y una acción exclusiva del
Owner.

Esta regla no amplía capacidades del agente, no modifica Malāk, no modifica el
Project Vault y no autoriza cambios de runtime.

## Autoridad

La separación de autoridad para ramas remotas es:

```text
Sync Agent
   ↓
puede crear rama determinista de propuesta
   ↓
puede abrir Draft PR
   ↓
puede observar / verificar / reportar estado
   ↓
NO puede eliminar rama
   ↓
Owner
   ↓
revisa y decide cualquier cleanup remoto
```

El Sync Agent no está autorizado a:

- ejecutar `git push --delete`;
- eliminar una referencia `refs/heads/*`;
- usar una lease para borrar una rama;
- borrar ramas por nombre, patrón, prefijo o wildcard;
- borrar una rama aunque coincidan nombre y SHA;
- usar force-push para reutilizar una rama existente;
- reinterpretar una PR cerrada como autorización de cleanup;
- inferir que una rama es descartable por haber sido creada por el propio
  agente.

`Agent-created != agent-owned authority`.

## Rechazo de una propuesta

`reject-proposal` continúa teniendo una responsabilidad acotada:

```text
PR revisada por el Owner
       ↓
PR CLOSED / unmerged
       ↓
verificación de identidad remota
       ↓
reconciliación de state v3
       ↓
pending_proposal_* = null
       ↓
last_reconciled_commit conserva la base previa
```

El rechazo no implica cleanup remoto.

Si la rama de propuesta continúa existiendo luego del rechazo, se trata como
residuo operativo visible bajo control del Owner.

## Reintento sobre el mismo HEAD

Las ramas de propuesta usan actualmente un nombre determinista:

```text
agent/vault-sync-<SHA8>
```

Por lo tanto, una rama residual puede colisionar con un nuevo intento para el
mismo HEAD de Malāk.

El flujo gobernado esperado es:

```text
run-once
   ↓
push non-fast-forward / rama existente
   ↓
STOP
   ↓
reportar rama + PR + HEAD + source range
   ↓
Owner revisa
   ├── conserva la rama
   └── elimina manualmente la rama si corresponde
          ↓
       nuevo run-once
```

El agente no debe resolver esa colisión mediante borrado, force-push ni takeover
de la rama.

## Información mínima a relevar

Cuando una revisión integral del Sync Agent evalúe propuestas pendientes,
reintentos, reconciliación o drift operativo, deberá considerar, según
aplicabilidad:

```text
source HEAD actual
last_observed_commit
last_reconciled_commit
pending_proposal_base_commit
pending_proposal_commit
pending_proposal_vault_commit
pending_proposal_pull_request_url
Vault main HEAD
rama determinista esperada
existencia de esa rama remota
HEAD observado de esa rama
PR asociada y su estado
resultado del último run
findings / reportes / evidencia
```

Una rama remota residual no debe omitirse de la revisión si puede afectar la
capacidad de proponer el rango pendiente.

## Clasificación de drift

Una rama residual no es por sí sola corrupción del state.

Debe clasificarse según evidencia:

- `STATE_DRIFT`: cuando state v3 y realidad remota no representan de forma
  coherente una propuesta pendiente o reconciliada;
- `DOCUMENTATION_DRIFT`: cuando la documentación describe una autoridad o
  comportamiento distinto del verificable;
- `AUTHORITY_DRIFT`: cuando una implementación, propuesta o procedimiento
  atribuye al agente autoridad de eliminación que pertenece al Owner;
- `SYNC_DRIFT`: cuando el lifecycle remoto impide repetir correctamente una
  sincronización que las reglas vigentes deberían poder proponer.

Detectar cualquiera de estos estados no concede autorización para eliminar una
rama ni modificar GitHub fuera de la propuesta gobernada.

## Contexto reproducido el 2026-09-09

Durante una reconciliación real del Vault se observó:

```text
proposal rejected
      ↓
state v3 reconciliado correctamente
      ↓
rama remota de propuesta permaneció
      ↓
retry del mismo source HEAD
      ↓
mismo nombre determinista
      ↓
push rejected: non-fast-forward
```

La recuperación correcta requirió intervención manual del Owner sobre la rama
remota. La sincronización posterior completó correctamente el rango y el state
v3 quedó reconciliado.

Este incidente demuestra una condición operativa real que debe permanecer
visible en futuras revisiones.

## Resolución de `KNOWN_AUTHORITY_DRIFT` — F-01

El rollback remoto automático posterior a un fallo de creación de Draft PR
contradecía la frontera Owner-only definida por este documento.

Este cambio elimina esa acción destructiva del failure path.

A partir de este cambio:

- si el `push` de la rama de propuesta ya ocurrió y la creación o confirmación
  de la Draft PR falla, la rama remota permanece intacta;
- el fallo reporta la identidad de la rama y conserva visible la posibilidad de
  un resultado remoto desconocido;
- el worktree y la rama local temporal pueden seguir limpiándose como
  housekeeping local;
- el agente no ejecuta borrado remoto, force-push ni takeover para recuperarse;
- cualquier cleanup de la rama remota continúa siendo una decisión y una acción
  exclusiva del Owner.

El fallo continúa resolviendo de forma cerrada: no se presenta una propuesta
como completada cuando no existe confirmación suficiente del circuito remoto.

```text
Agent-created remote branch
!=
agent-owned destructive authority
```

## Relación con actualización del Vault

Esta frontera no cambia el propósito principal del Sync Agent:

```text
Malāk source of truth
        ↓
relevar todas las rutas relevantes
        ↓
resolver mappings deterministas
        ↓
detectar coverage / projection / semantic drift
        ↓
proponer actualización del Vault
        ↓
Draft PR
        ↓
revisión humana
        ↓
reconciliación state v3
```

La prioridad sigue siendo que el agente no omita fuentes relevantes y que el
Vault permanezca actualizado, trazable y recuperable, sin ampliar autoridad
operativa.

## Regla final

> **Observar una rama no concede autoridad para eliminarla. Crear una rama no
> concede autoridad para destruirla. La eliminación de ramas remotas pertenece
> exclusivamente al Owner.**
