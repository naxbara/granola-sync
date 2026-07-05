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
vault_path: "C:\\Users\\TuNombre\\iCloudDrive\\iCloud~md~obsidian\\TuVault"

sync:
  include_transcripts: true
  fuzzy_threshold: 85

enrichment:
  enabled: false

logging:
  dir: "logs"
  verbose: false
```

Las credenciales de Granola se detectan automáticamente desde `supabase.json`:
- **Windows**: `%APPDATA%\Granola\supabase.json`
- **macOS**: `~/Library/Application Support/Granola/supabase.json`

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

---

Chat with meeting transcript: [link](https://notes.granola.ai/t/abc123)

Meeting Title: Reunión con cliente
Date: 2026-02-06
Meeting participants: user@email.com, otro@email.com

Transcript:

**[14:30:00]** _Speaker_: Texto del participante...

**[14:30:15]** _You_: Tu respuesta...
```

## Detección de duplicados

El sync detecta duplicados de dos formas:
1. **Por `granola_id`** en el frontmatter YAML (match exacto)
2. **Por título fuzzy** con la misma fecha (threshold configurable, default 85%)

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

Registra una tarea diaria no interactiva (sin `pause`, con logging a archivo):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_scheduled_task.ps1 -Time 09:00
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
