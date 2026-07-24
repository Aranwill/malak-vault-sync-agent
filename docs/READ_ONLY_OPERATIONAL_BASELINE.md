# Read-only Operational Baseline

## Estado

```text
status: validated
mode: dry-run
operational_authority: none
source_write_authority: none
vault_write_authority: none
```

## Baseline anterior

```text
954659b docs(baseline): record phase 1 completion
```

## Implementación

```text
54f2987 feat(agent): operationalize read-only audit runs
42a773f docs(agent): document read-only operation
```

## Capacidades verificadas

- comando `run-once`;
- actualización controlada de `origin/main`;
- validación de identidad de remotos antes de `fetch`;
- comparación contra el HEAD remoto de Malāk;
- detección de modificaciones, altas, bajas y renombres;
- resolución de candidatos con las rutas actuales del repositorio;
- límites de comandos, tiempo, archivos y evidencia;
- serialización correcta de candidatos;
- evidencia e informes con SHA-256;
- persistencia atómica del último commit observado;
- CI de solo lectura.

## Validación automatizada

```text
pytest: 165 passed
compileall: pass
git diff --check: pass
```

Entorno:

```text
Python 3.12.13
pytest 9.1.1
Linux 6.12.13 x86_64
```

## Validación end-to-end

Repositorios reales utilizados mediante clones desechables:

```text
Aranwill/jarvis
Aranwill/malak-project-vault
```

Bootstrap:

```text
conclusion: pass
changed_files: 0
document_candidates: 0
```

Cambio controlado:

```text
base: fdb3ee922efc796e53ade1fc3abe4125f4072bd0
head: fd4da3d371d07b6aa91cc9f1c4d4bac3838ad627
changed_files: 11
renames: 2
document_candidates: 4
validation_findings: 0
conclusion: pass
```

Estado posterior:

```text
last_observed_commit: fd4da3d371d07b6aa91cc9f1c4d4bac3838ad627
last_applied_commit: null
vault_commit_at_run: 03032a7b2aaecb47c27c2e8e5bff3a2c04179bd2
```

Los working trees de Malāk y del Vault permanecieron limpios y alineados.

## Límites vigentes

El agente no puede:

- modificar Malāk;
- modificar el Vault;
- crear ramas documentales;
- crear commits documentales;
- publicar cambios;
- abrir o fusionar pull requests;
- modificar snapshots históricos;
- utilizar LLM;
- cerrar decisiones.

## Pendiente operativo local

Antes de activar una tarea programada en Windows, el owner debe:

1. instalar esta versión en `D:\Ollama\malak-vault-sync-agent`;
2. crear `config/vault-sync.yaml`;
3. ejecutar `validate-config`;
4. ejecutar un bootstrap real con `run-once`;
5. revisar el estado, la evidencia y el informe generados.

La instalación del scheduler permanece separada y requiere aprobación humana.
