# Granolaupdater — Ronda 2 de mejoras (pendiente de ejecución)

> Plan generado el 2026-07-05 tras análisis completo del código. Estado: **aprobado en alcance (Fases 1-5, verificación con sync real), aún no ejecutado**.
> Rama sugerida: `improvements-2026-07b` desde `main`. Un commit por ítem; cada uno deja `ruff check .` y `pytest` en verde.

## Context

La ronda 1 (14 commits) ya está mergeada y pusheada en `main`: resiliencia HTTP, hidratación batch, path de updates, dry-run gratis, tests, tarea programada con ventana rodante de 3 días. Esta ronda ataca lo que quedó: bugs de corrección, lógica triplicada (fuente de divergencias .txt/.md) y gaps de tests/docs.

Hallazgo descartado: `logs/`, `dist/`, `build/`, `config.yaml` NO están trackeados en git (`.gitignore` ya los cubre) — no hay tarea de limpieza git.

---

## Fase 1 — Bugs de corrección (bajo riesgo)

### 1a. Defaults duplicados en `config.from_yaml` (bug del modelo descontinuado)
`src/granola_sync/config.py`
- `from_yaml` (líneas 69-87) duplica cada default literal; el fallback de `model` en línea 80 es `"claude-sonnet-4-20250514"` (descontinuado) mientras el dataclass (línea 25), `ClaudeEnricher`, `config.example.yaml`, README y tutorial dicen `"claude-opus-4-8"`. El `config.yaml` real tiene `enrichment:` sin `model:` → resuelve al sonnet muerto.
- Fix de raíz: reemplazar el merge manual por construcción introspectiva de dataclass:
  ```python
  def _merge(dc_type, data: dict):
      names = {f.name for f in dataclasses.fields(dc_type)}
      return dc_type(**{k: v for k, v in data.items() if k in names})
  # config.sync = _merge(SyncConfig, data.get("sync") or {})  # "or {}" — un "sync:" vacío parsea a None
  ```
- Tests nuevos `tests/test_config.py`: enrichment sin model → default del dataclass (test de regresión); archivo vacío; sección `sync:` con valor None; keys desconocidas ignoradas; expansión `~`; `validate()` (vault inexistente, credenciales, enrichment sin api_key, historical sin --from).

### 1b. N+1 en el exporter
`src/granola_sync/exporter/runner.py:131` — llama `api.get_documents_batch([doc.id])` un id por iteración. Hidratar todo antes del loop (como hace `engine._process_new`): un `full_map = {d.id: d for d in api.get_documents_batch([d.id for d in docs])}` con try/except de fallback. El cliente ya trocea en chunks de 50. Emitir un `ExportProgress(0, total, "Descargando contenido…")` inicial.

### 1c. Engine: ventana de updates, doble scan, mkdir
`src/granola_sync/sync/engine.py`
- `keep()` de daily/historical filtra solo por `created_at` → un doc *editado* dentro de la ventana pero creado antes nunca se detecta como update. Fix: `keep = created_at >= cutoff OR updated_at >= cutoff` (en ambos modos). El doc entra a `_process_new` y ahí la comparación `granola_updated` existente decide update/skip.
- `scan_vault_for_granola_ids` corre 2 veces por sync (en `_sync_daily` línea 109 y en `_process_new` línea 153): pasar el `id_map` como parámetro a `_process_new`.
- Línea 334: `notes_dir.mkdir(parents=True, exist_ok=True)`.
- Tests (`tests/test_engine.py`, freezegun): doc viejo editado reciente → update si está en vault, create si no; scan una sola vez (monkeypatch con contador); `notes_folder` anidado.

### 1d. GUI: estados cancelado / cero reuniones
`src/granola_sync/exporter/runner.py` + `src/granola_sync/gui/app.py`
- `ExportResult.cancelled: bool = False`; setearlo en el break de `should_cancel`.
- `ResultFrame`: si `cancelled` → "Exportación cancelada / Se alcanzaron a exportar N reuniones" (hoy muestra "✔ Listo" verde). Si `written == 0 and not cancelled` → "No se encontraron reuniones en el rango elegido" (hoy: "Procesando 0 de 0").
- Tests solo a nivel runner (flag cancelled, export con 0 docs); no testear widgets Tk.

## Fase 2 — Consolidar extracción de contenido + fixes de rendering

### 2a. Nuevo `src/granola_sync/converters/content.py`
La lógica de "mejor resumen" existe 3 veces con orden divergente: `engine._process_document` (268-307, único que revisa `doc.panels`), `txt_formatter._extract_summary_text` (68-98, prefiere notes_plain), `md_formatter._summary_markdown` (22-48, prefiere notes_markdown).
- `best_summary_markdown(doc) -> str`: prioridad canónica `last_viewed_panel (dict→PM, str→HTML) > notes dict > notes_markdown > notes_plain > otros panels > overview > summary`, devuelve `""`.
- `best_summary_text(doc) -> str`: `strip_markdown(best_summary_markdown(doc))`.
- Los 3 consumidores llaman al helper; `txt_formatter` conserva su placeholder `"(Sin resumen disponible)"`.
- Tests `tests/test_content.py`: un fixture por nivel de prioridad + doc solo-panels (regresión del gap txt/md) + panel HTML string.

### 2b. Frontmatter en `template.py`
- Línea 63: emitir `status: processed` solo si hubo enrichment; omitirlo si no (convención "omitir campos vacíos" ya presente en el archivo).
- Líneas 31-33: `date`/`time` sin `astimezone()` muestran el offset de origen, no hora local (el .txt sí convierte). Agregar propiedad `meeting_date_local` a `GranolaDocument` (`api/models.py`) y usarla en `template.py`, en el `date_str` de filename del engine (líneas 177, 255), en `txt_formatter._format_date_es` y en el filename de `md_formatter` — misma fecha local en filename y frontmatter. Las notas ya sincronizadas se matchean por `granola_id`, no por filename → sin duplicados.

### 2c. Unificar rendering de transcript
Nuevo `src/granola_sync/converters/transcript.py`: `transcript_lines(utterances) -> list[tuple[elapsed, speaker, text]]` — mover de `txt_formatter._format_transcript` (101-128) el `_EMBEDDED_SPEAKER_RE`, el cálculo de offsets elapsed y las etiquetas Tú/Otro. Decisiones: offsets elapsed ganan sobre hora absoluta sin tz (el bug del .md en `template.py:101-104`); etiquetas en español ganan sobre "You/Speaker". `txt_formatter` renderiza `[{ts}] {speaker}: {text}`; `template.py` renderiza `**[{ts}]** _{speaker}_: {text}`. Tests `tests/test_transcript.py`: stripping de speaker embebido, elapsed con timestamps naive/aware mezclados, orden.

### 2d. Dedups menores
- `_as_utc` → `utils.as_utc()`; borrar copias de `engine.py:100` y `runner.py:80`.
- `participant_names` como propiedad de `GranolaDocument` (mover lógica de `txt_formatter._participant_names`). El frontmatter sigue con emails.
- `logging_config.setup_logging(log_dir, verbose, console=True, prefix="sync")`: `console=False` omite RichHandler, `prefix` controla filename y glob de limpieza. `gui/app.py:main` (454-465, FileHandler artesanal sin limpieza) pasa a llamar `setup_logging(..., console=False, prefix="granola-notes")` → gana poda de 30 días.
- NO unificar el dict `{"day":1,"week":7,"month":30}` del GUI con los modos CLI (superficies distintas, 4 líneas).
- Tests: `test_template.py` (sin `status` si no hay enrichment; hora consistente con `astimezone()` calculado igual — no hardcodear zona, Windows no tiene `tzset`); actualizar expectativas de `test_txt_formatter.py`/`test_md_export.py`.

## Fase 3 — Flag `--window N` + simplificar scripts

- `cli.py`: `--window N` (int, default 1) → `config.window`; `AppConfig.window: int = 1` (sección CLI overrides).
- `engine._sync_daily`: `cutoff = now - timedelta(days=config.window)` (default 1 ≡ 24h actual — retrocompatible con la tarea programada instalada).
- `scripts/run_sync.ps1`: reemplazar el branch historical/--from por `--mode=daily --window $Window` (mismos nombres de parámetro → la tarea registrada en Task Scheduler sigue funcionando sin tocar).
- `Granola Sync Diario.sh`: `python3 -m granola_sync --mode=daily --window 3 --config config.yaml` — arregla la divergencia macOS (hoy usa `--mode=daily` plano, sin resiliencia). Revisar si existe par "Semanal".
- `Granola Sync Diario.bat`: eliminar el hack `for /f` con Python inline, misma línea.
- Tests: engine con `window=3` (doc de hace 2 días entra, de hace 4 no); `window=1` reproduce tests 24h existentes sin cambios.

## Fase 4 — Backfill de tests

- `tests/test_export_runner.py`: `export_documents` end-to-end con respx (patrón ya establecido en `test_client.py`): batch llamado 1 vez por ≤50 docs, archivos escritos, fallo de transcript tolerado, errores contados, cancelación temprana. Si el wiring de credenciales molesta, agregar parámetro opcional `api:` a `export_documents` para inyección.
- `tests/test_token_manager.py`: paths HTTP de `_refresh` con respx (éxito, 4xx, error de red, `force_refresh`).
- `tests/test_html.py`: listas anidadas, entidades, `<br>`, input vacío, tags sueltos.
- GUI: extraer el parsing de `ConfigFrame._parse_date` a función pura (`utils.parse_iso_date`) y testearla; no instanciar Tk en CI.

## Fase 5 — README + ProseMirror

- `README.md`: árbol del proyecto (falta `constants.py`, `exporter/md_formatter.py`, `gui/__main__.py`); documentar entry point `granola-notes-gui`; corregir framing "exporter = solo txt" (el GUI ya exporta .md); documentar `--window`.
- `prosemirror.py`: agregar nodos `codeBlock` (fenced), `blockquote` (prefijo `> `, recursivo), `hardBreak` (`\n`), `taskList`/`taskItem` (`- [ ]`/`- [x]` desde `attrs.checked`). NO tablas (el fallback actual ya rescata el texto). Tests por tipo de nodo.
- Limpieza local opcional de disco (logs viejos, `build/`, `dist/logs`) — no es tarea git.

## Explícitamente NO hacer

1. Early-stop de paginación en `get_documents` — asume orden del API no verificado; si no está ordenado por recencia, el daily perdería reuniones en silencio.
2. Reescritura de historia git / limpieza de artefactos — nada está trackeado.
3. Soporte de tablas Markdown en ProseMirror — costo > beneficio.
4. Cambiar participants del frontmatter a nombres — rompe shape existente sin beneficio.
5. Rework arquitectónico del GUI o tests de widgets tkinter.

## Verificación (aprobada: sync real contra el vault)

Por fase: `ruff check .` + `pytest`. Al final:
1. `python -m granola_sync --mode=dry-run --config config.yaml` (gratis).
2. **Antes de Fase 2**: exportar con el GUI (md y txt, "Última semana") a `scratch/before/`; después de Fase 2 a `scratch/after/`; diff — únicos cambios esperados: línea `status` ausente, horas locales, formato de transcript en .md. Cualquier otro diff es regresión.
3. `scripts/run_sync.ps1 -Window 3` real contra el vault de iCloud; revisar frontmatter/transcript de una nota actualizada.
4. GUI: export de 1 día a carpeta scratch en ambos formatos + cancelar a mitad de run (pantalla de cancelado).
5. Antes de mergear a `main`: correr la línea de comando exacta registrada en Task Scheduler.

## Archivos críticos

- `src/granola_sync/config.py`, `src/granola_sync/sync/engine.py`, `src/granola_sync/exporter/runner.py`
- `src/granola_sync/converters/template.py`, `converters/content.py` (nuevo), `converters/transcript.py` (nuevo), `converters/prosemirror.py`
- `src/granola_sync/api/models.py`, `utils.py`, `logging_config.py`, `cli.py`, `gui/app.py`
- `scripts/run_sync.ps1`, `Granola Sync Diario.bat`, `Granola Sync Diario.sh`, `README.md`
