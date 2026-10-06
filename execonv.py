"""Entry point CLI/GUI untuk RPA EXE Converter.

Pakai:
    python execonv.py                     # buka GUI
    python execonv.py --project <folder>  # build headless (CLI)

Opsi CLI:
    --project PATH         folder proyek RPA (wajib untuk CLI)
    --entry MODULE         nama modul dotted entry point (opsional; auto kalau tidak ada)
    --output PATH          folder output exe (opsional; default: <parent>/RPA_<name>_dist)
    --icon PATH            icon .ico (opsional)
    --gui                  paksa buka GUI meski ada argumen
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _run_cli(args: argparse.Namespace) -> int:
    from converter.builder import (
        BuildError,
        BuildOptions,
        build_exe,
        check_pyinstaller_available,
        default_output_dir,
    )
    from converter.entrypoint_detector import (
        EntryPointCandidate,
        EntryPointNotFoundError,
        find_entry_points,
        require_entry_point,
    )
    from converter.scanner import scan_project

    project_root = Path(args.project).resolve()

    ok, ver = check_pyinstaller_available()
    if not ok:
        print(f"[ERROR] PyInstaller tidak tersedia: {ver}", file=sys.stderr)
        return 2
    print(f"[INFO] PyInstaller {ver}")

    try:
        scan = scan_project(project_root)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    candidates = find_entry_points(scan.python_files, scan.project_root)
    entry: EntryPointCandidate | None = None
    if args.entry:
        for c in candidates:
            if c.module_name == args.entry:
                entry = c
                break
        if entry is None:
            print(f"[ERROR] Entry --entry {args.entry!r} tidak ditemukan.",
                  file=sys.stderr)
            print("Kandidat:", file=sys.stderr)
            for c in candidates:
                print(f"  - {c.module_name}  ({c.display_name})", file=sys.stderr)
            return 2
    else:
        try:
            entry = require_entry_point(candidates)
        except EntryPointNotFoundError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 2
        if len(candidates) > 1:
            print(f"[WARN] Multi-kandidat, pakai: {entry.display_name}")
            for c in candidates:
                marker = "*" if c is entry else " "
                print(f"  {marker} {c.module_name}")

    output_dir = Path(args.output).resolve() if args.output else default_output_dir(project_root)
    icon = Path(args.icon).resolve() if args.icon else None

    def _log(level: str, msg: str) -> None:
        print(f"[{level.upper()}] {msg}")

    opts = BuildOptions(
        scan_result=scan,
        entry_point=entry,
        output_dir=output_dir,
        icon_path=icon,
    )
    try:
        result = build_exe(opts, log=_log)
    except BuildError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] Exe: {result.exe_path}")
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="execonv",
        description="Converter proyek RPA Python menjadi satu Windows executable.",
    )
    p.add_argument("--project", help="Path folder proyek RPA (mode CLI)")
    p.add_argument("--entry", help="Nama modul dotted entry point (opsional)")
    p.add_argument("--output", help="Folder output exe")
    p.add_argument("--icon", help="Path ikon .ico (opsional)")
    p.add_argument("--gui", action="store_true", help="Paksa buka GUI")
    p.add_argument("-v", "--verbose", action="store_true", help="Log DEBUG")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.project and not args.gui:
        return _run_cli(args)
    from converter.ui import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
