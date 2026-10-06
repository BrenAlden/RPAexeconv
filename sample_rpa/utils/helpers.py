"""Fungsi helper untuk sample RPA."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def timestamp_now() -> str:
    """Timestamp ISO-like tanpa timezone (mis. ``2026-09-30 14:22:05``)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_input_files(input_dir: Path, pattern: str = "*.txt") -> list[Path]:
    """Kembalikan semua file di ``input_dir`` yang cocok ``pattern``, urut nama."""
    if not input_dir.is_dir():
        return []
    return sorted(input_dir.glob(pattern))


def write_output(dst: Path, content: str) -> Path:
    """Tulis ``content`` ke ``dst`` (UTF-8). Buat parent kalau perlu."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
    return dst
