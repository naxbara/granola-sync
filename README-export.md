# Granola Notes — Exportador a TXT

Exporta tus reuniones de Granola a archivos `.txt` (resumen + transcripción).
Ideal para guardarlas, archivarlas o compartirlas sin depender de Granola.

## Requisitos

1. **Tener la app de escritorio de Granola instalada** y haber iniciado sesión al menos una vez.
   👉 https://granola.ai
2. Windows 10 u 11.

No necesitas instalar Python ni nada extra.

## Cómo usar

1. Descarga `Granola Notes.exe` (un solo archivo, ~13 MB).
2. Doble click para abrirlo.
3. Si Windows Defender muestra una advertencia ("SmartScreen impidió el inicio…"):
   - Click en **Más información**.
   - Click en **Ejecutar de todas formas**.
   - Esto pasa porque el archivo no está firmado digitalmente; es seguro si lo descargaste del enlace original.
4. Elige una carpeta de salida (por defecto `Documentos\Granola Notes`).
5. Selecciona el rango (últimas 24 horas / 7 días / último mes / todo el historial).
6. Click en **Exportar**.
7. Cuando termine, click en **Abrir carpeta** para ver tus archivos.

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

Puedes abrirlos con Bloc de notas, Word o cualquier editor de texto.

## Problemas comunes

**"No pude conectarme a Granola"**
Asegúrate de:
1. Tener la app de Granola abierta (o haberla abierto al menos una vez recientemente).
2. Haber iniciado sesión.

Si la app de Granola se actualizó y la herramienta dejó de funcionar, abre Granola, cierra sesión y vuelve a iniciar sesión. Si persiste, contáctanos.

**Los acentos se ven mal en Bloc de notas**
Abre el archivo con Word, o abre Bloc de notas → Archivo → Abrir → seleccionar el archivo → en "Codificación" elegir **UTF-8**.

## Privacidad

Esta app:
- Lee tus tokens **localmente** desde donde Granola los guarda en tu PC.
- Habla solo con los servidores de Granola (los mismos que usa la app oficial).
- **No envía tus datos a ningún tercero.**
- No requiere ninguna cuenta adicional.

## Para desarrolladores

Código fuente en `src/granola_sync/gui/` y `src/granola_sync/exporter/`.
Build local:

```bash
pip install -e ".[gui]"
pyinstaller granola-notes.spec
```

El `.exe` resultante queda en `dist/Granola Notes.exe`.
