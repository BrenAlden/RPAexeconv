"""GUI konverter: pilih proyek, entry point, icon, output; klik Build.

Layout:
    - Header
    - Form: Project folder | Entry point (dropdown) | Icon (opsional) | Output
    - Toolbar: Build / Open Output
    - Progress bar + Panel log
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from .builder import (
    BuildError,
    BuildOptions,
    BuildResult,
    build_exe,
    check_pyinstaller_available,
    default_output_dir,
)
from .entrypoint_detector import (
    EntryPointCandidate,
    find_entry_points,
)
from .scanner import ScanResult, scan_project

logger = logging.getLogger(__name__)

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
    "entry_bg":  "#181825",
}


class ConverterApp:
    """Aplikasi konverter."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.scan_result: ScanResult | None = None
        self.entry_points: list[EntryPointCandidate] = []
        self.build_thread: threading.Thread | None = None
        self.log_queue: queue.Queue = queue.Queue()

        self._build_ui()
        self._pump_log_queue()
        self._check_pyinstaller_async()

    # ---------------------------------------------------------------- UI ---

    def _build_ui(self) -> None:
        self.root.title("RPA EXE Converter")
        self.root.geometry("880x640")
        self.root.minsize(720, 520)
        self.root.configure(bg=PALETTE["bg"])

        try:
            self.root.tk.call("tk", "scaling", 1.2)
        except tk.TclError:
            pass

        tkfont.nametofont("TkDefaultFont").configure(family="Segoe UI", size=10)
        self._mono = tkfont.Font(family="Consolas", size=10)

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self._apply_style(style)

        # ---------- Header ----------
        header = tk.Frame(self.root, bg=PALETTE["surface"], height=72)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        tk.Label(
            header, text="RPA EXE Converter",
            fg=PALETTE["text"], bg=PALETTE["surface"],
            font=("Segoe UI Semibold", 16),
        ).pack(side="left", padx=20, pady=(14, 0), anchor="w")
        tk.Label(
            header,
            text="Package folder Python RPA menjadi satu executable Windows.",
            fg=PALETTE["text_dim"], bg=PALETTE["surface"],
            font=("Segoe UI", 9),
        ).place(x=20, y=42)

        self.pyi_status_var = tk.StringVar(value="Cek PyInstaller...")
        tk.Label(
            header, textvariable=self.pyi_status_var,
            fg=PALETTE["text_dim"], bg=PALETTE["surface"],
            font=("Segoe UI", 9),
        ).pack(side="right", padx=20)

        # ---------- Form ----------
        form = tk.Frame(self.root, bg=PALETTE["bg"])
        form.pack(fill="x", padx=16, pady=12)
        form.columnconfigure(1, weight=1)

        # Project folder
        self._label(form, "Project folder", row=0)
        self.project_var = tk.StringVar()
        self._entry(form, self.project_var, row=0, column=1)
        self._btn(form, "Browse...", row=0, column=2,
                  command=self.on_pick_project)

        # Entry point
        self._label(form, "Entry point", row=1)
        self.entry_var = tk.StringVar()
        self.entry_combo = ttk.Combobox(
            form, textvariable=self.entry_var, state="readonly",
            values=[],
        )
        self.entry_combo.grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=6)
        self._btn(form, "Rescan", row=1, column=2, command=self.on_rescan)

        # Icon (opsional)
        self._label(form, "Icon (.ico) [opsional]", row=2)
        self.icon_var = tk.StringVar()
        self._entry(form, self.icon_var, row=2, column=1)
        self._btn(form, "Browse...", row=2, column=2, command=self.on_pick_icon)

        # Output folder
        self._label(form, "Output folder", row=3)
        self.output_var = tk.StringVar()
        self._entry(form, self.output_var, row=3, column=1)
        self._btn(form, "Browse...", row=3, column=2, command=self.on_pick_output)

        # ---------- Toolbar ----------
        toolbar = tk.Frame(self.root, bg=PALETTE["bg"])
        toolbar.pack(fill="x", padx=16, pady=(4, 8))

        self.btn_build = ttk.Button(
            toolbar, text="\u26A1  Build EXE",
            style="Accent.TButton", command=self.on_build,
        )
        self.btn_build.pack(side="left")

        self.btn_open_out = ttk.Button(
            toolbar, text="Open Output Folder",
            command=self.on_open_output, state="disabled",
        )
        self.btn_open_out.pack(side="left", padx=(8, 0))

        ttk.Button(toolbar, text="Clear Log",
                   command=self._clear_log).pack(side="right")

        # ---------- Progress ----------
        self.progress = ttk.Progressbar(
            self.root, mode="indeterminate",
            style="Accent.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x", padx=16, pady=(0, 8))

        # ---------- Log ----------
        log_wrap = tk.Frame(self.root, bg=PALETTE["surface"], bd=0)
        log_wrap.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self.log = tk.Text(
            log_wrap, wrap="word", bd=0, padx=12, pady=8,
            bg=PALETTE["surface"], fg=PALETTE["text"],
            insertbackground=PALETTE["text"], font=self._mono,
            state="disabled",
        )
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(log_wrap, orient="vertical", command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log["yscrollcommand"] = sb.set

        for tag, color in [
            ("info",    PALETTE["accent"]),
            ("out",     PALETTE["text"]),
            ("err",     PALETTE["danger"]),
            ("warn",    PALETTE["warning"]),
            ("success", PALETTE["success"]),
            ("cmd",     PALETTE["text_dim"]),
        ]:
            self.log.tag_config(tag, foreground=color)

        # ---------- Statusbar ----------
        self.status_var = tk.StringVar(value="Siap.")
        status = tk.Frame(self.root, bg=PALETTE["surface"], height=24)
        status.pack(fill="x", side="bottom")
        status.pack_propagate(False)
        tk.Label(
            status, textvariable=self.status_var,
            fg=PALETTE["text_dim"], bg=PALETTE["surface"],
            font=("Segoe UI", 9),
        ).pack(side="left", padx=12)

        self._log("info", "Selamat datang di RPA EXE Converter.")
        self._log("info", "Pilih folder proyek RPA untuk memulai.")

    def _apply_style(self, style: ttk.Style) -> None:
        style.configure(
            "TButton", background=PALETTE["surface2"], foreground=PALETTE["text"],
            borderwidth=0, focusthickness=0, padding=(12, 6),
            font=("Segoe UI", 10),
        )
        style.map(
            "TButton",
            background=[("active", PALETTE["accent"]),
                        ("disabled", PALETTE["surface2"])],
            foreground=[("disabled", PALETTE["text_dim"])],
        )
        style.configure(
            "Accent.TButton", background=PALETTE["accent"], foreground="#11111b",
            font=("Segoe UI Semibold", 10), padding=(16, 8),
        )
        style.map(
            "Accent.TButton",
            background=[("active", PALETTE["accent_hi"]),
                        ("disabled", PALETTE["surface2"])],
            foreground=[("disabled", PALETTE["text_dim"])],
        )
        style.configure(
            "TEntry",
            fieldbackground=PALETTE["entry_bg"],
            foreground=PALETTE["text"],
            insertcolor=PALETTE["text"],
            borderwidth=0, padding=6,
        )
        style.configure(
            "TCombobox",
            fieldbackground=PALETTE["entry_bg"],
            background=PALETTE["surface2"],
            foreground=PALETTE["text"],
            arrowcolor=PALETTE["text"],
            borderwidth=0, padding=6,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", PALETTE["entry_bg"])],
            selectbackground=[("readonly", PALETTE["entry_bg"])],
            selectforeground=[("readonly", PALETTE["text"])],
        )
        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor=PALETTE["surface"], background=PALETTE["accent"],
            bordercolor=PALETTE["surface"],
            lightcolor=PALETTE["accent"], darkcolor=PALETTE["accent"],
        )

        # Dropdown popup styling (Tk klasik, bukan ttk)
        self.root.option_add("*TCombobox*Listbox.background", PALETTE["surface2"])
        self.root.option_add("*TCombobox*Listbox.foreground", PALETTE["text"])
        self.root.option_add(
            "*TCombobox*Listbox.selectBackground", PALETTE["accent"],
        )
        self.root.option_add(
            "*TCombobox*Listbox.selectForeground", "#11111b",
        )

    def _label(self, parent: tk.Widget, text: str, row: int) -> None:
        tk.Label(
            parent, text=text, fg=PALETTE["text_dim"], bg=PALETTE["bg"],
            font=("Segoe UI", 9), anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=(4, 8), pady=6)

    def _entry(self, parent: tk.Widget, var: tk.StringVar,
               row: int, column: int) -> None:
        e = ttk.Entry(parent, textvariable=var)
        e.grid(row=row, column=column, sticky="ew", padx=(8, 8), pady=6)

    def _btn(self, parent: tk.Widget, text: str, row: int, column: int,
             command) -> None:
        ttk.Button(parent, text=text, command=command).grid(
            row=row, column=column, padx=(0, 4), pady=6,
        )

    # ------------------------------------------------------------ actions --

    def on_pick_project(self) -> None:
        d = filedialog.askdirectory(title="Pilih folder proyek RPA")
        if not d:
            return
        self.project_var.set(d)
        self._rescan()

    def on_rescan(self) -> None:
        if not self.project_var.get().strip():
            messagebox.showwarning(
                "Rescan", "Pilih folder proyek terlebih dahulu.",
            )
            return
        self._rescan()

    def on_pick_icon(self) -> None:
        f = filedialog.askopenfilename(
            title="Pilih icon (.ico)",
            filetypes=[("Windows Icon", "*.ico"), ("All files", "*.*")],
        )
        if f:
            self.icon_var.set(f)

    def on_pick_output(self) -> None:
        d = filedialog.askdirectory(title="Pilih folder output")
        if d:
            self.output_var.set(d)

    def on_open_output(self) -> None:
        out = self.output_var.get().strip()
        if not out:
            return
        path = Path(out)
        if not path.exists():
            self._log("warn", f"Folder output belum ada: {path}")
            return
        try:
            import os
            os.startfile(str(path))  # type: ignore[attr-defined]
        except (OSError, AttributeError):
            import subprocess
            subprocess.Popen(["explorer", str(path)])

    def on_build(self) -> None:
        if self.build_thread is not None and self.build_thread.is_alive():
            messagebox.showinfo("Build", "Build sedang berjalan.")
            return

        project = self.project_var.get().strip()
        if not project:
            messagebox.showwarning("Build", "Pilih folder proyek terlebih dahulu.")
            return
        if self.scan_result is None:
            self._rescan()
            if self.scan_result is None:
                return

        entry_label = self.entry_var.get().strip()
        entry = self._find_entry_by_label(entry_label)
        if entry is None:
            messagebox.showerror(
                "Build",
                "Entry point tidak dipilih. Rescan dan pilih dari dropdown.",
            )
            return

        output = self.output_var.get().strip()
        if not output:
            output_path = default_output_dir(self.scan_result.project_root)
            self.output_var.set(str(output_path))
        else:
            output_path = Path(output)

        icon_path: Path | None = None
        if self.icon_var.get().strip():
            icon_path = Path(self.icon_var.get().strip())

        options = BuildOptions(
            scan_result=self.scan_result,
            entry_point=entry,
            output_dir=output_path,
            icon_path=icon_path,
        )

        self._set_building(True)
        self.build_thread = threading.Thread(
            target=self._build_worker, args=(options,), daemon=True,
        )
        self.build_thread.start()

    # ------------------------------------------------------------- worker --

    def _build_worker(self, options: BuildOptions) -> None:
        try:
            result: BuildResult = build_exe(options, log=self._log)
            self.root.after(0, self._on_build_success, result)
        except BuildError as exc:
            self.root.after(0, self._on_build_error, str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Build gagal tak terduga")
            self.root.after(0, self._on_build_error, f"Error tak terduga: {exc}")

    def _on_build_success(self, result: BuildResult) -> None:
        self._set_building(False)
        self._log("success", f"Build sukses: {result.exe_path}")
        self.btn_open_out.configure(state="normal")
        self.status_var.set(f"Sukses. Exe: {result.exe_path}")
        messagebox.showinfo(
            "Build sukses",
            f"Executable dibuat:\n{result.exe_path}\n\n"
            f"Folder input/ dan output/ sudah dibuat di sebelahnya.",
        )

    def _on_build_error(self, msg: str) -> None:
        self._set_building(False)
        self._log("err", msg)
        self.status_var.set("Build gagal.")
        messagebox.showerror("Build gagal", msg)

    def _set_building(self, building: bool) -> None:
        if building:
            self.btn_build.configure(state="disabled")
            self.progress.start(12)
            self.status_var.set("Building...")
        else:
            self.btn_build.configure(state="normal")
            self.progress.stop()

    # ---------------------------------------------------------- scan flow --

    def _rescan(self) -> None:
        project = self.project_var.get().strip()
        if not project:
            return
        proj_path = Path(project)
        try:
            self._log("info", f"Scan proyek: {proj_path}")
            self.scan_result = scan_project(proj_path)
        except (FileNotFoundError, NotADirectoryError) as exc:
            self._log("err", str(exc))
            messagebox.showerror("Scan error", str(exc))
            self.scan_result = None
            return

        self._log("info",
                  f"Ditemukan {len(self.scan_result.python_files)} file .py, "
                  f"{len(self.scan_result.data_files)} file data.")

        self.entry_points = find_entry_points(
            self.scan_result.python_files,
            self.scan_result.project_root,
        )
        labels = [c.display_name for c in self.entry_points]
        self.entry_combo["values"] = labels
        if labels:
            self.entry_var.set(labels[0])
            self._log("info",
                      f"Kandidat entry point: {len(labels)}. Dipilih: {labels[0]}")
            if len(labels) > 1:
                self._log("warn",
                          "Multi-kandidat terdeteksi. Ganti pilihan di dropdown "
                          "kalau bukan file yang benar.")
        else:
            self.entry_var.set("")
            self._log("err",
                      'Tidak ada file dengan blok `if __name__ == "__main__":`.')
            messagebox.showerror(
                "Entry point tidak ditemukan",
                "Tidak ada file dengan `if __name__ == \"__main__\":` di proyek.\n"
                "Tambahkan blok tersebut di file utama.",
            )

        # Auto isi output dir
        if not self.output_var.get().strip():
            self.output_var.set(str(default_output_dir(self.scan_result.project_root)))

    def _find_entry_by_label(self, label: str) -> EntryPointCandidate | None:
        for c in self.entry_points:
            if c.display_name == label:
                return c
        return None

    # ---------------------------------------------------------- log queue --

    def _log(self, level: str, msg: str) -> None:
        """Thread-safe log push (dipanggil juga oleh builder worker)."""
        self.log_queue.put((level, msg))

    def _pump_log_queue(self) -> None:
        try:
            while True:
                level, msg = self.log_queue.get_nowait()
                self._append_log(level, msg)
        except queue.Empty:
            pass
        self.root.after(60, self._pump_log_queue)

    def _append_log(self, level: str, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n", level)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------ PyInstaller check

    def _check_pyinstaller_async(self) -> None:
        def _worker() -> None:
            ok, ver = check_pyinstaller_available()
            self.root.after(0, self._on_pyi_checked, ok, ver)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_pyi_checked(self, ok: bool, ver: str) -> None:
        if ok:
            self.pyi_status_var.set(f"PyInstaller {ver}")
            self._log("info", f"PyInstaller terdeteksi: {ver}")
        else:
            self.pyi_status_var.set("PyInstaller: tidak terdeteksi")
            self._log("err", "PyInstaller belum ter-install untuk Python ini.")
            self._log("info", f"Install: {self._pip_install_hint()}")

    @staticmethod
    def _pip_install_hint() -> str:
        import sys as _sys
        return f'"{_sys.executable}" -m pip install pyinstaller'


def run() -> int:
    """Entry point untuk aplikasi GUI konverter."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    root = tk.Tk()
    ConverterApp(root)
    root.mainloop()
    return 0
