# Granola Notes — Exportador a TXT

Exporta tus reuniones de Granola a archivos `.txt` (resumen + transcripción).
Ideal para guardarlas, archivarlas o compartirlas sin depender de Granola.

## Requisitos

1. **Tener la app de escritorio de Granola instalada** y haber iniciado sesión al menos una vez.
   👉 https://granola.ai
2. Windows 10/11 **o** macOS 12 (Monterey) o superior.

No necesitas instalar Python ni nada extra.

## Cómo usar en Windows

1. Descarga `Granola Notes.exe` (un solo archivo, ~13 MB).
2. Doble click para abrirlo.
3. Si Windows Defender muestra una advertencia ("SmartScreen impidió el inicio…"):
   - Click en **Más información**.
   - Click en **Ejecutar de todas formas**.
   - Esto pasa porque el archivo no está firmado digitalmente; es seguro si lo descargaste del enlace original.
4. Elige una carpeta de salida (por defecto `Documentos/Granola Notes`).
5. Selecciona el rango (últimas 24 horas / 7 días / último mes / todo el historial).
6. Click en **Exportar**.
7. Cuando termine, click en **Abrir carpeta** para ver tus archivos.

## Cómo usar en macOS

1. Descarga `Granola Notes.app` y muévela a tu carpeta de Aplicaciones (opcional).
2. Doble click para abrirla.
3. Si macOS muestra "no se puede abrir porque es de un desarrollador no identificado":
   - Mantén presionado **Control** y haz click en la app.
   - Selecciona **Abrir** en el menú contextual.
   - Click en **Abrir** en el diálogo de confirmación.
   - Solo necesitas hacer esto la primera vez.
4. Elige una carpeta de salida (por defecto `Documentos/Granola Notes`).
5. Selecciona el rango (últimas 24 horas / 7 días / último mes / todo el historial).
6. Click en **Exportar**.
7. Cuando termine, click en **Abrir carpeta** para ver tus archivos en Finder.

## Qué obtienes

Un archivo `.txt` por reunión, con este formato:

```
================================================================================
Título de la reunión
================================================================================

Fecha: 8 de mayo de 2026, 14:30
Duración: 45 minutos
Participantes: Juan Pérez, María González

--------------------------------------------------------------------------------
RESUMEN
--------------------------------------------------------------------------------

(El resumen generado por Granola)

--------------------------------------------------------------------------------
TRANSCRIPCIÓN
--------------------------------------------------------------------------------

[00:00:00] Tú: Hola, gracias por venir.
[00:00:12] Otro: Encantada de estar aquí.
```

Los archivos se nombran como `2026-05-08 - titulo-de-la-reunion.txt` y se guardan en la carpeta que elegiste.

Puedes abrirlos con Bloc de notas, TextEdit, Word o cualquier editor de texto.

## Problemas comunes

**"No pude conectarme a Granola"**
Asegúrate de:
1. Tener la app de Granola abierta (o haberla abierto al menos una vez recientemente).
2. Haber iniciado sesión.

Si la app de Granola se actualizó y la herramienta dejó de funcionar, abre Granola, cierra sesión y vuelve a iniciar sesión. Si persiste, contáctanos.

**Los acentos se ven mal en Bloc de notas (Windows)**
Abre el archivo con Word, o abre Bloc de notas → Archivo → Abrir → seleccionar el archivo → en "Codificación" elegir **UTF-8**.

**macOS pide permiso para acceder al llavero (Keychain)**
La app necesita leer las credenciales de Granola desde el llavero del sistema. Esto es seguro — solo accede a la entrada de Granola. Si aparece un diálogo de permiso, haz click en **Permitir**.

## Privacidad

Esta app:
- Lee tus tokens **localmente** desde donde Granola los guarda (Windows: `%APPDATA%\Granola\`; macOS: `~/Library/Application Support/Granola/`).
- Habla solo con los servidores de Granola (los mismos que usa la app oficial).
- **No envía tus datos a ningún tercero.**
- No requiere ninguna cuenta adicional.

## Para desarrolladores

Código fuente en `src/granola_sync/gui/` y `src/granola_sync/exporter/`.
Build local:

```bash
pip install -e ".[gui]"

# Windows
pyinstaller granola-notes.spec
# → dist/Granola Notes.exe

# macOS
pyinstaller granola-notes-macos.spec
# → dist/Granola Notes.app
```
