# Incremento Correctivo Integral 5 — Informe de implementación y validación

## Estado

```text
Implementación local: completa en la rama de la PR #7
Validación automatizada Linux: completa sobre el HEAD publicado
Validación de documentos reales del Vault: completa
CI Windows/Linux: gate obligatorio sobre cada HEAD final de la PR
Validación nativa Windows con gh: pendiente
Publicación como PR draft: completa; PR #7
Merge: no autorizado
Cierre operativo: no declarado
```

Fecha: 2026-08-02.

## Baseline verificado

| Componente | Rama | HEAD |
|---|---|---|
| Malāk | `main` | `b4d1d512fe953d593608391390f82ab500fdc9d6` |
| Project Vault | `main` | `46672bcb971dbcdfcf25b1a4c7359aec9f047980` |
| Vault Sync Agent | `main` | `0feed6eae3d3919ea4867891c12eda5eea81c511` |

La implementación se preparó en
`agent/increment-5-integral-corrections`. Malāk y el Vault permanecieron
sin modificaciones.

La ejecución CI #14 verificó el HEAD publicado `70f82fab` con `256 passed`
en Windows Server 2025 y Ubuntu. Toda corrección posterior debe volver a
superar la misma matriz sobre su propio HEAD antes del merge; el estado de
ese gate se consulta en GitHub y no se congela como vigente en este informe.

## Brechas reconciliadas

1. El bootstrap de `controlled-proposal` establece el primer
   `last_reconciled_commit` sin crear una propuesta retrospectiva.
2. Cada proyección se valida nuevamente después de generar el contenido
   final y antes del primer commit.
3. El frontmatter YAML de Markdown rechaza delimitadores incompletos,
   ausencia del delimitador inicial, sintaxis inválida, claves duplicadas
   y raíces que no sean mappings.
4. Los wikilinks de Obsidian se resuelven contra el Vault, incluyendo
   nombres con puntos y extensión `.md` omitida.
5. La denylist protege la ruta real e inmutable
   `09-repository-snapshots/**`.
6. Una PR creada antes de un fallo de persistencia se recupera solo si su
   identidad remota es única y coincide con todos los invariantes
   gobernados; el rango original se conserva aunque Malāk avance después
   del fallo, y el agente se detiene para exigir reconciliación.
7. Los informes registran `triggered_by: manual-on-demand`.
8. La versión pública, el metadata del paquete y los informes quedan
   alineados en `0.3.0`.
9. Las reglas cubren todas las rutas vigentes de Malāk; los dos artefactos
   de `documents/projects/jarvis/archive/` permanecen deliberadamente fuera
   por ser históricos.
10. CI ejecuta la suite en `ubuntu-latest` y `windows-latest`.
11. La documentación distingue el cierre histórico del Incremento 4 de la
    certificación pendiente del baseline actual.
12. El informe auditable y `AUDIT_INDEX.md` también se validan después de
    escribir su contenido final y antes del segundo commit.

## Validación ejecutada

```text
python -m pytest -q: 259 passed en el checkout Linux corregido
python -m compileall -q src tests: aprobado
git diff --check: aprobado
validación de ocho documentos reales del Vault: aprobada
```

Además, los ocho documentos allowlisted del Vault real fueron evaluados
con los validadores de Markdown, frontmatter, enlaces y wikilinks. Resultado:

```text
vault_candidate_validation: PASS
```

El contraste de reglas contra el árbol real de Malāk dejó sin candidato
únicamente:

- `documents/projects/jarvis/archive/estado_actual_jarvis_v0.4.1.md`;
- `documents/projects/jarvis/archive/manifest_jarvis_legacy.yaml`.

La exclusión es deliberada: ambos documentos son históricos y no deben
alterar el baseline derivado vigente.

## Validación pendiente en Windows

La matriz CI ejecuta la suite y `compileall` de forma nativa en Windows y
Linux sobre cada HEAD publicado. También debe ejecutarse una prueba aislada
con GitHub CLI autenticado para verificar el camino de recuperación remota
sin leer ni modificar el estado operativo real.

Esa prueba deberá usar:

- una copia temporal de `sync-state.json`;
- clones limpios en `main`;
- una PR histórica o descartable con identidad conocida;
- comprobación de URL, rama, base, HEAD, cuerpo, estado y borrador;
- ausencia de merge y de escritura directa en el Vault;
- eliminación completa de los artefactos temporales al finalizar.

Hasta registrar esa evidencia y comprobar el gate CI sobre el HEAD final,
el incremento no está cerrado operativamente.

## Invariantes preservadas

- Malāk permanece de solo lectura para el agente.
- El Vault solo puede recibir propuestas en una rama aislada.
- Toda PR se crea como draft.
- El agente no aprueba ni integra PR.
- No existe scheduler activo.
- No se utiliza LLM.
- `last_applied_commit` permanece en `null`.
- `operational_authority` permanece en `none`.
- Kernel, Planner y runtime de Malāk permanecen intactos.

## Cuatro preguntas de ley

1. **Blueprint:** aprobado; el agente continúa como tooling externo.
2. **Constitución Cognitiva:** aprobado; no infiere decisiones ni contenido.
3. **Gobernanza:** aprobado; conserva PR draft, revisión humana y fallo seguro.
4. **Simplicidad del Kernel:** aprobado; el Kernel no fue modificado.

## Conclusión provisional

La implementación y la validación local del Incremento Correctivo Integral 5
están completas en la PR draft #7. El merge y el cierre operativo requieren
una aprobación humana posterior, CI verde sobre el HEAD final en ambos
sistemas y validación nativa aislada en Windows.
