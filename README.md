# Malāk Vault Synchronization Agent

Agente externo y determinista para detectar y auditar cambios entre el
repositorio oficial de Malāk y el Malāk Project Vault.

## Estado

```text
Fase 1 — cerrada
Gates 0–9 — cerrados
Read-only Operationalization — implementada
Modo operativo — dry-run / solo lectura documental
```

El agente puede actualizar referencias remotas, detectar cambios nuevos en
`Aranwill/jarvis/main`, generar evidencia verificable, resolver documentos
candidatos, validar el Vault y persistir el último commit observado.

No modifica Malāk ni el contenido del Vault.

## Autoridad

```text
Agente:
observa, compara, valida, registra estado y genera evidencia

LLM:
no utilizado

Humano:
revisa informes y conserva toda autoridad de escritura y aprobación
```

El agente no puede:

- modificar `Aranwill/jarvis`;
- modificar archivos del Vault;
- crear ramas o commits;
- ejecutar `push`;
- abrir, aprobar o fusionar pull requests;
- modificar snapshots históricos;
- cerrar decisiones;
- utilizar LLM;
- integrarse con el Kernel o runtime de Malāk.

## Repositorios observados

| Rol | Repositorio | Rama | Acceso |
|---|---|---|---|
| Fuente operativa | `Aranwill/jarvis` | `main` | fetch e inspección |
| Vault derivado | `Aranwill/malak-project-vault` | `main` | fetch, inspección y validación local |

`fetch` actualiza únicamente referencias remotas de Git. No ejecuta `pull`,
`checkout`, `reset` ni modifica los working trees.

## Requisitos

- Python 3.12 o superior;
- Git disponible localmente;
- clones locales de ambos repositorios;
- acceso de lectura a ambos remotos;
- working trees en `main` y limpios;
- Vault local alineado con `origin/main`.

## Instalación de desarrollo

```powershell
cd D:\Ollama\malak-vault-sync-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Configuración local

Copiar el ejemplo sin publicarlo:

```powershell
Copy-Item `
  .\config\vault-sync.example.yaml `
  .\config\vault-sync.yaml
```

Revisar especialmente:

```yaml
source:
  local_path: D:/Ollama/jarvis
  remote: origin
  branch: main
  fetch: true

vault:
  local_path: D:/Ollama/malak-project-vault
  remote: origin
  branch: main
  fetch: true
```

`config/vault-sync.yaml` y `var/` están excluidos de Git.

## Validar configuración

```powershell
malak-vault-sync validate-config `
  --config .\config\vault-sync.yaml
```

Código de salida:

- `0`: configuración válida;
- `2`: configuración inválida.

## Ejecutar una observación

```powershell
malak-vault-sync run-once `
  --config .\config\vault-sync.yaml
```

La primera ejecución crea un baseline local:

```text
bootstrap: true
changed_files: 0
```

Las ejecuciones posteriores:

1. actualizan `origin/main` de ambos repositorios;
2. verifican identidad, rama, limpieza y alineación;
3. comparan el último commit observado con el HEAD remoto de Malāk;
4. detectan modificaciones, altas, bajas y renombres;
5. resuelven documentos candidatos del Vault;
6. validan rutas, Markdown, YAML y enlaces;
7. generan evidencia e informe con SHA-256;
8. guardan el nuevo estado solo después de completar el circuito.

Salidas locales:

```text
var/state/sync-state.json
var/state/sync-state.json.prev
var/evidence/<run_id>/
var/reports/<run_id>/
```

Códigos de salida:

- `0`: ejecución completada con `pass` o `pass_with_findings`;
- `1`: auditoría completada con conclusión `fail`;
- `2`: error operativo o de seguridad; el estado no avanza.

## Controles operativos

- comandos Git y combinaciones de argumentos allowlisted;
- identidad exacta de ambos remotos;
- timeout aplicado a todas las operaciones Git;
- límite de archivos modificados;
- límite total del paquete de evidencia;
- límite de tamaño por documento candidato;
- lock de ejecución;
- estado escrito de forma atómica con backup;
- identificadores de ejecución con microsegundos;
- credenciales sanitizadas en evidencia e informes;
- snapshots históricos del Vault fuera del allowlist.

## Automatización

El comando `run-once` ya puede ser invocado por el Programador de tareas de
Windows. La instalación del scheduler se realiza como un paso operativo
separado, después de validar una ejecución en la PC del owner.

El scheduler no concede autoridad adicional: cada corrida permanece en
`dry-run` y solo genera estado, evidencia e informes locales.

## Pruebas

```powershell
python -m pytest
python -m compileall .\src .\tests
git diff --check
```

GitHub Actions repite estas validaciones en cada pull request y en cada cambio
integrado a `main`.

## Historial de Gates

```text
Gate 0 — relevamiento de solo lectura
Gate 1 — workspace y configuración
Gate 2 — inspección Git de solo lectura
Gate 3 — estado persistente local
Gate 4 — paquete de evidencia
Gate 5 — resolución de documentos candidatos
Gate 6 — validadores deterministas
Gate 7 — informe de auditoría
Gate 8 — runner, lock y polling externo
Gate 9 — validación final de Fase 1
Operational Gate 1 — CLI run-once
Operational Gate 2 — detección remota segura
Operational Gate 3 — persistencia y límites
Operational Gate 4 — reglas y renombres
Operational Gate 5 — validación end-to-end
```
