"""Resolusi dependency: ekstrak import via AST, pisahkan lokal vs third-party.

Tujuan:
    1. Kumpulkan semua top-level module name yang diimport dari file .py.
    2. Klasifikasikan sebagai lokal (ada file/package di dalam proyek),
       stdlib (ada di :data:`sys.stdlib_module_names`), atau third-party.
    3. Sediakan list untuk ``--hidden-import`` PyInstaller supaya import
       tidak langsung (mis. dynamic import) tetap ter-bundle.
"""

from __future__ import annotations

import ast
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Python 3.10+ menyediakan sys.stdlib_module_names sebagai frozenset str
_STDLIB: frozenset[str] = getattr(sys, "stdlib_module_names", frozenset())


@dataclass
class DependencyGraph:
    """Ringkasan dependency dari sekumpulan file .py."""

    local_modules: set[str] = field(default_factory=set)
    third_party: set[str] = field(default_factory=set)
    stdlib: set[str] = field(default_factory=set)
    unresolved: set[str] = field(default_factory=set)

    @property
    def hidden_imports(self) -> list[str]:
        """Union lokal + third-party, siap dipakai untuk ``--hidden-import``.

        Sudah diurutkan supaya command PyInstaller reproducible.
        """
        return sorted(self.local_modules | self.third_party)


def _iter_import_names(tree: ast.AST) -> set[str]:
    """Ambil semua top-level module name dari sebuah AST."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # "import a.b.c" -> top level "a"
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # Import relatif (from . import x) tidak punya module absolut,
            # tapi memberi sinyal bahwa parent package adalah lokal.
            if node.level > 0:
                continue
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def _collect_local_module_names(
    python_files: list[Path],
    search_roots: list[Path],
) -> set[str]:
    """Nama top-level modul yang tinggal di dalam salah satu ``search_roots``.

    Definisi "lokal":
        - File ``foo.py`` yang berada langsung di suatu search root -> ``foo``.
        - Direktori ``foo/`` (baik dengan atau tanpa ``__init__.py``) yang
          berada langsung di suatu search root **dan** mengandung minimal satu
          file ``.py`` -> ``foo``.

    Kenapa multiple search roots? Banyak proyek RPA menaruh source-code di
    subfolder (mis. ``Codes/``, ``src/``). File entry point mengasumsikan
    folder tersebut jadi ``sys.path[0]`` saat diinvokasi ``python Main.py``.
    Dengan menambahkan folder itu sebagai search root, kita bisa mengenali
    ``Controller``, ``Config``, dst. sebagai lokal.
    """
    locals_: set[str] = set()
    resolved_roots = [r.resolve() for r in search_roots]

    for root in resolved_roots:
        if not root.is_dir():
            continue
        # File .py langsung di root
        for py in python_files:
            if py.parent.resolve() == root and py.stem != "__init__":
                locals_.add(py.stem)
        # Subdirektori root sebagai package / namespace package
        for child in root.iterdir():
            if not child.is_dir():
                continue
            has_py = any(
                f.suffix == ".py"
                for f in python_files
                if _is_within(f, child)
            )
            if has_py:
                locals_.add(child.name)

    return locals_


def _is_within(path: Path, ancestor: Path) -> bool:
    try:
        path.resolve().relative_to(ancestor.resolve())
        return True
    except ValueError:
        return False


def resolve_dependencies(
    python_files: list[Path],
    project_root: Path,
    extra_search_roots: list[Path] | None = None,
) -> DependencyGraph:
    """Bangun :class:`DependencyGraph` dari semua file .py di proyek.

    Args:
        python_files: file .py hasil scan.
        project_root: root proyek RPA.
        extra_search_roots: root tambahan untuk deteksi modul lokal, mis.
            direktori parent dari entry point yang bersarang.
    """
    graph = DependencyGraph()
    search_roots = [project_root]
    if extra_search_roots:
        search_roots.extend(extra_search_roots)
    local_names = _collect_local_module_names(python_files, search_roots)
    logger.debug("Modul lokal terdeteksi: %s", sorted(local_names))

    all_imports: set[str] = set()
    for py in python_files:
        try:
            source = py.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            try:
                source = py.read_text(encoding="latin-1")
            except OSError as exc:
                logger.warning("Skip import scan %s: %s", py, exc)
                continue
        try:
            tree = ast.parse(source, filename=str(py))
        except SyntaxError as exc:
            logger.warning("Skip %s: syntax error saat scan import (%s)", py, exc)
            continue
        all_imports.update(_iter_import_names(tree))

    for name in all_imports:
        if not name:
            continue
        if name in local_names:
            graph.local_modules.add(name)
        elif name in _STDLIB:
            graph.stdlib.add(name)
        else:
            graph.third_party.add(name)

    logger.info(
        "Dependency: %d lokal, %d third-party, %d stdlib",
        len(graph.local_modules),
        len(graph.third_party),
        len(graph.stdlib),
    )
    return graph


# Mapping nama PyPI -> nama modul Python.
# Beberapa paket punya nama distribusi (di pip / requirements.txt) yang beda
# dengan nama module saat di-import. PyInstaller butuh nama modul untuk
# --hidden-import, bukan nama distribusi.
_PYPI_TO_IMPORT: dict[str, list[str]] = {
    "pywin32": ["win32com", "win32api", "win32con", "win32gui",
                "pywintypes", "pythoncom"],
    "python-dateutil": ["dateutil"],
    "pillow": ["PIL"],
    "pyyaml": ["yaml"],
    "beautifulsoup4": ["bs4"],
    "msgpack-python": ["msgpack"],
    "python-dotenv": ["dotenv"],
    "opencv-python": ["cv2"],
    "opencv-python-headless": ["cv2"],
    "scikit-learn": ["sklearn"],
    "scikit-image": ["skimage"],
    "protobuf": ["google.protobuf"],
    "grpcio": ["grpc"],
    "pymongo": ["pymongo", "bson"],
    "azure-storage-blob": ["azure.storage.blob"],
}


def _split_requirement(line: str) -> str | None:
    """Ambil nama paket dari satu baris ``requirements.txt``."""
    # Buang komentar & whitespace
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith("-"):  # -e, -r, --index-url, ...
        return None
    # Buang extras ``pkg[extra]``, version specifier, dan environment markers
    for sep in (";", "==", ">=", "<=", "!=", "~=", ">", "<", "["):
        if sep in line:
            line = line.split(sep, 1)[0]
    line = line.strip()
    return line.lower() or None


def parse_requirements_file(path: Path) -> list[str]:
    """Baca ``requirements.txt`` dan kembalikan nama paket (lowercase)."""
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        text = path.read_text(encoding="latin-1", errors="replace")
    names: list[str] = []
    for raw in text.splitlines():
        name = _split_requirement(raw)
        if name and name not in names:
            names.append(name)
    return names


def hidden_imports_from_requirements(req_names: list[str]) -> list[str]:
    """Konversi nama paket PyPI menjadi nama import untuk ``--hidden-import``.

    Menerapkan mapping alias populer (pywin32 -> win32com, dst.). Untuk paket
    yang tidak ada di mapping, nama paket dipakai apa adanya. Underscore lebih
    umum di nama modul dibanding dash, jadi dash otomatis diubah ke underscore.
    """
    result: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        if name and name not in seen:
            result.append(name)
            seen.add(name)

    for pkg in req_names:
        aliases = _PYPI_TO_IMPORT.get(pkg)
        if aliases:
            for a in aliases:
                _add(a)
        else:
            _add(pkg.replace("-", "_"))
    return result


def build_add_data_args(
    data_files: list[Path],
    project_root: Path,
    separator: str = ";",
) -> list[str]:
    root = project_root.resolve()
    args: list[str] = []
    for f in data_files:
        src = f.resolve()
        try:
            rel_dir = src.parent.relative_to(root)
        except ValueError:
            continue
        # PyInstaller expects "SRC{sep}DEST_DIR". "." artinya root bundle.
        dest = str(rel_dir) if str(rel_dir) != "." else "."
        args.append(f"{src}{separator}{dest}")
    return args
