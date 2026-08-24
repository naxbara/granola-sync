# Avance — Granolaupdater

> Última actualización: 2026-08-23

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
- [ ] **Fase 6 — Higiene del repo.** Bug 1a del PLAN ronda 2 (modelo
      descontinuado como fallback), limpiar los `*.bak-migracion`

### Ronda 2 — pendiente desde 2026-07-05

`PLAN-mejoras-ronda2.md` (untracked, aprobado en alcance, **sin ejecutar**):
bugs de corrección, lógica de contenido triplicada entre `engine.py`,
`txt_formatter.py` y `md_formatter.py`, flag `--window`, backfill de tests.
Sigue vigente; la Fase 6 de arriba se come solo una parte.

---

## Ejecutado

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

1. **Fase 4 — empresas sin asumir.** Es lo que originalmente pidió Sebastián y
   ahora tiene los insumos que le faltaban: dominios de correo reales y fichas
   de `Personas/` cruzadas. Detectar y marcar (`orgs_sin_respaldo`), nunca
   reescribir el cuerpo — **hay reuniones que sí son de Kauel**.
2. **Resolver las sugerencias pendientes** con `--mode=speakers` sobre las
   transcripciones nuevas que deje el sync nocturno.
3. Fase 5 (skills) y Fase 6 (higiene del repo).

---

## Decisiones y bloqueos

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
