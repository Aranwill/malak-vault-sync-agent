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

## Hallazgo heredado que no se corrige en este packet

La documentación vigente de `controlled-proposal` describe un camino histórico
en el que, si el push de una propuesta funciona pero la creación de la Draft PR
falla, puede realizarse cleanup automático de la rama remota.

Esa conducta entra en tensión con la frontera Owner-only establecida aquí.

Por instrucción explícita del Owner, **este packet no modifica runtime ni lógica
del agente**. En consecuencia:

- no se agrega ninguna nueva eliminación automática;
- no se modifica `reject-proposal`;
- no se modifica `proposal_reconciliation.py`;
- no se modifica el writer;
- no se modifican Git operations;
- no se modifica state v3;
- no se cambia versión;
- no se agregan tests de eliminación.

La discrepancia existente debe permanecer visible como `KNOWN_AUTHORITY_DRIFT`
hasta que el Owner decida explícitamente si corresponde un cambio separado.
No puede usarse este documento como autorización implícita para modificar ese
comportamiento.

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
