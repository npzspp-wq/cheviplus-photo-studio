"""Fast static audit checks run before building the Windows EXE."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def main():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    patch_source = (ROOT / "cheviplus_stability_patch.py").read_text(encoding="utf-8")
    spec_source = (ROOT / "CheviplusPhotoStudio.spec").read_text(encoding="utf-8")
    workflow_source = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")

    ast.parse(app_source)
    ast.parse(patch_source)

    require("launcher.py" in spec_source, "PyInstaller must package launcher.py with stability patches")
    require("scipy==" in requirements, "scipy must be pinned explicitly because app imports scipy.ndimage")
    require("pull_request:" in workflow_source, "GitHub Actions checks must run on pull requests")
    require("python -m unittest discover" in workflow_source, "Unit tests must run before EXE build")
    require("python -m compileall app.py" in workflow_source, "Syntax check must run before EXE build")

    # Guard against reintroducing aggressive single-largest-component cleanup in the patch layer.
    require("real_separate_part" in patch_source, "Separated kit parts must be preserved by cleanup logic")
    require("_fix_basic_grid" in patch_source, "Tkinter/grid placement fix must remain active")
    print("Static audit checks passed")


if __name__ == "__main__":
    main()
