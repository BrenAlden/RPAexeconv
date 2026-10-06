from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntryPointCandidate:
    """Kandidat entry point yang ditemukan di proyek.

    Perhatikan: :attr:`module_name` sengaja hanya berupa **stem** file (tanpa
    dotted path). Ini menyerupai perilaku ``python <script.py>`` di mana
    direktori file jadi ``sys.path[0]``, dan menghindari nama modul invalid
    saat proyek berada di folder yang mengandung spasi/karakter non-identifier.
    """

    file_path: Path
    project_root: Path

    @property
    def module_name(self) -> str:
        """Nama modul untuk :func:`runpy.run_module` (hanya stem file)."""
        return self.file_path.stem

    @property
    def parent_dir(self) -> Path:
        """Direktori parent absolut dari file entry."""
        return self.file_path.parent.resolve()

    @property
    def parent_relative(self) -> Path:
        """Path parent relatif terhadap ``project_root``.

        Berupa ``Path(".")`` kalau entry berada langsung di root proyek.
        """
        return self.parent_dir.relative_to(self.project_root.resolve())

    @property
    def display_name(self) -> str:
        """Label yang enak dibaca di dropdown UI."""
        rel = self.file_path.resolve().relative_to(self.project_root.resolve())
        return str(rel).replace("\\", "/")

    def __str__(self) -> str:  # pragma: no cover - kosmetik
        return self.display_name


def _has_main_guard(tree: ast.AST) -> bool:
    """True jika AST punya top-level ``if __name__ == "__main__":``.

    Menerima bentuk::

        if __name__ == "__main__":
        if "__main__" == __name__:
        if __name__ == '__main__':
    """
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare):
            continue
        if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
            continue

        left, right = test.left, test.comparators[0]
        if _is_dunder_name(left) and _is_main_literal(right):
            return True
        if _is_dunder_name(right) and _is_main_literal(left):
            return True
    return False


def _is_dunder_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "__name__"


def _is_main_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == "__main__"


def find_entry_points(
    python_files: list[Path],
    project_root: Path,
) -> list[EntryPointCandidate]:
    """Kembalikan daftar kandidat entry point, sudah diurutkan prioritas.

    Urutan prioritas:
        1. ``main.py`` di root proyek
        2. File bernama ``main.py`` di kedalaman berapa pun
        3. File bernama ``__main__.py``
        4. File dengan main guard di root proyek
        5. File lain dengan main guard, diurutkan berdasarkan kedalaman

    Args:
        python_files: daftar path file .py dari :func:`scanner.scan_project`.
        project_root: root proyek RPA.

    Returns:
        List :class:`EntryPointCandidate`. Bisa kosong jika tidak ada.
    """
    root = project_root.resolve()
    candidates: list[EntryPointCandidate] = []

    for py_file in python_files:
        source = _safe_read(py_file)
        if source is None:
            continue
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            logger.warning("Skip %s: syntax error (%s)", py_file, exc)
            continue

        if _has_main_guard(tree):
            candidates.append(EntryPointCandidate(py_file.resolve(), root))

    candidates.sort(key=lambda c: _priority_key(c, root))
    logger.info("Ditemukan %d kandidat entry point", len(candidates))
    return candidates


def _priority_key(cand: EntryPointCandidate, root: Path) -> tuple[int, int, str]:
    """Kunci sort: (kelompok prioritas, kedalaman, path string)."""
    rel = cand.file_path.relative_to(root)
    depth = len(rel.parts) - 1
    name = rel.name

    if name == "main.py" and depth == 0:
        group = 0
    elif name == "main.py":
        group = 1
    elif name == "__main__.py":
        group = 2
    elif depth == 0:
        group = 3
    else:
        group = 4

    return (group, depth, str(rel).lower())


def _safe_read(path: Path) -> str | None:
    """Baca file .py dengan beberapa encoding fallback."""
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            logger.warning("Gagal baca %s: %s", path, exc)
            return None
    logger.warning("Tidak bisa decode %s dengan encoding manapun", path)
    return None


class EntryPointNotFoundError(RuntimeError):
    """Diangkat jika tidak ada file dengan main guard di proyek."""


def require_entry_point(
    candidates: list[EntryPointCandidate],
) -> EntryPointCandidate:
    """Ambil kandidat teratas atau raise error yang informatif."""
    if not candidates:
        raise EntryPointNotFoundError(
            "Tidak ditemukan file dengan blok `if __name__ == \"__main__\":`.\n"
            "Tambahkan blok tersebut ke file utama proyek RPA Anda, atau\n"
            "pilih file entry point secara manual."
        )
    return candidates[0]
