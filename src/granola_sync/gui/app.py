"""Tkinter GUI for the Granola Notes exporter.

Three swappable frames inside a single root window:
  - ConfigFrame: pick output folder, date range, transcript toggle
  - ProgressFrame: progress bar + cancel
  - ResultFrame: success summary with "Open folder" button (the post-sync tutorial)
  - ErrorFrame: shown when Granola creds can't be found / decrypted

Export runs on a background thread; UI updates marshalled via `root.after`.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import __version__
from ..auth.credentials import load_credentials
from ..exporter.runner import ExportProgress, ExportResult, export_documents
from ..utils import default_credentials_path

logger = logging.getLogger(__name__)

APP_TITLE = "Granola → Carpeta de Notas"
APP_VERSION = __version__
DEFAULT_OUTPUT_NAME = "Granola Notes"

_FONT_UI = "SF Pro Display" if sys.platform == "darwin" else "Segoe UI"
_FONT_MONO = "Menlo" if sys.platform == "darwin" else "Consolas"


def _default_output_dir() -> Path:
    """`~/Documents/Granola Notes` — falls back to home if Documents is missing."""
    home = Path.home()
    docs = home / "Documents"
    base = docs if docs.exists() else home
    return base / DEFAULT_OUTPUT_NAME


def _open_folder(path: Path) -> None:
    """Open a folder in the system file explorer (no shell — path is a list arg)."""
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("560x460")
        self.root.minsize(520, 440)

        self._cancel_flag = threading.Event()
        self._event_queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._result: ExportResult | None = None
        self._creds_path = default_credentials_path()

        self.container = ttk.Frame(self.root, padding=20)
        self.container.pack(fill="both", expand=True)

        self._show_initial_frame()
        self.root.after(80, self._drain_events)

    def run(self) -> None:
        self.root.mainloop()

    # ----- frame management -----

    def _clear(self) -> None:
        for w in self.container.winfo_children():
            w.destroy()

    def _show_initial_frame(self) -> None:
        try:
            load_credentials(self._creds_path)
        except Exception as e:
            logger.warning("Credentials check failed: %s", e)
            self._show_error_frame(str(e))
            return
        self._show_config_frame()

    def _show_config_frame(self) -> None:
        self._clear()
        ConfigFrame(self.container, self).pack(fill="both", expand=True)

    def _show_progress_frame(self) -> None:
        self._clear()
        self.progress_frame = ProgressFrame(self.container, self)
        self.progress_frame.pack(fill="both", expand=True)

    def _show_result_frame(self, result: ExportResult) -> None:
        self._clear()
        ResultFrame(self.container, self, result).pack(fill="both", expand=True)

    def _show_error_frame(self, detail: str) -> None:
        self._clear()
        ErrorFrame(self.container, self, detail).pack(fill="both", expand=True)

    # ----- export lifecycle -----

    def start_export(
        self,
        output_dir: Path,
        days_back: int | None,
        include_transcripts: bool,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> None:
        self._cancel_flag.clear()
        self._show_progress_frame()
        self._worker = threading.Thread(
            target=self._run_export,
            args=(output_dir, days_back, include_transcripts, date_from, date_to),
            daemon=True,
        )
        self._worker.start()

    def cancel_export(self) -> None:
        self._cancel_flag.set()

    def _run_export(
        self,
        output_dir: Path,
        days_back: int | None,
        include_transcripts: bool,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> None:
        def on_progress(p: ExportProgress) -> None:
            self._event_queue.put(("progress", p))

        try:
            result = export_documents(
                output_dir=output_dir,
                credentials_path=self._creds_path,
                days_back=days_back,
                include_transcripts=include_transcripts,
                on_progress=on_progress,
                should_cancel=self._cancel_flag.is_set,
                date_from=date_from,
                date_to=date_to,
            )
            self._event_queue.put(("done", result))
        except Exception as e:
            logger.exception("Export failed")
            self._event_queue.put(("error", str(e)))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self._event_queue.get_nowait()
                if kind == "progress" and hasattr(self, "progress_frame"):
                    self.progress_frame.update_progress(payload)
                elif kind == "done":
                    self._show_result_frame(payload)
                elif kind == "error":
                    self._show_error_frame(payload)
        except queue.Empty:
            pass
        self.root.after(80, self._drain_events)


class ConfigFrame(ttk.Frame):
    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app
        self.output_var = tk.StringVar(value=str(_default_output_dir()))
        self.range_var = tk.StringVar(value="day")
        self.from_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.transcripts_var = tk.BooleanVar(value=True)
        self._build()

    def _build(self) -> None:
        ttk.Label(
            self, text="Exportar reuniones de Granola", font=(_FONT_UI, 14, "bold")
        ).pack(anchor="w")
        ttk.Label(
            self,
            text="Genera un archivo .txt por reunión con resumen y transcripción.",
            foreground="#555",
            wraplength=500,
        ).pack(anchor="w", pady=(4, 16))

        # Output folder
        ttk.Label(self, text="Carpeta de salida:").pack(anchor="w")
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(4, 14))
        entry = ttk.Entry(row, textvariable=self.output_var)
        entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Cambiar…", command=self._pick_folder).pack(side="left", padx=(6, 0))

        # Date range
        ttk.Label(self, text="Descargar reuniones de:").pack(anchor="w")
        for value, label in (
            ("day", "Últimas 24 horas"),
            ("week", "Últimos 7 días"),
            ("month", "Último mes"),
            ("all", "Todo el historial"),
            ("custom", "Rango de fechas…"),
        ):
            ttk.Radiobutton(
                self, text=label, value=value, variable=self.range_var,
                command=self._on_range_change,
            ).pack(anchor="w")

        # Custom date-range inputs — enabled only when "Rango de fechas…" is picked.
        self.date_row = ttk.Frame(self)
        self.date_row.pack(fill="x", pady=(6, 0), padx=(22, 0))
        ttk.Label(self.date_row, text="Desde").grid(row=0, column=0, sticky="w")
        self.from_entry = ttk.Entry(self.date_row, textvariable=self.from_var, width=13)
        self.from_entry.grid(row=0, column=1, padx=(6, 14))
        ttk.Label(self.date_row, text="Hasta").grid(row=0, column=2, sticky="w")
        self.to_entry = ttk.Entry(self.date_row, textvariable=self.to_var, width=13)
        self.to_entry.grid(row=0, column=3, padx=(6, 0))
        ttk.Label(
            self,
            text="Formato AAAA-MM-DD. Deja «Hasta» vacío para llegar hasta hoy; "
                 "usa la misma fecha en ambos campos para un solo día.",
            foreground="#777", font=(_FONT_UI, 8), wraplength=480,
        ).pack(anchor="w", padx=(22, 0), pady=(3, 0))
        self._on_range_change()

        ttk.Checkbutton(
            self, text="Incluir transcripción completa", variable=self.transcripts_var
        ).pack(anchor="w", pady=(14, 0))

        ttk.Button(
            self, text="Exportar", command=self._on_export, style="Accent.TButton"
        ).pack(pady=(20, 0), ipadx=20, ipady=4)

        ttk.Label(
            self,
            text=f"Granola Notes v{APP_VERSION}",
            foreground="#999",
            font=(_FONT_UI, 8),
        ).pack(side="bottom", anchor="e", pady=(20, 0))

    def _pick_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.output_var.get(), mustexist=False)
        if chosen:
            self.output_var.set(chosen)

    def _on_range_change(self) -> None:
        state = "normal" if self.range_var.get() == "custom" else "disabled"
        self.from_entry.configure(state=state)
        self.to_entry.configure(state=state)

    @staticmethod
    def _parse_date(text: str, label: str, required: bool):
        """Parse an AAAA-MM-DD field.

        Returns a date, or None when empty and optional. Shows an error dialog
        and returns False on an invalid value or a missing required one.
        """
        text = text.strip()
        if not text:
            if required:
                messagebox.showerror("Falta una fecha", f"Ingresa la fecha «{label}» (AAAA-MM-DD).")
                return False
            return None
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror(
                "Fecha inválida",
                f"«{label}» debe tener el formato AAAA-MM-DD (ej. 2026-07-01).",
            )
            return False

    def _on_export(self) -> None:
        output_dir = Path(self.output_var.get()).expanduser()
        choice = self.range_var.get()

        if choice == "custom":
            date_from = self._parse_date(self.from_var.get(), "Desde", required=True)
            if date_from is False:
                return
            date_to = self._parse_date(self.to_var.get(), "Hasta", required=False)
            if date_to is False:
                return
            if date_to is not None and date_to < date_from:
                messagebox.showerror("Rango inválido", "«Hasta» no puede ser anterior a «Desde».")
                return
            self.app.start_export(
                output_dir, None, self.transcripts_var.get(),
                date_from=date_from, date_to=date_to,
            )
            return

        days = {"day": 1, "week": 7, "month": 30, "all": None}[choice]
        self.app.start_export(output_dir, days, self.transcripts_var.get())


class ProgressFrame(ttk.Frame):
    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text="Exportando reuniones…", font=(_FONT_UI, 14, "bold")).pack(
            anchor="w", pady=(0, 12)
        )
        self.progress = ttk.Progressbar(self, mode="determinate", length=480)
        self.progress.pack(fill="x", pady=(0, 8))
        self.status_var = tk.StringVar(value="Conectando con Granola…")
        ttk.Label(self, textvariable=self.status_var, foreground="#555", wraplength=480).pack(
            anchor="w"
        )
        ttk.Button(self, text="Cancelar", command=self.app.cancel_export).pack(pady=(20, 0))

    def update_progress(self, p: ExportProgress) -> None:
        if p.total > 0:
            self.progress["maximum"] = p.total
            self.progress["value"] = p.current
        self.status_var.set(f"Procesando {p.current} de {p.total}: {p.title or 'sin título'}")


class ResultFrame(ttk.Frame):
    def __init__(self, master: tk.Misc, app: App, result: ExportResult) -> None:
        super().__init__(master)
        self.app = app
        self.result = result
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text="✔ Listo", font=(_FONT_UI, 16, "bold"), foreground="#2a7a2a").pack(
            anchor="w", pady=(0, 8)
        )

        msg = f"Se exportaron {self.result.written} reuniones."
        if self.result.errors:
            msg += f"  ({self.result.errors} con errores)"
        ttk.Label(self, text=msg, font=(_FONT_UI, 11)).pack(anchor="w", pady=(0, 16))

        ttk.Label(self, text="📁 Tus archivos están en:", foreground="#555").pack(anchor="w")
        path_frame = ttk.Frame(self, padding=(8, 6), relief="solid", borderwidth=1)
        path_frame.pack(fill="x", pady=(2, 14))
        ttk.Label(path_frame, text=str(self.result.output_dir), font=(_FONT_MONO, 10)).pack(
            anchor="w"
        )

        btns = ttk.Frame(self)
        btns.pack(pady=(4, 0))
        ttk.Button(
            btns, text="Abrir carpeta", command=self._open, style="Accent.TButton"
        ).pack(side="left", padx=(0, 8), ipadx=14, ipady=4)
        ttk.Button(btns, text="Cerrar", command=self.app.root.destroy).pack(
            side="left", ipadx=10, ipady=4
        )

        _editor_tip = (
            "Tip: cada archivo .txt se abre con TextEdit o cualquier editor de texto."
            if sys.platform == "darwin" else
            "Tip: cada archivo .txt se abre con el Bloc de notas o Word. "
            "Si no ves los acentos correctamente, abre con Word o Bloc de notas (UTF-8)."
        )
        ttk.Label(
            self,
            text=_editor_tip,
            foreground="#777",
            font=(_FONT_UI, 9),
            wraplength=500,
        ).pack(anchor="w", pady=(20, 0))

    def _open(self) -> None:
        try:
            _open_folder(self.result.output_dir)
        except Exception as e:
            logger.warning("Failed to open folder: %s", e)


class ErrorFrame(ttk.Frame):
    def __init__(self, master: tk.Misc, app: App, detail: str) -> None:
        super().__init__(master)
        self.app = app
        self.detail = detail
        self._build()

    def _build(self) -> None:
        ttk.Label(
            self, text="⚠ No pude conectarme a Granola", font=(_FONT_UI, 14, "bold")
        ).pack(anchor="w", pady=(0, 12))
        ttk.Label(
            self,
            text="Para usar esta aplicación necesitas:",
            wraplength=500,
        ).pack(anchor="w")
        ttk.Label(
            self,
            text="  1. Tener la app de escritorio de Granola instalada (granola.ai).",
            wraplength=500,
        ).pack(anchor="w", pady=(2, 0))
        ttk.Label(
            self,
            text="  2. Haber iniciado sesión en la app al menos una vez.",
            wraplength=500,
        ).pack(anchor="w", pady=(2, 12))

        ttk.Label(self, text="Detalle técnico:", foreground="#555").pack(anchor="w")
        detail_box = tk.Text(self, height=4, wrap="word", background="#f4f4f4")
        detail_box.insert("1.0", self.detail)
        detail_box.configure(state="disabled")
        detail_box.pack(fill="x", pady=(4, 16))

        btns = ttk.Frame(self)
        btns.pack()
        ttk.Button(btns, text="Reintentar", command=self.app._show_initial_frame).pack(
            side="left", padx=(0, 8), ipadx=14, ipady=4
        )
        ttk.Button(btns, text="Cerrar", command=self.app.root.destroy).pack(
            side="left", ipadx=10, ipady=4
        )


def main() -> None:
    # Log to a file in a user-writable location so the packaged (windowed) app
    # leaves a trail — a windowed .exe has no console, so a plain FileHandler is
    # used directly instead of the CLI's Rich console logging.
    log_dir = Path.home() / ".granola_notes" / "logs"
    handlers: list[logging.Handler] = []
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_dir / "granola-notes.log", encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
        handlers=handlers or None,
    )
    app = App()
    app.run()


if __name__ == "__main__":
    main()
