"""Sample RPA: baca file .txt dari folder input, tambahkan header timestamp,
tulis ke folder output.

Dipakai untuk uji coba RPA EXE Converter. Membuktikan:
    - Path input/output dihitung relatif terhadap exe (bukan _MEIPASS).
    - Modul lokal (utils, config) ter-bundle dan bisa di-import.
    - Print statements sampai ke panel log launcher secara real-time.
    - Tombol Stop di launcher bisa menghentikan proses saat sleep panjang.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from config import BATCH_LABEL, VERSION
from utils.helpers import list_input_files, timestamp_now, write_output


def resolve_io_dirs() -> tuple[Path, Path]:
    """Ambil folder input/output dari env var launcher, fallback ke CWD."""
    inp = os.environ.get("RPA_INPUT_DIR")
    out = os.environ.get("RPA_OUTPUT_DIR")
    base = Path.cwd()
    return (
        Path(inp) if inp else base / "input",
        Path(out) if out else base / "output",
    )


def process_file(src: Path, dst_dir: Path) -> Path:
    """Proses satu file .txt: tambahkan header timestamp, tulis ke ``dst_dir``."""
    content = src.read_text(encoding="utf-8", errors="replace")
    stamp = timestamp_now()
    body = (
        f"# Processed by {BATCH_LABEL} v{VERSION}\n"
        f"# Source   : {src.name}\n"
        f"# Timestamp: {stamp}\n"
        f"# {'-' * 40}\n"
        f"{content}\n"
    )
    dst = dst_dir / f"{src.stem}_processed.txt"
    return write_output(dst, body)


def main() -> int:
    print(f"=== {BATCH_LABEL} v{VERSION} ===")
    input_dir, output_dir = resolve_io_dirs()
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = list_input_files(input_dir, pattern="*.txt")
    print(f"Ditemukan {len(files)} file .txt di {input_dir}")

    if not files:
        print("Tidak ada file untuk diproses. Letakkan file .txt di folder input/.")
        sample = input_dir / "hello.txt"
        if not sample.exists():
            sample.write_text(
                "Halo dari sample RPA!\nGanti isi file ini lalu klik Start lagi.\n",
                encoding="utf-8",
            )
            print(f"Sample dibuat: {sample}")
        return 0

    for i, src in enumerate(files, 1):
        print(f"[{i}/{len(files)}] Proses {src.name}...", flush=True)
        time.sleep(0.4)  # simulasi kerja RPA (juga untuk uji tombol Stop)
        dst = process_file(src, output_dir)
        print(f"           -> {dst.name}", flush=True)

    print(f"Selesai. {len(files)} file diproses.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
