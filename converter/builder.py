"""Builder: siapkan workspace dan invoke PyInstaller menghasilkan .exe onefile.

Alur:
    1. Buat workspace temporer.
    2. Copy proyek RPA ke ``<workspace>/project/`` (bebas polusi build).
    3. Tulis launcher ke ``<workspace>/_rpa_launcher.py``.
    4. Jalankan PyInstaller dengan --onefile --windowed --name RPA_<nama>.
    5. Pindahkan exe ke folder output final.
    6. Buat folder ``input/`` dan ``output/`` di sebelah exe.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .dependency_resolver import (
    DependencyGraph,
    build_add_data_args,
    hidden_imports_from_requirements,
    parse_requirements_file,
    resolve_dependencies,
)
from .entrypoint_detector import EntryPointCandidate
from .scanner import IGNORED_DIRS, ScanResult, _sanitize_name
from .wrapper_generator import write_launcher

logger = logging.getLogger(__name__)

LogCallback = Callable[[str, str], None]
"""Callback log: ``fn(level, message)`` dengan level: info|warn|error|cmd|out."""


# Modul yang default di-exclude supaya exe tidak membengkak jika tidak
# dipakai proyek RPA. User bisa override lewat BuildOptions.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    "torch", "torchvision", "torchaudio",
    "tensorflow", "tensorboard",
    "matplotlib",
    "IPython", "jupyter", "notebook", "ipykernel",
    "pytest",
    "sphinx",
)


@dataclass
class BuildOptions:
    """Opsi untuk memicu build."""

    scan_result: ScanResult
    entry_point: EntryPointCandidate
    output_dir: Path
    icon_path: Path | None = None
    extra_hidden_imports: list[str] = field(default_factory=list)
    excludes: list[str] = field(
        default_factory=lambda: list(DEFAULT_EXCLUDES),
    )
    clean: bool = True

    @property
    def project_name(self) -> str:
        return self.scan_result.project_name

    @property
    def exe_name(self) -> str:
        """Nama exe dengan tepat satu prefix ``RPA_``."""
        name = self.project_name
        if name.lower().startswith("rpa_"):
            return name
        return f"RPA_{name}"


@dataclass
class BuildResult:
    """Hasil build."""

    success: bool
    exe_path: Path | None
    stdout: str
    stderr: str
    returncode: int

    @property
    def io_dirs(self) -> tuple[Path, Path] | None:
        if self.exe_path is None:
            return None
        base = self.exe_path.parent
        return base / "input", base / "output"


class BuildError(RuntimeError):
    """Diangkat saat PyInstaller gagal atau prasyarat build kurang."""


# ------------------------------------------------------------------ checks ---


def check_pyinstaller_available() -> tuple[bool, str]:
    """Cek apakah PyInstaller ter-install untuk interpreter aktif.

    Returns:
        ``(ok, versi_atau_pesan_error)``.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"Tidak bisa menjalankan PyInstaller: {exc}"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "PyInstaller error").strip()
    return True, proc.stdout.strip()


# --------------------------------------------------------------- workspace ---


def _copy_project(src: Path, dst: Path) -> None:
    """Copy proyek ke workspace, skip direktori yang di-ignore."""
    def _ignore(_dir: str, names: list[str]) -> list[str]:
        return [n for n in names if n in IGNORED_DIRS]

    shutil.copytree(src, dst, ignore=_ignore, dirs_exist_ok=False)


# --------------------------------------------------------------- runner ----


import re as _re

# PyInstaller nulis pesan INFO ke stderr, bukan stdout. Klasifikasi berdasarkan
# level yang tercetak di baris (mis. "909 INFO:", "WARNING:", "ERROR:") jauh
# lebih bermanfaat dibanding hanya melihat stream sumber.
_PYI_LEVEL_RE = _re.compile(
    r"^\s*(?:\d+\s+)?"                              # timestamp opsional
    r"(INFO|DEBUG|WARNING|ERROR|CRITICAL)\s*:\s*",  # level
    _re.IGNORECASE,
)

_LEVEL_TO_TAG = {
    "DEBUG":    "out",
    "INFO":     "out",
    "WARNING":  "warn",
    "ERROR":    "err",
    "CRITICAL": "err",
}


def _classify_pyi_line(line: str, stream: str) -> str:
    """Tentukan tag log untuk satu baris output PyInstaller.

    Args:
        line: konten baris (tanpa newline).
        stream: "stdout" atau "stderr" — dipakai sebagai fallback.
    """
    m = _PYI_LEVEL_RE.match(line)
    if m:
        return _LEVEL_TO_TAG[m.group(1).upper()]
    # Tidak ada level marker: kalau dari stderr anggap warn, stdout anggap out.
    return "warn" if stream == "stderr" else "out"


def _run_pyinstaller(
    args: list[str],
    cwd: Path,
    log: LogCallback,
) -> tuple[int, str, str]:
    """Jalankan PyInstaller dan stream output baris demi baris ke ``log``."""
    log("cmd", " ".join(shlex.quote(a) for a in args))

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    creationflags = 0
    if sys.platform == "win32":
        # Hindari console popup kalau converter sendiri sudah windowed
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    proc = subprocess.Popen(
        args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
        creationflags=creationflags,
    )

    import threading

    def _pump(stream, sink: list[str], stream_name: str) -> None:
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                clean = line.rstrip("\r\n")
                sink.append(clean)
                log(_classify_pyi_line(clean, stream_name), clean)
        finally:
            try:
                stream.close()
            except OSError:
                pass

    t_out = threading.Thread(target=_pump,
                             args=(proc.stdout, stdout_lines, "stdout"),
                             daemon=True)
    t_err = threading.Thread(target=_pump,
                             args=(proc.stderr, stderr_lines, "stderr"),
                             daemon=True)
    t_out.start()
    t_err.start()
    rc = proc.wait()
    t_out.join(timeout=2)
    t_err.join(timeout=2)
    return rc, "\n".join(stdout_lines), "\n".join(stderr_lines)

def build_exe(
    options: BuildOptions,
    log: LogCallback | None = None,
) -> BuildResult:
    """Build satu exe dari proyek RPA.

    Args:
        options: opsi build.
        log: callback opsional untuk streaming log. Signature: ``fn(level, msg)``.

    Returns:
        :class:`BuildResult`.

    Raises:
        BuildError: kalau prasyarat kurang (PyInstaller tidak ada, dsb.)
            atau input tidak konsisten.
    """
    _log: LogCallback = log or (lambda _lvl, _msg: None)

    # --- Validasi prasyarat -------------------------------------------------
    ok, ver = check_pyinstaller_available()
    if not ok:
        raise BuildError(
            "PyInstaller tidak tersedia untuk interpreter aktif.\n"
            f"Detail: {ver}\n"
            "Install dengan: pip install pyinstaller"
        )
    _log("info", f"PyInstaller {ver}")

    scan = options.scan_result
    ep = options.entry_point
    if ep.project_root.resolve() != scan.project_root.resolve():
        raise BuildError("Entry point berasal dari proyek lain dari scan_result.")

    project_root = scan.project_root.resolve()
    output_dir = options.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if options.icon_path is not None:
        icon = options.icon_path.resolve()
        if not icon.is_file():
            raise BuildError(f"Icon tidak ditemukan: {icon}")
        if icon.suffix.lower() != ".ico":
            _log("warn", f"Icon bukan .ico ({icon.suffix}); PyInstaller mungkin menolak.")
    else:
        icon = None

    # --- Siapkan workspace --------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="rpa_build_") as tmp:
        workspace = Path(tmp)
        proj_copy = workspace / "project"
        _log("info", f"Workspace: {workspace}")
        _log("info", f"Copy proyek -> {proj_copy}")
        try:
            _copy_project(project_root, proj_copy)
        except OSError as exc:
            raise BuildError(f"Gagal copy proyek: {exc}") from exc

        from .scanner import scan_project 

        scan_ws = scan_project(proj_copy)

        # Hitung parent entry point di workspace copy. Ini jadi search root
        # tambahan supaya modul yang di-import Main.py (Controller, Config, ...)
        # dikenali sebagai lokal dan ditemukan PyInstaller lewat --paths.
        entry_rel = ep.parent_relative  # relatif ke project root asli
        entry_parent_ws = (proj_copy / entry_rel).resolve()
        entry_parent_ws.mkdir(parents=True, exist_ok=True)

        extra_roots: list[Path] = []
        if entry_parent_ws != proj_copy.resolve():
            extra_roots.append(entry_parent_ws)

        deps: DependencyGraph = resolve_dependencies(
            scan_ws.python_files,
            scan_ws.project_root,
            extra_search_roots=extra_roots,
        )
        _log("info",
             f"Hidden imports: {len(deps.local_modules)} lokal + "
             f"{len(deps.third_party)} third-party")

        launcher_path = workspace / "_rpa_launcher.py"
        write_launcher(
            launcher_path,
            entry_module=ep.module_name,
            project_label=scan.project_root.name,
        )
        _log("info", f"Launcher: {launcher_path.name}")

        # --- Susun argumen PyInstaller -------------------------------------
        exe_name = options.exe_name
        dist_dir = workspace / "dist"
        build_dir = workspace / "build"
        spec_dir = workspace

        # Augment hidden imports dari requirements.txt di root proyek (kalau ada).
        # Ini penting untuk transitif seperti openpyxl yang tidak di-import
        # langsung tapi dibutuhkan pandas.read_excel di runtime.
        req_hidden: list[str] = []
        req_file = proj_copy / "requirements.txt"
        if req_file.is_file():
            req_names = parse_requirements_file(req_file)
            req_hidden = hidden_imports_from_requirements(req_names)
            if req_hidden:
                _log("info",
                     f"requirements.txt: {len(req_names)} paket -> "
                     f"{len(req_hidden)} hidden imports tambahan")

        hidden_imports = sorted(
            (set(deps.hidden_imports)
             | set(options.extra_hidden_imports)
             | set(req_hidden)
             | {ep.module_name}),
        )
        add_data = build_add_data_args(scan_ws.data_files, scan_ws.project_root)

        # --paths urut dari yang paling spesifik (parent entry) ke yang umum
        # (project root) supaya resolusi PyInstaller mengutamakan yang benar.
        paths_args: list[str] = []
        for p in [entry_parent_ws, proj_copy.resolve()]:
            if str(p) not in paths_args:
                paths_args.append(str(p))

        # Excludes: jangan buang modul yang justru dipakai (dari deps.third_party
        # atau requirements). Kalau user memang butuh torch, biarkan.
        effective_excludes: list[str] = []
        do_not_exclude = (
            set(deps.hidden_imports)
            | set(options.extra_hidden_imports)
            | set(req_hidden)
        )
        for mod in options.excludes:
            if mod not in do_not_exclude:
                effective_excludes.append(mod)
        if effective_excludes:
            _log("info",
                 f"Excludes: {', '.join(effective_excludes)} "
                 f"(gunakan BuildOptions.excludes=[] untuk menonaktifkan)")

        args: list[str] = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--windowed",
            "--noconfirm",
            "--name", exe_name,
            "--distpath", str(dist_dir),
            "--workpath", str(build_dir),
            "--specpath", str(spec_dir),
        ]
        for p in paths_args:
            args.extend(["--paths", p])
        for mod in effective_excludes:
            args.extend(["--exclude-module", mod])
        if options.clean:
            args.append("--clean")
        if icon is not None:
            args.extend(["--icon", str(icon)])
        for mod in hidden_imports:
            args.extend(["--hidden-import", mod])
        for data in add_data:
            args.extend(["--add-data", data])
        args.append(str(launcher_path))

        # --- Jalankan -------------------------------------------------------
        _log("info", "Menjalankan PyInstaller...")
        rc, stdout, stderr = _run_pyinstaller(args, cwd=workspace, log=_log)
        if rc != 0:
            raise BuildError(
                f"PyInstaller keluar dengan kode {rc}. Lihat log untuk detail."
            )

        produced = dist_dir / f"{exe_name}.exe"
        if not produced.is_file():
            raise BuildError(
                f"PyInstaller sukses tapi exe tidak ditemukan: {produced}"
            )

        # --- Pindahkan output ke lokasi final ------------------------------
        final_exe = output_dir / f"{exe_name}.exe"
        if final_exe.exists():
            try:
                final_exe.unlink()
            except OSError as exc:
                raise BuildError(
                    f"Gagal menghapus exe lama {final_exe}: {exc}"
                ) from exc
        shutil.move(str(produced), str(final_exe))
        _log("info", f"Exe final: {final_exe}")

        # --- Buat folder input/output di sebelah exe -----------------------
        (output_dir / "input").mkdir(exist_ok=True)
        (output_dir / "output").mkdir(exist_ok=True)
        _log("info", "Folder input/ dan output/ siap.")

        return BuildResult(
            success=True,
            exe_path=final_exe,
            stdout=stdout,
            stderr=stderr,
            returncode=rc,
        )


def default_output_dir(project_root: Path) -> Path:
    """Direktori output default: ``<project_parent>/RPA_<name>_dist``."""
    root = project_root.resolve()
    return root.parent / f"RPA_{_sanitize_name(root.name)}_dist"
