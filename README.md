# Malāk Vault Synchronization Agent

Herramienta externa y determinista para auditar cambios entre el repositorio oficial de Malāk y el Malāk Project Vault.

## Estado

```text
Fase 1
Gate 1 — workspace y configuración
```

El agente todavía no está operativo.

La implementación actual se limita a:

- estructura mínima del proyecto;
- configuración YAML;
- validación estricta;
- comando `validate-config`;
- pruebas deterministas.

## Autoridad

El agente no posee autoridad operativa ni documental.

```text
Agente:
observa, compara, valida y genera evidencia

LLM:
no utilizado en la Fase 1

Humano:
revisa, aprueba y autoriza cada gate
```

## Repositorios observados

Fuente de verdad operativa:

```text
Aranwill/jarvis
rama: main
modo: solo lectura
```

Vault documental derivado:

```text
Aranwill/malak-project-vault
rama: main
modo: solo lectura durante la Fase 1
```

## Límites de la Fase 1

El agente no puede:

- modificar `Aranwill/jarvis`;
- modificar archivos del Vault;
- crear ramas;
- crear commits;
- ejecutar `push`;
- abrir pull requests;
- aprobar o mergear pull requests;
- modificar snapshots históricos;
- cerrar decisiones;
- utilizar LLM;
- ejecutar automatización completa;
- integrarse con el Kernel o runtime de Malāk.

## Requisitos

- Python 3.12 o superior;
- Git disponible localmente;
- acceso de lectura a los repositorios observados.

## Instalación de desarrollo

Crear y activar el entorno virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instalar el proyecto con dependencias de desarrollo:

```powershell
python -m pip install -e ".[dev]"
```

## Configuración

El archivo de ejemplo se encuentra en:

```text
config/vault-sync.example.yaml
```

La configuración local futura deberá utilizar:

```text
config/vault-sync.yaml
```

Ese archivo está excluido de Git.

En Gate 1:

```text
mode: dry-run
source.fetch: false
```

## Validar configuración

Mediante el módulo:

```powershell
python -m malak_vault_sync.cli validate-config --config .\config\vault-sync.example.yaml
```

Mediante el entrypoint instalado:

```powershell
malak-vault-sync validate-config --config .\config\vault-sync.example.yaml
```

## Pruebas

```powershell
python -m pytest
python -m compileall .\src .\tests
```

## Gates

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
Gate 9 — validación final
```

No debe iniciarse un gate posterior sin aprobación humana explícita.