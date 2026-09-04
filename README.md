# Granola-to-Obsidian Sync

Sincroniza automáticamente tus notas de reuniones de [Granola](https://granola.ai) hacia tu vault de [Obsidian](https://obsidian.md).

> 📖 **Tutorial completo** (novedades de la 1.0, instalación, modos, programación y enrichment): abre [`docs/tutorial.html`](docs/tutorial.html) en tu navegador.

## Requisitos

- Python 3.11+
- Granola desktop app instalado y con sesión iniciada
- Un vault de Obsidian

## Instalación

```bash
git clone https://github.com/tu-usuario/Granolaupdater.git
cd Granolaupdater
pip install -e ".[dev]"
```

## Configuración

Copia el archivo de ejemplo y edítalo con tu ruta de vault:

```bash
cp config.example.yaml config.yaml
```

```yaml
vault_path: "C:\\Users\\TuNombre\\Obsidian\\TuVault"

sync:
  include_transcripts: true
  fuzzy_threshold: 85
  transcripts_folder: "Transcripciones"
  transcript_mode: separate   # separate | inline | none

enrichment:
  enabled: false

logging:
  dir: "logs"
  verbose: false
```

Las credenciales de Granola se detectan automáticamente desde `supabase.json`:
- **Windows**: `%APPDATA%\Granola\supabase.json`
- **macOS**: `~/Library/Application Support/Granola/supabase.json`

Granola 2.x guarda las credenciales cifradas en `supabase.json.enc` y puede no
dejar ningún `supabase.json` en texto plano. Basta con que exista cualquiera de
los dos: el `.enc` se desencripta con la clave del sistema (DPAPI en Windows,
Llavero en macOS).

## Uso

```bash
# Sync de las últimas 24 horas (modo por defecto)
granola-sync

# O con python directamente
python -m granola_sync
```

### Modos de operación

```bash
# Daily: sync últimas 24h (default)
granola-sync --mode=daily

# Historical: importar todo desde una fecha
granola-sync --mode=historical --from=2024-01-01

# Historical: un rango cerrado de fechas (--to es inclusive)
granola-sync --mode=historical --from=2026-06-01 --to=2026-06-30

# Verify: verificar integridad de notas existentes
granola-sync --mode=verify

# Dry-run: ver qué haría sin escribir archivos
granola-sync --mode=dry-run
```

### Opciones adicionales

```bash
# Usar un archivo de config diferente
granola-sync --config=otro-config.yaml

# Override del vault path
granola-sync --vault="C:\otro\vault"

# Desactivar enrichment de Claude AI
granola-sync --no-enrich

# Logging verbose
granola-sync --verbose
```

## Asistentes: de dónde salen los nombres

Granola solo mira los calendarios de la cuenta con la que se registró, y no
acepta cuentas personales en el plan gratuito. El resultado es que casi ninguna
reunión llega con asistentes. Por eso los participantes se arman en cascada,
del dato más duro al más blando:

1. `people.attendees` de Granola — trae correo y, cuando existe, **nombre,
   empresa y cargo** (`details.person.employment`)
2. `people.creator` — el organizador, presente en todos los documentos
3. `google_calendar_event.attendees` de Granola
4. **Google Calendar directo** (opcional, ver abajo)
5. `Personas/` del vault — completa nombre, empresa y rol por correo, sin red

`participants:` en el frontmatter sigue siendo una lista de correos: es la
llave con que se cruzan las fichas de `Personas/`. Los nombres van al cuerpo,
en la línea `Asistentes:` del callout, y solo aparecen los que sí se pudieron
identificar.

### Activar Google Calendar (opcional)

```bash
pip install -e ".[calendar]"
granola-sync --mode=auth-calendar   # una sola vez, abre el navegador
```

Pide **solo** el permiso `calendar.readonly` y guarda su token en
`secrets/google_token.json`. Configúralo con el bloque `calendar:` del
`config.example.yaml`.

El cruce entre la reunión de Granola y el evento del calendario se hace por
hora de inicio (±30 min) y parecido del título. **Si el match no es claro no se
escribe nada**: dos eventos parecidos a la misma hora, o un evento sin
invitados, dejan la reunión sin asistentes antes que inventarlos.

## Formato de salida

Las notas se guardan en `{vault}/Reuniones/` con el formato `YYYY-MM-DD-titulo-slugificado.md`
(la subcarpeta es configurable con `sync.notes_folder`).

Cada archivo contiene:

```markdown
---
type: meeting
date: 2026-02-06
time: 14:30
source: granola
granola_id: abc123
granola_updated: 2026-02-06T15:20:00+00:00
duration: 45min
participants: [user@email.com]
status: processed
---

### Tema 1
- Punto importante
- Otro punto

### Tema 2
- Detalle relevante

> [!quote]- Transcripcion completa
> La transcripcion literal de esta reunion vive fuera del camino de lectura
> por defecto para no pesar en las consultas al vault.
> Ver: [[2026-02-06-reunion-con-cliente-transcript]]
> Granola: https://notes.granola.ai/t/abc123
> Meeting participants: user@email.com, otro@email.com
```

### La transcripción va aparte

Con `transcript_mode: separate` (el default) la transcripción literal **no** se
pega en la nota: va a `{vault}/Transcripciones/<nombre>-transcript.md` y la nota
queda con el callout plegado de arriba. El motivo es de peso: la transcripción
era el 80% del vault y arruinaba cualquier consulta con IA.

El archivo de transcripción se ve así:

```markdown
---
type: transcripcion
date: '2026-02-06'
source: granola
granola_id: abc123
reunion: "[[2026-02-06-reunion-con-cliente]]"
---

> Transcripcion literal de [[2026-02-06-reunion-con-cliente]]. Fuera del camino de lectura por defecto.

Chat with meeting transcript: [link](https://notes.granola.ai/t/abc123)

Meeting Title: Reunión con cliente
Date: 2026-02-06
Meeting participants: user@email.com, otro@email.com

Transcript:

**[14:30:00]** _Speaker_: Texto del participante...

**[14:30:15]** _You_: Tu respuesta...
```

### Quién habló

Granola no entrega diarización: sin plan pago, todos los interlocutores remotos
llegan con la misma etiqueta. `source: microphone` es el dueño del micrófono y
siempre se escribe `_You_`; el resto colapsa en `_Speaker_`.

Hay un solo caso que se puede resolver sin adivinar: **una reunión con un único
otro asistente al que podemos nombrar**. Ahí `_Speaker_` pasa a ser su nombre y
la transcripción lo declara en su frontmatter:

```yaml
speaker_attribution: 1a1     # 1a1 | granola  (ausente = etiqueta genérica)
```

Requiere `owner_emails` en la config para distinguir tus direcciones de las
ajenas. Si algún día Granola empieza a mandar `detected_speaker_name`, esa
etiqueta gana y el modo pasa a `granola` automáticamente.

En un grupo de cinco los turnos son genuinamente indistinguibles, así que se
mantiene `_Speaker_`.

### Sugerencias que tú confirmas

Cuando nadie figura en la invitación pero un nombre de `Personas/` aparece **a
la vez en el título y en lo que se habla**, el sync lo anota como sugerencia —
sin tocar la etiqueta del cuerpo:

```yaml
speaker_attribution: sugerido
speaker_candidates: ["Juan Carlos Lanas", "Gustavo"]
speaker_evidence: "'lanas' en el título y 18× en la transcripción"
```

Se resuelve de dos formas, indistintamente:

```bash
granola-sync --mode=speakers   # muestra evidencia y ejemplos, y aplica lo que elijas
```

o escribiendo `speaker_confirmed: Juan Carlos Lanas` a mano en Obsidian; el
mismo comando lo aplica después. Al confirmar, las etiquetas genéricas del
cuerpo pasan al nombre y el frontmatter queda en `confirmado` — que **sobrevive
a los resyncs**: la pregunta se responde una sola vez.

Exigir título **y** transcripción es lo que lo hace utilizable. Solo la
transcripción trae a quien fue *mencionado*, no a quien habla: tu propio nombre
aparece en todas. Se excluyen tus direcciones, las fichas de grupo, y si dos
personas comparten el token la sugerencia lo declara en vez de elegir.

Con `transcript_mode: inline` se conserva el comportamiento antiguo (todo en un
archivo), que es el que usa el exportador de la GUI. Con `none` no se escribe
transcripción.

## Detección de duplicados

El sync detecta duplicados de dos formas:

1. **Por `granola_id`** en el frontmatter YAML (match exacto). Es la vía
   principal: cubre todo lo que escribió este sync, aunque hayas movido la nota
   a otra carpeta del vault. Las notas de `Transcripciones/` quedan fuera del
   mapa aunque repitan el `granola_id` de su reunión — la que interesa es la
   nota de reunión, que es la que lleva `granola_updated` y la que se regenera.
2. **Por título fuzzy** con la misma fecha (`fuzzy_threshold`, default 85), y
   **solo contra notas sin `granola_id`**: las escritas a mano o anteriores al
   id. Una nota que ya tiene el id de *otra* reunión no puede ser un duplicado,
   así que no entra a la comparación — si no, dos reuniones del mismo día con
   títulos parecidos ("… v2") se leen como una sola. Con `fuzzy_threshold: 0`
   el fallback se apaga y solo queda el match por id.

## Enrichment con Claude AI (opcional)

Si activas el enrichment en `config.yaml`, Claude analiza cada nota y agrega al frontmatter:
- Proyectos detectados
- Tags relevantes
- Tipo de reunión

```yaml
enrichment:
  enabled: true
  api_key: "sk-ant-tu-api-key"
  model: "claude-opus-4-8"   # para alto volumen y menor costo: "claude-haiku-4-5"
```

## Programación automática

### Windows (Task Scheduler)

Registra una tarea diaria no interactiva (sin `pause`, con logging a archivo).
Usa una **ventana móvil** (por defecto 3 días) para que un día saltado se recupere
en la siguiente corrida — gratis gracias al dedup + la actualización de notas:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_scheduled_task.ps1 -Time 09:00
# Ventana más ancha (ej. 7 días) como red de seguridad extra:
powershell -ExecutionPolicy Bypass -File scripts\install_scheduled_task.ps1 -Time 09:00 -Window 7
```

- Verificar: `schtasks /query /tn GranolaSyncDaily`
- Ejecutar ahora: `schtasks /run /tn GranolaSyncDaily`
- Quitar: `powershell -ExecutionPolicy Bypass -File scripts\install_scheduled_task.ps1 -Uninstall`

### macOS / Linux (cron o launchd)

Los scripts `Granola Sync Diario.sh` / `Semanal.sh` sirven para correr manualmente.
Para automatizar, una entrada de cron diaria a las 9:00:

```cron
0 9 * * *  cd /ruta/a/Granolaupdater && /usr/bin/python3 -m granola_sync --mode=daily --config config.yaml
```

En macOS también puedes usar un `launchd` plist en `~/Library/LaunchAgents/` con
`StartCalendarInterval` apuntando al mismo comando.

## Tests

```bash
pytest
```

## Estructura del proyecto

```
src/granola_sync/
├── cli.py                  # CLI con argparse
├── config.py               # Configuración YAML
├── logging_config.py       # Setup de logging (Rich + archivo)
├── utils.py                # Slugify, rutas por plataforma
├── auth/
│   ├── credentials.py      # Lee supabase.json (+ .enc de Granola 2.x)
│   ├── token_manager.py    # Refresh de tokens WorkOS
│   └── encrypted_storage.py# Descifra storage de Granola 2.x (DPAPI/Keychain)
├── api/
│   ├── client.py           # Cliente API de Granola
│   └── models.py           # Modelos Pydantic
├── converters/
│   ├── prosemirror.py      # ProseMirror JSON → Markdown / texto plano
│   ├── html.py             # HTML de paneles legacy → Markdown / texto
│   └── template.py         # Template de nota Obsidian
├── enrichment/
│   └── claude_enricher.py  # Enrichment con Claude API
├── sync/                   # Pipeline CLI → Obsidian (.md con frontmatter)
│   ├── engine.py            # Orquestación principal
│   ├── dedup.py             # Detección de duplicados
│   └── vault.py             # Escritura atómica al vault
├── exporter/               # Pipeline GUI → .txt (sin dedup ni Obsidian)
│   ├── runner.py            # Orquestación del export
│   └── txt_formatter.py     # Render a texto plano
└── gui/
    └── app.py               # GUI Tkinter para usuarios no técnicos
```
