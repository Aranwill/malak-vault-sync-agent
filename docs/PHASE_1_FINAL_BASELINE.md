# Vault Synchronization Agent — Baseline Final de Fase 1

## 1. Identificación

- **Proyecto:** Malāk Vault Synchronization Agent
- **Ruta local validada:** `D:\Ollama\malak-vault-sync-agent`
- **Rama:** `main`
- **HEAD verificado:** `7ff4880de8b006904e81c6418fefd397febc627`
- **Último commit:** `7ff4880 fix(audit): align canonical run id contract`
- **Estado de la Fase 1:** completada y validada
- **Autoridad operativa:** ninguna sobre Malāk ni sobre el Vault
- **Modo:** `dry-run`
- **Control:** Human in Control

## 2. Jerarquía de autoridad

1. `Aranwill/jarvis`, rama `main`, es la única fuente de verdad operativa de Malāk.
2. El agente posee únicamente permisos y operaciones de lectura sobre Malāk.
3. `Aranwill/malak-project-vault`, rama `main`, es documental, derivado y sin autoridad operativa.
4. Obsidian es únicamente una interfaz local.
5. El agente no forma parte del Kernel ni del runtime de Malāk.
6. El agente no puede aprobar, aplicar, commitear, pushear ni mergear cambios sobre Malāk o el Vault.

## 3. Gates cerrados

### Gate 7

Cerrado antes del baseline actual.

### Gate 8

Cerrado con las siguientes capacidades integradas:

- `run_once()` supervisado;
- lectura del estado existente;
- bootstrap seguro cuando `last_observed_commit` es `null`;
- inspección Git read-only;
- comparación de commits;
- generación de evidencia;
- resolución de candidatos documentales;
- validación;
- construcción de informe;
- persistencia local controlada;
- lock local atómico;
- integración del lock con `run_once()`;
- polling externo determinista;
- integración de polling con `run_once()`;
- parada explícita;
- intervalo y función de espera inyectables;
- propagación de errores.

Commits relevantes:

- `eea98be feat(audit): add controlled audit report persistence`
- `e8b8543 feat(runner): add supervised single-run orchestration`
- `a80f05c feat(lock): add local execution lock`
- `5585d84 feat(runner): integrate local execution lock`
- `c13be6c feat(polling): add deterministic external polling`
- `b8a5a3f feat(runner): integrate deterministic polling`

### Gate 9

Cerrado mediante validación final, sin ampliar funcionalidad.

Incluyó:

- verificación de rama, HEAD, commits y working tree;
- suite completa;
- `compileall`;
- `git diff --check`;
- prueba supervisada end-to-end;
- inspección y verificación de evidencia e informe;
- auditoría de comandos Git;
- confirmación de integridad de Malāk y del Vault;
- confirmación de `last_applied_commit: null`;
- corrección de un defecto bloqueante del contrato de `run_id`;
- repetición exitosa de la prueba end-to-end.

## 4. Corrección bloqueante descubierta en Gate 9

La primera prueba end-to-end reveló una incompatibilidad entre:

- el formato generado por `build_run_id()`;
- la validación aplicada por los almacenes de evidencia e informe.

Formato canónico final:

```text
YYYYMMDDTHHMMSSZ_<source8>_<vault8>
```

Ejemplo:

```text
20260722T233850Z_f4d4a3d3_52976e77
```

La corrección quedó cerrada con:

```text
7ff4880 fix(audit): align canonical run id contract
```

La solución:

- centralizó la validación mediante `validate_run_id()`;
- eliminó el patrón duplicado del almacén de informes;
- alineó evidencia, informe, runner y pruebas;
- agregó pruebas de contrato para formatos válidos e inválidos.

## 5. Validación técnica final

Resultado verificado:

- **Suite completa:** `148 passed in 3.92s`
- **`compileall`:** correcto
- **`git diff --check`:** correcto
- **Working tree:** limpio
- **Lock local:** inexistente al finalizar
- **Rama:** `main`
- **HEAD:** `7ff4880de8b006904e81c6418fefd397febc627`

## 6. Prueba supervisada end-to-end

La corrida final utilizó:

- Malāk en `D:\Ollama\jarvis`;
- Vault en `D:\Ollama\malak-project-vault`;
- estado local en `var/state/sync-state.json`;
- evidencia en `var/evidence`;
- informes en `var/reports`.

Resultado:

- conclusión: `pass`;
- bootstrap: `false`;
- archivos cambiados: `0`;
- candidatos documentales: `0`;
- hallazgos: `0`;
- repositorios inspeccionados: `2`;
- estado sin modificaciones;
- Malāk sin modificaciones;
- Vault sin modificaciones;
- agente sin cambios en el working tree.

Run ID verificado:

```text
20260722T233850Z_f4d4a3d3_52976e77
```

Artefactos:

```text
var/evidence/20260722T233850Z_f4d4a3d3_52976e77
var/reports/20260722T233850Z_f4d4a3d3_52976e77
```

Todos los hashes SHA-256 del paquete de evidencia y del paquete de informe fueron verificados con resultado positivo.

## 7. Estado final

Valores verificados:

```json
{
  "last_applied_commit": null,
  "last_observed_commit": "f4d4a3d371d07b6aa91cc9f1c4d4bac3838ad627",
  "source_branch": "main",
  "source_repository": "Aranwill/jarvis",
  "status": "success",
  "vault_commit_at_run": "52976e771ad8307badbc0ac37a78a771e6df51fc"
}
```

La Fase 1 no actualiza automáticamente este estado.

## 8. Comandos Git permitidos

La implementación operativa inspeccionada utiliza únicamente subcomandos read-only:

- `git rev-parse`
- `git branch`
- `git status`
- `git remote`
- `git diff`

La ejecución usa argumentos separados y `shell=False`.

No se identificaron rutas operativas que ejecuten:

- `git fetch`
- `git pull`
- `git push`
- `git add`
- `git commit`
- `git checkout`
- `git switch`
- `git reset`
- `git merge`
- `git clean`

## 9. Flujo funcional de Fase 1

```text
polling externo determinista
→ lock local
→ lectura del estado
→ inspección Git read-only
→ validación de repositorios
→ comparación de commits
→ generación de evidencia
→ resolución de candidatos documentales
→ validación
→ generación de informe
→ persistencia local controlada
→ verificación de hashes
→ liberación del lock
→ fin de la ejecución
```

## 10. Capacidades explícitamente no implementadas

Permanecen fuera de la Fase 1:

- CLI operativa de ejecución;
- scheduler del sistema;
- servicio de Windows;
- escritura automática del estado;
- modificación automática del Vault;
- modificación o ejecución sobre Malāk;
- aplicación automática de candidatos;
- ramas, commits, push o PR automáticos;
- LLM;
- aprobación automática;
- integración con el Kernel o runtime.

## 11. Hardening no bloqueante pendiente

Estas mejoras fueron identificadas, pero no forman parte del baseline implementado:

- restringir combinaciones exactas de subcomando y argumentos Git;
- evaluar `GIT_OPTIONAL_LOCKS=0`;
- bloquear explícitamente opciones como `--ext-diff`, `--textconv` y `--output`;
- evaluar persistencia transaccional mediante directorio temporal y renombre atómico;
- definir una política formal de retención de artefactos.

Estas observaciones no bloquean el cierre de la Fase 1 y no deben interpretarse como capacidades aprobadas.

## 12. Conclusión

La Fase 1 del Vault Synchronization Agent queda cerrada.

El agente puede observar Malāk en modo read-only, comparar commits, producir evidencia verificable, resolver candidatos documentales, validar y generar informes locales sin modificar Malāk, el Vault ni el estado de aplicación.

Toda futura capacidad de actualización del Vault requiere una fase separada, aprobación explícita y controles adicionales de Human in Control.
