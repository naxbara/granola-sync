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
from pathlib import Path
from tkinter import filedialog, ttk

from .. import __version__
from ..auth.credentials import load_credentials
from ..exporter.runner import ExportProgress, ExportResult, export_documents
from ..logging_config import setup_logging
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

    def start_export(self, output_dir: Path, days_back: int | None, include_transcripts: bool) -> None:
        self._cancel_flag.clear()
        self._show_progress_frame()
        self._worker = threading.Thread(
            target=self._run_export,
            args=(output_dir, days_back, include_transcripts),
            daemon=True,
        )
        self._worker.start()

    def cancel_export(self) -> None:
        self._cancel_flag.set()

    def _run_export(self, output_dir: Path, days_back: int | None, include_transcripts: bool) -> None:
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
        ):
            ttk.Radiobutton(self, text=label, value=value, variable=self.range_var).pack(anchor="w")

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

    def _on_export(self) -> None:
        output_dir = Path(self.output_var.get()).expanduser()
        days = {"day": 1, "week": 7, "month": 30, "all": None}[self.range_var.get()]
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
    # Log to a file in a user-writable location so scheduled/packaged runs leave
    # a trail (basicConfig was console-only and lost when the window closed).
    log_dir = Path.home() / ".granola_notes" / "logs"
    try:
        setup_logging(log_dir=str(log_dir), verbose=False)
    except OSError:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    app = App()
    app.run()


if __name__ == "__main__":
    main()
