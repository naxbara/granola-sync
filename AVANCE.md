# Avance — Granolaupdater

> Última actualización: 2026-11-25

Sincroniza las notas de reunión de Granola al vault de Obsidian
(`Reuniones/` + `Transcripciones/`). Repo: `github.com/naxbara/granola-sync`,
rama principal `main`. Corre solo cada noche a las 21:00 vía la tarea de
Windows `GranolaSyncDaily`, con ventana móvil de 3 días.

---

## Plan

### Ronda 3 — participantes y empresas (2026-08-23)

Nace de dos fallas de datos medidas ese día: los asistentes se estaban
perdiendo (la línea `Meeting participants:` cayó de 34/51 notas en abril a
1/50 en agosto) y Granola inventa la empresa en sus resúmenes.

- [x] **Fase 0 — Diagnóstico.** Por qué cayó el calendario, de dónde sale el
      "Kauel", si la diarización se puede activar
- [x] **Fase 1 — La transcripción nace separada.** Absorber lo que hacía a
      mano `extraer-transcripciones.py` del vault
- [x] **Fase 2 — Asistentes con nombre, empresa y rol.** Cascada Granola →
      Google Calendar → `Personas/`
- [x] **Fase 3 — Quién habló.** Regla determinista del 1:1, más sugerencia
      con confirmación humana cuando no hay invitación
- [ ] **Fase 4 — Empresas: detectar, no asumir.** Marcar las organizaciones
      que el resumen afirma sin respaldo en la transcripción ni en los
      dominios de los asistentes. **Es la que cierra el pedido original**
- [ ] **Fase 5 — Skills del vault.** `enrich-vault`, `personas-vault`,
      `mantenimiento-vault` y los zips de Cowork, atrasados 4-6 semanas
- [ ] **Fase 6 — Higiene del repo.** ~~Bug 1a del PLAN ronda 2 (modelo
      descontinuado como fallback)~~ — *resuelto el 2026-09-17 (`93ef586`)*;
      falta limpiar los `*.bak-migracion`

### Ronda 2 — pendiente desde 2026-07-05

`PLAN-mejoras-ronda2.md` (untracked, aprobado en alcance, **sin ejecutar**):
bugs de corrección, lógica de contenido triplicada entre `engine.py`,
`txt_formatter.py` y `md_formatter.py`, flag `--window`, backfill de tests.
Sigue vigente; la Fase 6 de arriba se come solo una parte.

---

## Ejecutado

### 2026-11-25

- **Granola 7.821 movió la sesión a `stored-accounts.json.enc` y el sync dejó de leerla.** Granola se actualizó solo a las 19:34 en el servidor. Al arrancar, migra los tokens de `supabase.json` a `stored-accounts.json` y vacía el primero, que quedó en 30 bytes. Desde ese momento fallaron el sync de las 21:00 (`GranolaSyncDaily`, resultado 1) y el paso `sync` del digest, con «No valid tokens found», aunque Granola tenía la sesión abierta. Reabrir Granola no lo arreglaba. El formato nuevo se sacó del código de la app (`resources/app.asar`), sin abrir las credenciales: `{version: 2, currentUserId, accountsById: {<id>: {user, tokens, savedAt, workspaces}}}`, donde `tokens` es el mismo objeto WorkOS de antes.
  - `credentials.py`: si `stored-accounts.json(.enc)` trae `version`, manda ese archivo, y se lee la cuenta de `currentUserId`. Sin `version` (antes de que la app migre), se sigue leyendo `supabase.json` como antes. La renovación de tokens escribe en el mismo archivo y solo toca los tokens de esa cuenta. Los campos de token que el modelo no conoce se conservan, y se mantiene el tipo, objeto o texto JSON, en que venían. La escritura cifrada y en texto plano quedó en `_write_blob`, común a los dos formatos.
  - `utils.credentials_exist` también reconoce `stored-accounts.json(.enc)`.
  - 6 tests nuevos en `test_credentials.py`, **202 en verde**. Un dry-run real a las 22:04 trajo 753 documentos, ninguno nuevo desde el sync manual de las 19:32, así que no hubo que rehacer el digest del día. **La escritura de tokens renovados contra el archivo real no se probó**: el token seguía vigente y no hubo renovación. La primera corrida que renueve el token es la prueba.
  - Sin commit.

### 2026-11-20

- **Granola sin sesión ya no da un traceback.** Un sync manual de la mañana cayó con `ValueError: No valid tokens found in …\supabase.json`. Hacia las 9:12, Granola reescribió `supabase.json.enc` y `stored-accounts.json.enc` (re-login o renovación de sesión), y el archivo descifrado venía sin `workos_tokens`. Al rato ya traía tokens, y un dry-run funcionó sin tocar nada. El mensaje despistaba: nombraba `supabase.json`, que en el servidor ni existe, porque el archivo que se lee es el `.enc`.
  - `credentials.py`: excepción `NoTokensError` (subclase de `ValueError`), que nombra el archivo que en verdad se leyó y dice qué hacer (abrir Granola, verificar la sesión, reintentar). El CLI la atrapa y sale con código 1, sin traceback.
  - **Los `.bat` Diario y Semanal ya no dicen «Sincronizacion completada» cuando falla.** Leen el código de salida: `0` = completada, `3` = completada sin índices, cualquier otro = «FALLO (codigo N)». Terminan con `exit /b` del mismo código. Los IF van en una sola línea porque los `.bat` tienen fin de línea LF.
  - 1 test nuevo en `test_credentials.py`, **196 en verde**. Los `.bat` se probaron con códigos simulados 0, 3 y 1.

### 2026-11-02

- **Si el índice falla, se reintenta y se avisa.** El 30-oct el sync escribió las reuniones, pero `sc_vault` no pudo regenerar `Indices/`: un clipping tenía una ruta de 302 caracteres (arreglado en `segundo-cerebro` `46bf9b4`). El error quedó como un WARNING en el log y el digest dijo `"sync":"ok"`. Además, el fin de semana nadie lo reintentó, porque sin notas nuevas el sync no regenera.
  - **Reintento**: cuando la regeneración falla queda `logs/indices_pending`. Mientras exista, el sync siguiente regenera aunque no haya escrito notas, y la marca se borra cuando sale bien.
  - **Código de salida 3**: las notas se escriben igual, pero el CLI termina con `3`. Así la tarea programada aparece con error y el digest marca `sync: error: exit code 3`, lo que dispara su alerta por correo. **También afecta a `cerebro run granola` de la beta**, que lo reporta como error cuando se reconstruya el zip.
  - **Avisos en una corrida que sale bien**: lo que el generador escribe en stderr (por ejemplo, `skipped unreadable note`) queda en el log y en pantalla. Antes se descartaba.
  - 6 tests nuevos en `test_indices.py`, **195 en verde**. La salida con código 3 del CLI no tiene test propio.

### 2026-09-19

- **Este paquete entra en la beta 0 de Segundo Cerebro** como wheel (`granola-obsidian-sync`), y `sc run granola` lo llama con una config propia (sin enriquecimiento, índices con `sc_vault`). Probado en un entorno limpio: `--mode historical` importó 21 reuniones a un vault nuevo sin errores.
- **Comentarios con nombres reales reemplazados por ejemplos genéricos** (`1c5ce13`): el escaneo del build de la beta encontró el nombre del dueño, un cliente y un socio como ejemplos de calibración en `config.py`, `speakers.py` y `engine.py`. Solo comentarios; 189 tests sin cambios.

### 2026-09-18

- **`indices.engine`** (`59862ae`): elige quién regenera `Indices/` al final
  del sync — `script` (default, el generador del vault), `sc_vault`
  (`python -m sc_vault indices`, misma salida detrás del perfil del vault) o
  `auto` (`sc_vault` si está instalado, si no el script). Un `sc_vault`
  ausente o un engine desconocido se reportan como cualquier otra falla: nunca
  tumban el sync. 5 tests nuevos, **189 tests**.
- **Producción usa `sc_vault`** (tramo 5 del plan Segundo Cerebro, 21:30):
  `sc_vault` instalado editable en `C:\Python314`, `<vault>/vault.yaml` con el
  perfil real y `indices.engine: auto` en el `config.yaml` real. Verificado:
  el perfil carga (dueño + 6 correos) y `--mode=dry-run` corre sin errores
  sobre los 570 documentos. Paso atrás si algo falla: `indices.engine: script`
  y borrar `<vault>/vault.yaml`.

### 2026-09-17

**Las horas de las notas venían en UTC (+3/+4 h).** Granola entrega
`created_at` y los timestamps del transcript en UTC (`...Z`), y el código los
formateaba con `strftime` sin convertir. Las reuniones con evento de calendario
salían bien porque ese `dateTime` trae offset (`-03:00`); las **sin calendario**
(la mitad) quedaban corridas, y las de después de las 20-21 h caían al día
siguiente — también en el nombre del archivo.

- **`utils.to_local()`**: `meeting_date` y las marcas `[hh:mm:ss]` del
  transcript pasan por la zona local de la máquina. `utils.LOCAL_TZ` permite
  fijarla; los tests la fijan en UTC (`conftest.py`) y `test_local_time.py`
  reproduce el bug con UTC-3. **161 tests.**
- **Vault corregido** contra la API de Granola como fuente de verdad (verificado
  con Google Calendar): 281 horas de reunión, marcas de hora de 555
  transcripciones, y 6 reuniones que cambiaban de día renombradas junto a su
  transcripción, con los links actualizados en 23 notas. Quedaron 567/567
  reuniones calzando. Sin tocar: 5 notas cuyo `granola_id` ya no existe en
  Granola y 2 transcripciones con marcas ambiguas.

**Plan Segundo Cerebro (producto), Fase 0 y tramo 2 de la Fase 1** (el plan
vive en el vault: `Planes/Plan-Producto-Segundo-Cerebro-Sep2026.md`):

- **Aviso de reuniones viejas editadas en Granola** (`93ef586`): el sync
  diario las lista en `stats.stale` y en el log **sin reescribirlas**, porque
  una actualización pisa la nota entera y borraría el enriquecimiento. El
  modelo por defecto de `enrichment` sale del dataclass; `test_config.py`
  compara los defaults de todas las secciones por introspección.
- **Golden de un sync completo** (`7d543a0`): `tests/fixtures/golden_sync/`,
  nota + transcripción byte a byte. Regenerar solo a propósito con
  `UPDATE_GOLDEN=1`.
- **El sync lee el perfil del vault** (`<vault>/vault.yaml`, paquete
  `sc_vault` del repo `segundo-cerebro`), commit `e2e3212`. Precedencia
  `config.yaml` > perfil > defaults. Toma carpetas (reuniones,
  transcripciones, `people_folder` nuevo), correos del dueño, idioma y zona
  horaria. Las palabras que el sync escribe en las notas pasan a `vocab.py`
  (es copiado literal, en nuevo). **`sc_vault` es opcional** (extra
  `profile`): sin él, o con un perfil roto, todo queda como antes. Verificado:
  el `config.yaml` real da la misma configuración con y sin `sc_vault`, y un
  dry-run real no muestra cambios. Producción no tenía `sc_vault`
  instalado hasta el tramo 5 (18-sep, ver arriba). **184 tests.**

### 2026-09-06

**El cambio de hora corrió el sync una hora, y a las otras cinco tareas
también.** Chile entró en horario de verano la madrugada del 6-sep (UTC-4 →
UTC-3) y `GranolaSyncDaily` pasó a correr **22:00 en vez de 21:00**. La causa
no es de este proyecto sino del cmdlet que usan todos los instaladores:
`New-ScheduledTaskTrigger -At '21:00'` escribe el `StartBoundary` **en UTC**
(`2026-09-07T00:00:00Z`), y un boundary con zona ancla la tarea a un instante
absoluto — el instante se respeta, la hora de reloj no.

- **Las seis tareas reescritas** con el boundary sin zona (`...T21:00:00`), que
  es como Windows entiende "hora local". Verificado contra el respaldo de cada
  XML: idénticas salvo la hora — acciones, argumentos, principal y settings
  intactos.
- **`scripts/install_scheduled_task.ps1` normaliza el boundary** antes de
  registrar, para que reinstalar no reintroduzca el desfase. Mismo arreglo en
  los otros tres instaladores del equipo (DailyDigest ×2, ProfileScout).
- **Nada se había roto**: las seis se movieron juntas, así que la cadena de los
  domingos conservó su orden y sus separaciones. El costo real era en abril,
  cuando se irían para el otro lado.
- Regla registrada en el vault:
  `Notas/Decisiones/2026-09-06-las-tareas-programadas-van-en-hora-local.md`.

### 2026-09-04

**La segunda reunión del día dejó de leerse como duplicado.** "Revisión
Política IA Volcom v2" nunca entró al vault: el fuzzy match la comparó con la
nota de la reunión anterior del mismo día (score ≈95 contra el umbral 85) y la
saltó, transcripción incluida. Al destaparlo apareció una causa mayor.

- **`scan_vault_for_granola_ids` apuntaba a la transcripción, no a la
  reunión.** Las notas de `Transcripciones/` repiten el `granola_id` de su
  reunión y, como esa carpeta ordena después de `Reuniones/`, ganaban la
  entrada del mapa: 507 de 524 ids apuntaban al archivo equivocado. Ahora se
  excluyen por `type: transcripcion` (constante `TRANSCRIPT_NOTE_TYPE`).
- **Efecto colateral que llevaba semanas silencioso:** las transcripciones no
  llevan `granola_updated`, así que toda reunión editada en Granola después de
  su sync se saltaba en vez de regenerarse. En todos los logs hay **un solo**
  `Update queued`. Con el mapa arreglado, la comparación vuelve a hacerse
  contra la nota correcta.
- **El fuzzy solo mira notas sin `granola_id`.** Lo que escribió este sync se
  desduplica por id; una nota con id de *otra* reunión no puede ser un
  duplicado. El fallback queda para notas escritas a mano o previas al id.
- **`fuzzy_threshold: 0` lo apaga** (antes 0 hacía matchear todo).
- Reunión y transcripción (1356 líneas) ya en el vault. **157 tests en verde.**

### 2026-08-31

**El sync regenera los índices del vault.** La Fase 3 del
[[Plan-Segundo-Cerebro-IA-Agosto-2026]] creó cuatro índices derivados en
`Indices/` del vault (reuniones por cliente, por persona, línea de tiempo y
decisiones) que se construyen **desde el frontmatter que escribe este sync**.
Quedaban viejos apenas entraba una nota nueva, así que el disparador correcto
es este, no un reloj aparte: se regeneran **cuando cambia la fuente**.

- **Módulo nuevo `sync/indices.py`** con `regenerate(config, wrote_notes)`.
  Corre el generador del vault con el mismo intérprete que el sync
  (`sys.executable`, no el Python del PATH — un venv no debe salirse de su
  propio entorno).
- **Config nueva `indices:`** (`enabled`, `script`, `timeout_seconds`).
  Apagada por defecto en `config.example.yaml`, encendida en el `config.yaml`
  de Sebastián. El `script` se resuelve relativo al vault o absoluto.
- **Enganchado en `cli.py`** justo después de `engine.run()`.

**Las dos reglas que definen el módulo**, ambas cubiertas por tests:

1. **Nunca hace fallar el sync.** Script ausente, exit code distinto de cero,
   timeout o `OSError` vuelven como `IndicesResult.failed` y se reportan como
   warning con el comando para rehacerlo a mano. Las notas son el producto;
   los índices son derivados y se reconstruyen cuando sea.
2. **Solo corre si algo cambió.** Sin notas nuevas ni actualizadas, o en
   `--mode=dry-run`, no se ejecuta. Un dry-run promete no escribir nada, y eso
   incluye los índices.

**11 tests nuevos** (`tests/test_indices.py`) — los tres casos de "no debe
correr", el camino feliz, los argumentos que se pasan (`--vault` y `--apply`:
sin `--apply` el generador es dry-run y no escribiría nada), ruta absoluta, y
los cuatro modos de falla. Suite completa: **154 en verde**.

Verificado end-to-end contra el vault real: `--mode=dry-run` no toca los
índices, y con `wrote_notes=True` los cuatro archivos de `Indices/` quedan
regenerados con el timestamp de la corrida.

### 2026-08-23

**Fase 0 — diagnóstico (solo lectura, sobre el cache descifrado de Granola).**
Los tres hallazgos, dos de los cuales cambiaron el plan:

- **Calendario conectado, pero al equivocado.** Granola sincroniza al día,
  solo que mira `sebastian.suarez@kauel.com` y `francisco.marshall@kauel.com`.
  La agenda real vive en `ssuarez@gmail.com`. Medido sobre el 16-22 ago: 15
  reuniones, **0 con `participants:`**, y el calendario de gmail tenía los
  correos de 10 de ellas.
- **El "Kauel" no se arregla renombrando.** El workspace es
  `slug: kauel.com` / `display_name: KYON`, plan `free`, rol admin. Como el
  nombre visible ya es "KYON", el resumen resuelve el "nosotros" contra el
  **dominio de la cuenta**, no contra el display name.
- **Diarización apagada y sin toggle.** `transcription_diarization: false`;
  las etiquetas de hablante son función de pago (`speaker_attribution_upsell`)
  y lo que Granola ofrece no es diarización de audio sino integración con
  Zoom/Meet. Evidencia: 250 utterances con **0** `detected_speaker_name`.
- Riesgo anotado: `transcription_retention_time_ms` = **72 h**. Si el servidor
  borra transcripciones a los 3 días, `--mode=historical` no las recupera.

**Fase 1 — transcripción separada** (`060cc27`). `converters/transcript.py`
nuevo; `template.py` gana `transcript_mode` (`separate` por defecto, `inline`
para el exporter de la GUI); `engine.py` escribe los dos archivos, la
transcripción primero para que el link nunca apunte al vacío; `--mode=verify`
detecta callouts cuya transcripción desapareció. Verificado byte a byte
contra `2026-08-21-habitat`: una nota recién sincronizada es **idéntica** a
una migrada por el script.

**Fase 2 — asistentes** (`98c4a21`). `converters/people.py` con cascada y
`Participant(email, name, company, title, source)`; rescata
`details.person.employment` (nombre, empresa, cargo) y `people.creator`, que
venía en el 100% de los documentos y se descartaba entero.
`sources/calendar.py` lee Google Calendar en solo lectura (`calendar.readonly`,
token propio, cliente OAuth compartido con DailyDigest), cruzando por hora
(±30 min) y título. `PersonasIndex` completa nombre/empresa/rol desde el vault
sin red: **273 correos indexados**. Resultado sobre el 19-21 ago: de **0 a 43
participantes**, 9/9 notas con alguien identificado por nombre.

**Fase 3 — hablantes** (`ded70bb`). Campos de diarización declarados para el
día que lleguen; regla determinista del 1:1; y el flujo que pidió Sebastián:
cuando nadie figura en la invitación pero un nombre de `Personas/` aparece **en
el título y en lo hablado**, se anota como sugerencia sin tocar el cuerpo, y se
resuelve con `--mode=speakers` o escribiendo `speaker_confirmed:` en Obsidian.
La respuesta sobrevive a los resyncs. De **1 a 4 de 13** reuniones con hablante
nombrado.

Estado al cierre: **142 tests en verde**, ruff limpio, `main` pusheado. Todas
las pruebas contra un vault de prueba en el scratchpad — el vault real no se
tocó en ningún momento.

### 2026-08-09
- `861e98b` — soporte para instalaciones de Granola que solo traen
  `supabase.json.enc` (sin el archivo en claro).

### 2026-07-04 / 2026-07-05
- Ronda 1 de mejoras, 14 commits: dry-run gratis, hidratación por lotes, path
  de update para notas cambiadas, carpeta de notas configurable, log anclado a
  la config, instalador de la tarea programada, exportador GUI con salida
  `.md`, tests de engine/client/credentials/enricher/html y ruff.

---

## Próximos pasos

1. **Hora local — confirmada el 2026-09-17** contra la API: las 7 reuniones
   de las últimas 36 h traen fecha y hora en UTC-3. Quedan a mano, si
   importan, las 5 notas huérfanas de Granola y las 2 transcripciones
   ambiguas.
1b. **Tramo 5 del plan de producto** (con confirmación): instalar el extra
   `profile` (`pip install -e ".[profile]"`) en el Python del sync y crear el
   `vault.yaml` real. Hasta entonces el perfil no se lee en producción.
2. **Fase 4 — empresas sin asumir.** Es lo que originalmente pidió Sebastián y
   ahora tiene los insumos que le faltaban: dominios de correo reales y fichas
   de `Personas/` cruzadas. Detectar y marcar (`orgs_sin_respaldo`), nunca
   reescribir el cuerpo — **hay reuniones que sí son de Kauel**.
2. **Resolver las sugerencias pendientes** con `--mode=speakers` sobre las
   transcripciones nuevas que deje el sync nocturno.
3. **Confirmar el enganche de índices en una corrida nocturna real** con notas
   nuevas — hasta ahora se verificó forzando `wrote_notes=True`, porque el día
   que se implementó no llegaron notas nuevas.
4. **Ver un `Update queued` real.** La vía de actualización estuvo muerta desde
   agosto por el mapa de ids: hay que confirmar en una corrida nocturna que una
   reunión editada en Granola **dentro de sus primeras 24 h** se regenera de
   verdad (las más viejas ahora solo se avisan, ver Decisiones). Ojo con el otro lado de lo
   mismo: un `--mode=historical` sobre el histórico ahora **sí** puede
   reescribir notas viejas editadas a mano. Antes de correrlo, dry-run.
5. Fase 5 (skills) y Fase 6 (higiene del repo).

---

## Decisiones y bloqueos

- **2026-09-17 — Una reunión vieja editada en Granola se avisa, no se
  regenera.** Regenerar pisa la nota entera y borra lo que agregaron
  `enrich-vault` y `personas-vault`; las 2 detectadas ese día estaban
  enriquecidas. Registrada en el vault:
  `Notas/Decisiones/2026-09-17-un-cambio-en-granola-no-reescribe-una-nota-enriquecida.md`.
- **2026-09-17 — El perfil del vault es opcional y nunca manda sobre
  `config.yaml`.** Sin `sc_vault`, o con un `vault.yaml` roto, el sync queda
  idéntico. Las palabras que otras herramientas buscan literalmente (`> Ver:`,
  el título del callout) cambian solo junto con el idioma del vault. Registrada
  en el vault:
  `Notas/Decisiones/2026-09-17-la-identidad-del-dueno-vive-en-vault-yaml-no-en-el-codigo.md`.
- **2026-09-17 — La hora se convierte a la zona de la máquina, no a una zona
  fija en el config.** Windows y Mac corren en hora de Chile, y la zona del
  sistema sigue sola los cambios de hora. `utils.LOCAL_TZ` queda como punto
  para fijarla (lo usan los tests). Ojo en cualquier script que lea la API de
  Granola: `created_at` y los timestamps vienen en UTC; solo el `dateTime` del
  calendario trae offset.
- **2026-09-04 — El fuzzy de títulos no se apagó, se acotó.** Subir el umbral
  no arreglaba nada: un sufijo "v2" puntúa ≈95 y habría que exigir títulos
  idénticos. Apagarlo del todo dejaba sin red las notas hechas a mano. Se optó
  por sacar del universo de candidatos toda nota que ya tenga `granola_id`:
  esa pertenece a otra reunión y por definición no es un duplicado.
- **2026-09-04 — El `granola_id` de una transcripción no identifica la nota.**
  Regla del vault, no solo de este proyecto: cualquier mapa `id → archivo`
  tiene que excluir `type: transcripcion`. Registrada en el vault:
  `Notas/Decisiones/2026-09-04-el-granola-id-de-una-transcripcion-no-identifica-la-nota.md`.
- **2026-08-31 — Los índices del vault se regeneran acá, no en una tarea
  aparte.** El disparador es el cambio de la fuente, no un reloj: los índices
  salen del frontmatter que escribe este sync. Se descartó dejarlos al lint
  semanal del vault (quedaban hasta 7 días viejos) y una tarea programada
  propia (otra cosa que mantener, corriendo aunque no haya nada nuevo). El
  chequeo del `lint-vault` se conserva igual, pero como **red de seguridad**:
  detecta índices viejos si este enganche falló sin que nadie lo notara.
  Registrada en el vault: `Notas/Decisiones/2026-08-31-los-indices-se-regeneran-al-final-del-sync.md`.
- **2026-08-31 — El enganche es best-effort a propósito.** Si el generador
  falla, el sync **igual termina bien**. Invertir esa relación —que un índice
  derivado pueda tumbar la sincronización de las notas— sería subordinar el
  producto a su subproducto.
- **2026-08-23 — La transcripción va separada por defecto.** `transcript_mode`
  arranca en `separate` en el código, no solo en el `config.yaml` de
  Sebastián: es el comportamiento correcto ahora. `inline` queda para el
  exporter de la GUI, que escribe archivos sueltos fuera del vault.
- **2026-08-23 — "Transcripcion" se queda sin tilde.** Corregirla partiría el
  vault en dos formatos y rompería la detección de "ya procesada" de
  `extraer-transcripciones.py`. La uniformidad gana sobre la ortografía.
- **2026-08-23 — `participants:` sigue siendo lista de correos.** Es la llave
  de identidad con que `personas-vault` cruza las fichas; cambiarle el shape
  rompía el cruce. Los nombres van al cuerpo, en la línea `Asistentes:`.
- **2026-08-23 — Ante duda, no se escribe nada.** Dos eventos de calendario
  parecidos a la misma hora, un evento sin invitados o un timestamp sin zona
  horaria dejan la reunión sin asistentes. El caso que lo justifica:
  "Abastible" tenía a ±7 minutos un evento de 7 personas que no era esa
  reunión. Un roster equivocado se lee como un hecho.
- **2026-08-23 — Umbral de título en 55, medido.** El match correcto pero mal
  nombrado puntuó 59 ("Geovita presentación" vs "Geovitas y Sebastián Suárez")
  y el mejor candidato equivocado, 38.
- **2026-08-23 — El histórico contaminado no se toca** (decisión de
  Sebastián). Solo cambia el pipeline nuevo. Quedan sin corregir las 81 notas
  cuyo "Kauel" no aparece en su propia transcripción y las 127 con el bug de
  sintaxis `projects: [[[`. Criterio si algún día se retoma: priorizar las
  posteriores a junio 2026.
- **2026-08-23 — Se reusa el cliente OAuth de DailyDigest**, con token propio
  y solo scope `calendar.readonly`. Evita trabajo en Google Console; el
  acoplamiento es que si ese cliente se mueve o rota, esto se cae.
- **Pendiente de Sebastián:** su ficha en `Personas/` dice empresa "Kauel",
  anterior a su salida de mayo, y por eso aparece así en los rosters. Se
  arregla en la fuente con `personas-vault` (Fase 5), no parchando acá.
- **Sin bloqueos externos.** Todo lo que falta depende de este proyecto.

---

## Docs relacionados

- `PLAN-mejoras-ronda2.md` — backlog técnico de julio, sin ejecutar
- `README.md` — formato de salida, cascada de asistentes, atribución de hablantes
- `docs/tutorial.html` — tutorial v1.0 del exportador GUI
- Vault: `Planes/Plan-Segundo-Cerebro-IA-Agosto-2026.md` (la Fase 1 de ese plan
  es la que este proyecto absorbió) y `Recursos/segundo-cerebro/README.md`
