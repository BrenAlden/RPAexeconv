from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_LAUNCHER_TEMPLATE = r'''"""Launcher GUI untuk proyek RPA "__RPA_PROJECT_LABEL__".

Auto-generated oleh RPA EXE Converter. Jangan edit manual.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox, ttk
except BaseException as exc:
    # Mode --windowed tidak punya console. Persist error bootstrap agar crash
    # sebelum GUI dibuat tidak lagi silent.
    base = Path(sys.executable).resolve().parent
    try:
        (base / "launcher_error.log").write_text(
            "Gagal import tkinter:\n" + "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
    raise

ENTRY_MODULE = "__RPA_ENTRY_MODULE__"
PROJECT_LABEL = "__RPA_PROJECT_LABEL__"
CHILD_FLAG = "--run-rpa"

# ------------------------------------------------------------------ helpers ---


def exe_dir() -> Path:
    """Direktori tempat exe berada (bukan _MEIPASS)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def ensure_io_dirs() -> tuple[Path, Path]:
    """Bikin folder input/ dan output/ di sebelah exe."""
    base = exe_dir()
    inp = base / "input"
    out = base / "output"
    inp.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    return inp, out


def open_folder(path: Path) -> None:
    """Buka folder di Explorer (Windows) / fallback os.startfile."""
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        try:
            subprocess.Popen(["explorer", str(path)])
        except OSError:
            pass


# --------------------------------------------------------------- child mode ---


def run_as_child() -> int:
    """Mode anak: jalankan modul RPA lewat runpy.

    Env var yang di-set untuk kode RPA:
        RPA_INPUT_DIR   -> path absolut folder input
        RPA_OUTPUT_DIR  -> path absolut folder output
        RPA_EXE_DIR     -> path absolut folder exe

    CWD juga di-chdir ke folder exe agar path relatif di kode RPA konsisten.
    """
    import runpy

    inp, out = ensure_io_dirs()
    base = exe_dir()
    os.environ["RPA_INPUT_DIR"] = str(inp)
    os.environ["RPA_OUTPUT_DIR"] = str(out)
    os.environ["RPA_EXE_DIR"] = str(base)
    os.chdir(base)

    # Force unbuffered output supaya parent bisa membaca line-by-line
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
        sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

    print(f"[launcher] Menjalankan modul: {ENTRY_MODULE}", flush=True)
    print(f"[launcher] Input dir : {inp}", flush=True)
    print(f"[launcher] Output dir: {out}", flush=True)
    print("-" * 60, flush=True)

    try:
        runpy.run_module(ENTRY_MODULE, run_name="__main__", alter_sys=True)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 0
    except BaseException as exc:  # noqa: BLE001 - tangkap semua, tampilkan
        import traceback

        print("[launcher] ERROR:", exc, file=sys.stderr, flush=True)
        traceback.print_exc()
        return 1
    return 0


# --------------------------------------------------------------- parent GUI --


PALETTE = {
    "bg":        "#1e1e2e",
    "surface":   "#282a36",
    "surface2":  "#313244",
    "text":      "#cdd6f4",
    "text_dim":  "#a6adc8",
    "accent":    "#89b4fa",
    "accent_hi": "#b4befe",
    "success":   "#a6e3a1",
    "danger":    "#f38ba8",
    "warning":   "#f9e2af",
}


class LauncherApp:
    """GUI utama untuk mengontrol eksekusi RPA."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.process: subprocess.Popen | None = None
        self.log_queue: queue.Queue = queue.Queue()
        self.reader_threads: list[threading.Thread] = []

        self.input_dir, self.output_dir = ensure_io_dirs()

        self._build_ui()
        self._pump_log_queue()

    # ---------- UI construction ----------

    def _build_ui(self) -> None:
        self.root.title(f"RPA Launcher - {PROJECT_LABEL}")
        self.root.geometry("820x620")
        self.root.minsize(640, 500)
        self.root.configure(bg=PALETTE["bg"])

        try:
            self.root.tk.call("tk", "scaling", 1.2)
        except tk.TclError:
            pass

        base_font = tkfont.nametofont("TkDefaultFont")
        base_font.configure(family="Segoe UI", size=10)
        mono_font = tkfont.Font(family="Consolas", size=10)

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self._apply_style(style)

        # --- Header ---
        header = tk.Frame(self.root, bg=PALETTE["surface"], height=64)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        tk.Label(
            header,
            text=PROJECT_LABEL,
            fg=PALETTE["text"],
            bg=PALETTE["surface"],
            font=("Segoe UI Semibold", 14),
        ).pack(side="left", padx=20, pady=16)

        self.status_var = tk.StringVar(value="Ready")
        self.status_dot = tk.Canvas(
            header, width=12, height=12, bg=PALETTE["surface"],
            highlightthickness=0,
        )
        self._paint_dot(PALETTE["text_dim"])
        self.status_dot.pack(side="right", padx=(0, 12), pady=24)
        tk.Label(
            header, textvariable=self.status_var,
            fg=PALETTE["text_dim"], bg=PALETTE["surface"],
            font=("Segoe UI", 10),
        ).pack(side="right", pady=24)

        # --- Toolbar ---
        toolbar = tk.Frame(self.root, bg=PALETTE["bg"])
        toolbar.pack(fill="x", padx=16, pady=(12, 8))

        self.btn_start = ttk.Button(
            toolbar, text="\u25B6  Start", style="Accent.TButton",
            command=self.on_start,
        )
        self.btn_start.pack(side="left")

        self.btn_stop = ttk.Button(
            toolbar, text="\u25A0  Stop", style="Danger.TButton",
            command=self.on_stop, state="disabled",
        )
        self.btn_stop.pack(side="left", padx=(8, 0))

        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", fill="y", padx=12, pady=4,
        )

        ttk.Button(
            toolbar, text="Open Input",
            command=lambda: open_folder(self.input_dir),
        ).pack(side="left")
        ttk.Button(
            toolbar, text="Open Output",
            command=lambda: open_folder(self.output_dir),
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            toolbar, text="Clear Log", command=self.clear_log,
        ).pack(side="right")

        # --- Progress bar ---
        self.progress = ttk.Progressbar(
            self.root, mode="indeterminate",
            style="Accent.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x", padx=16, pady=(4, 8))

        # --- Log panel ---
        log_frame = tk.Frame(self.root, bg=PALETTE["surface"], bd=0)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self.log = tk.Text(
            log_frame, wrap="word", bd=0, padx=12, pady=8,
            bg=PALETTE["surface"], fg=PALETTE["text"],
            insertbackground=PALETTE["text"], font=mono_font,
            state="disabled",
        )
        self.log.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log.yview,
        )
        scrollbar.pack(side="right", fill="y")
        self.log["yscrollcommand"] = scrollbar.set

        self.log.tag_config("stdout", foreground=PALETTE["text"])
        self.log.tag_config("stderr", foreground=PALETTE["danger"])
        self.log.tag_config("info", foreground=PALETTE["accent"])
        self.log.tag_config("success", foreground=PALETTE["success"])
        self.log.tag_config("warning", foreground=PALETTE["warning"])
        self.log.tag_config("input", foreground=PALETTE["accent_hi"])

        # --- Command input (untuk RPA yang memakai built-in input()) ---
        command_frame = tk.Frame(self.root, bg=PALETTE["bg"])
        command_frame.pack(fill="x", padx=16, pady=(0, 8))

        tk.Label(
            command_frame,
            text="Command Input",
            fg=PALETTE["text_dim"],
            bg=PALETTE["bg"],
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(0, 8))

        self.command_var = tk.StringVar()
        self.command_entry = ttk.Entry(
            command_frame,
            textvariable=self.command_var,
            state="disabled",
        )
        self.command_entry.pack(side="left", fill="x", expand=True)
        self.command_entry.bind("<Return>", self.send_command)

        self.btn_send = ttk.Button(
            command_frame,
            text="Send",
            command=self.send_command,
            state="disabled",
        )
        self.btn_send.pack(side="left", padx=(8, 0))

        # --- Footer ---
        footer = tk.Frame(self.root, bg=PALETTE["bg"])
        footer.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(
            footer, text=f"Working dir: {exe_dir()}",
            fg=PALETTE["text_dim"], bg=PALETTE["bg"], font=("Segoe UI", 9),
        ).pack(side="left")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._log("info", f"Launcher siap. Modul entry: {ENTRY_MODULE}")
        self._log("info", f"Input dir : {self.input_dir}")
        self._log("info", f"Output dir: {self.output_dir}")

    def _apply_style(self, style: ttk.Style) -> None:
        style.configure(
            "TButton", background=PALETTE["surface2"], foreground=PALETTE["text"],
            borderwidth=0, focusthickness=0, padding=(14, 8), font=("Segoe UI", 10),
        )
        style.map(
            "TButton",
            background=[("active", PALETTE["accent"]), ("disabled", PALETTE["surface2"])],
            foreground=[("disabled", PALETTE["text_dim"])],
        )
        style.configure(
            "Accent.TButton", background=PALETTE["accent"], foreground="#11111b",
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", PALETTE["accent_hi"]), ("disabled", PALETTE["surface2"])],
            foreground=[("disabled", PALETTE["text_dim"])],
        )
        style.configure(
            "Danger.TButton", background=PALETTE["danger"], foreground="#11111b",
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#eb6f8b"), ("disabled", PALETTE["surface2"])],
            foreground=[("disabled", PALETTE["text_dim"])],
        )
        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor=PALETTE["surface"], background=PALETTE["accent"],
            bordercolor=PALETTE["surface"], lightcolor=PALETTE["accent"],
            darkcolor=PALETTE["accent"],
        )
        style.configure("TSeparator", background=PALETTE["surface2"])
        style.configure(
            "TEntry",
            fieldbackground=PALETTE["surface"],
            foreground=PALETTE["text"],
            insertcolor=PALETTE["text"],
            borderwidth=0,
            padding=8,
        )
        style.map(
            "TEntry",
            fieldbackground=[("disabled", PALETTE["surface2"])],
            foreground=[("disabled", PALETTE["text_dim"])],
        )

    def _paint_dot(self, color: str) -> None:
        self.status_dot.delete("all")
        self.status_dot.create_oval(1, 1, 11, 11, fill=color, outline=color)

    # ---------- log queue pump ----------

    def _pump_log_queue(self) -> None:
        try:
            while True:
                tag, line = self.log_queue.get_nowait()
                self._append_log(tag, line)
        except queue.Empty:
            pass
        self.root.after(60, self._pump_log_queue)

    def _log(self, tag: str, text: str) -> None:
        self.log_queue.put((tag, text))

    def _append_log(self, tag: str, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ---------- process control ----------

    def on_start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self._log("warning", "Proses masih berjalan.")
            return

        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_var.set("Running")
        self._paint_dot(PALETTE["accent"])
        self.progress.start(12)
        self._log("info", "Mulai eksekusi RPA...")

        # Windows: hindari popup console child (build --windowed)
        creation_flags = 0
        startupinfo = None
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]

        try:
            self.process = subprocess.Popen(
                [sys.executable, CHILD_FLAG],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=str(exe_dir()),
                creationflags=creation_flags,
                startupinfo=startupinfo,
            )
        except OSError as exc:
            self._on_finished(exit_code=-1, error=str(exc))
            return

        # Aktifkan field command hanya saat child punya stdin pipe aktif.
        self.command_entry.configure(state="normal")
        self.btn_send.configure(state="normal")
        self.command_entry.focus_set()
        self._log(
            "info",
            "Jika RPA meminta input, ketik nilai di Command Input lalu tekan Enter/Send.",
        )

        t_out = threading.Thread(
            target=self._read_stream,
            args=(self.process.stdout, "stdout"),
            daemon=True,
        )
        t_err = threading.Thread(
            target=self._read_stream,
            args=(self.process.stderr, "stderr"),
            daemon=True,
        )
        t_wait = threading.Thread(target=self._wait_process, daemon=True)
        t_out.start()
        t_err.start()
        t_wait.start()
        self.reader_threads = [t_out, t_err, t_wait]

    def send_command(self, _event=None) -> None:
        """Kirim satu baris ke ``input()`` milik proses RPA."""
        process = self.process
        if process is None or process.poll() is not None or process.stdin is None:
            self._log("warning", "Proses RPA tidak sedang menunggu input.")
            return

        value = self.command_var.get()
        try:
            process.stdin.write(value + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            self._log("stderr", f"Gagal mengirim input: {exc}")
            return

        shown = value if value else "<Enter>"
        self._log("input", f"> {shown}")
        self.command_var.set("")
        self.command_entry.focus_set()

    def on_stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self._log("warning", "Menghentikan proses...")
        try:
            self.process.kill()
        except OSError as exc:
            self._log("stderr", f"Gagal kill: {exc}")

    def _read_stream(self, stream, tag: str) -> None:
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                self._log(tag, line.rstrip("\r\n"))
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _wait_process(self) -> None:
        assert self.process is not None
        code = self.process.wait()
        self.root.after(120, lambda c=code: self._on_finished(exit_code=c))

    def _on_finished(self, exit_code: int, error: str | None = None) -> None:
        if self.process is not None and self.process.stdin is not None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        self.command_entry.configure(state="disabled")
        self.btn_send.configure(state="disabled")
        self.command_var.set("")
        self.progress.stop()
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        if error:
            self._log("stderr", f"Gagal start proses: {error}")
            self.status_var.set("Error")
            self._paint_dot(PALETTE["danger"])
        elif exit_code == 0:
            self._log("success", "Selesai. Exit code 0.")
            self.status_var.set("Finished")
            self._paint_dot(PALETTE["success"])
        else:
            self._log("stderr", f"Selesai dengan exit code {exit_code}.")
            self.status_var.set(f"Exit {exit_code}")
            self._paint_dot(PALETTE["danger"])
        self.process = None

    def on_close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            if not messagebox.askyesno(
                "Konfirmasi",
                "Proses RPA masih berjalan. Hentikan dan tutup?",
            ):
                return
            try:
                self.process.kill()
            except OSError:
                pass
        self.root.destroy()


# ---------------------------------------------------------------- entry ----


def _write_startup_error(exc: BaseException) -> Path | None:
    """Persist traceback karena executable --windowed tidak punya console."""
    path = exe_dir() / "launcher_error.log"
    try:
        path.write_text(
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            encoding="utf-8",
        )
        return path
    except OSError:
        return None


def main() -> int:
    if CHILD_FLAG in sys.argv[1:]:
        return run_as_child()

    root = None
    try:
        root = tk.Tk()
        LauncherApp(root)

        # Onefile dapat butuh waktu lama untuk extract. Saat GUI siap, paksa
        # window muncul di depan agar tidak tersembunyi di belakang terminal.
        root.update_idletasks()
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)
        root.after(600, lambda: root.attributes("-topmost", False))
        root.focus_force()
        root.mainloop()
        return 0
    except BaseException as exc:  # noqa: BLE001 - startup harus terdiagnosis
        log_path = _write_startup_error(exc)
        if root is not None:
            try:
                detail = str(exc)
                if log_path is not None:
                    detail += f"\n\nDetail disimpan di:\n{log_path}"
                messagebox.showerror("Launcher Error", detail)
            except BaseException:
                pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
'''


_TOKEN_ENTRY = "__RPA_ENTRY_MODULE__"
_TOKEN_LABEL = "__RPA_PROJECT_LABEL__"


def generate_launcher_source(
    entry_module: str,
    project_label: str,
) -> str:
    if not entry_module:
        raise ValueError("entry_module kosong")
    for part in entry_module.split("."):
        if not part.isidentifier():
            raise ValueError(f"Nama modul entry tidak valid: {entry_module!r}")

    safe_label = project_label.replace("\\", "\\\\").replace('"', '\\"')
    source = (
        _LAUNCHER_TEMPLATE
        .replace(_TOKEN_ENTRY, entry_module)
        .replace(_TOKEN_LABEL, safe_label)
    )
    logger.debug("Launcher source ter-generate (%d karakter)", len(source))
    return source


def write_launcher(
    target_path: Path,
    entry_module: str,
    project_label: str,
) -> Path:
    source = generate_launcher_source(entry_module, project_label)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(source, encoding="utf-8")
    logger.info("Launcher ditulis ke %s", target_path)
    return target_path
