"""Dry-run pipeline converter melawan proyek RPA nyata (tanpa build)."""
from __future__ import annotations

import sys
from pathlib import Path

# Import dari root converter
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from converter.dependency_resolver import (  # noqa: E402
    build_add_data_args,
    resolve_dependencies,
)
from converter.entrypoint_detector import find_entry_points  # noqa: E402
from converter.scanner import scan_project  # noqa: E402
from converter.wrapper_generator import generate_launcher_source  # noqa: E402


def run(project_root: Path) -> None:
    print(f"[SCAN] project_root = {project_root}")
    scan = scan_project(project_root)
    print(f"       python_files = {len(scan.python_files)}")
    print(f"       data_files   = {len(scan.data_files)}")
    print(f"       project_name = {scan.project_name!r}")
    print()

    candidates = find_entry_points(scan.python_files, scan.project_root)
    print(f"[ENTRY] candidates = {len(candidates)}")
    for c in candidates:
        print(
            f"   - {c.display_name}"
            f"   [module={c.module_name!r} parent_rel={c.parent_relative}]"
        )
    if not candidates:
        print("   (none)")
        return
    entry = candidates[0]
    print(f"[ENTRY] pilihan   = {entry.display_name}")
    print()

    extra = []
    if entry.parent_dir != project_root.resolve():
        extra.append(entry.parent_dir)
    print(f"[DEP] extra_search_roots = {[str(p) for p in extra]}")
    deps = resolve_dependencies(scan.python_files, scan.project_root, extra)
    print(f"      local        = {sorted(deps.local_modules)}")
    print(f"      third_party  = {sorted(deps.third_party)}")
    print(f"      stdlib count = {len(deps.stdlib)}")
    if deps.unresolved:
        print(f"      unresolved   = {sorted(deps.unresolved)}")
    print(f"      hidden_imports (--hidden-import): {deps.hidden_imports}")
    print()

    add_data = build_add_data_args(scan.data_files, scan.project_root)
    print(f"[DATA] --add-data entries = {len(add_data)}")
    for a in add_data[:6]:
        print(f"   - {a}")
    if len(add_data) > 6:
        print(f"   ... (+{len(add_data) - 6} more)")
    print()

    print("[WRAP] generate launcher source...")
    src = generate_launcher_source(entry.module_name, project_root.name)
    print(f"       size = {len(src)} chars")

    # Validasi sintaks launcher yang di-generate
    import ast
    ast.parse(src)
    print("       AST parse OK")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        p = Path(arg).resolve()
        print("=" * 78)
        run(p)
        print()
