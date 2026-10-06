from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

IGNORED_DIRS: frozenset[str] = frozenset({
    "venv", ".venv", "env", ".env",
    "__pycache__",
    ".git", ".hg", ".svn",
    "build", "dist", ".eggs",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "node_modules",
    ".idea", ".vscode",
})

IGNORED_DIR_PATTERNS: tuple[str, ...] = ("*.egg-info",)

DATA_FILE_EXTENSIONS: frozenset[str] = frozenset({
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".txt", ".csv", ".xml", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".bmp",
    ".ttf", ".otf", ".woff", ".woff2",
    ".sql", ".db",
    ".env", 
})


@dataclass
class ScanResult:
    """Hasil scan folder proyek RPA."""

    project_root: Path
    python_files: list[Path] = field(default_factory=list)
    data_files: list[Path] = field(default_factory=list)

    @property
    def project_name(self) -> str:
        """Nama proyek (nama folder root, disanitasi untuk nama file)."""
        return _sanitize_name(self.project_root.name)


def _is_ignored_dir(name: str) -> bool:
    """True jika nama direktori masuk daftar ignore (exact atau glob)."""
    if name in IGNORED_DIRS:
        return True
    return any(fnmatch.fnmatch(name, pat) for pat in IGNORED_DIR_PATTERNS)


def _sanitize_name(name: str) -> str:
    """Buat nama aman untuk file executable Windows."""
    keep = "-_"
    cleaned = "".join(c if c.isalnum() or c in keep else "_" for c in name)
    cleaned = cleaned.strip("_") or "project"
    return cleaned


def scan_project(project_root: str | Path) -> ScanResult:
    """Telusuri ``project_root`` secara rekursif.

    Args:
        project_root: Path folder root proyek RPA.

    Returns:
        :class:`ScanResult` berisi daftar file .py dan file data.

    Raises:
        FileNotFoundError: jika ``project_root`` tidak ada.
        NotADirectoryError: jika ``project_root`` bukan direktori.
    """
    root = Path(project_root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Folder proyek tidak ditemukan: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path bukan direktori: {root}")

    logger.info("Scan proyek: %s", root)
    result = ScanResult(project_root=root)

    for path in _iter_files(root):
        suffix = path.suffix.lower()
        if suffix == ".py":
            result.python_files.append(path)
        elif suffix in DATA_FILE_EXTENSIONS:
            result.data_files.append(path)

    logger.info(
        "Scan selesai: %d file .py, %d file data",
        len(result.python_files),
        len(result.data_files),
    )
    return result


def _iter_files(root: Path) -> Iterable[Path]:
    """Generator file, skip direktori terlarang secara efisien."""
    # os.walk lebih efisien untuk prune direktori dibanding Path.rglob
    import os

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune in-place supaya os.walk tidak turun ke dir yang di-skip
        dirnames[:] = [d for d in dirnames if not _is_ignored_dir(d)]
        base = Path(dirpath)
        for name in filenames:
            yield base / name


def relative_module_path(file_path: Path, project_root: Path) -> str:
    """Konversi path file .py menjadi nama modul dotted (relative ke root).

    Contoh: ``/proj/utils/helpers.py`` dengan root ``/proj`` -> ``utils.helpers``.
    """
    rel = file_path.resolve().relative_to(project_root.resolve())
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)
