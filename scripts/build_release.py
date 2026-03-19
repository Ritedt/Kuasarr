#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""Build helper for Kuasarr releases.

Creates Python packages (sdist/wheel) and a Windows EXE via PyInstaller.
All artifact names contain the version pulled from version.json.
"""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "version.json"
RELEASE_ROOT = ROOT / "release"
PYINSTALLER_SPEC_SUFFIX = ".spec"


def read_version() -> str:
    if not VERSION_FILE.exists():
        raise FileNotFoundError(f"version.json nicht gefunden: {VERSION_FILE}")
    data = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    version = data.get("version")
    if not version:
        raise ValueError("version.json enthält keine 'version'-Angabe")
    return version


def ensure_module_available(module_name: str, install_hint: str) -> None:
    if importlib.util.find_spec(module_name) is None:
        raise ModuleNotFoundError(
            f"Das Modul '{module_name}' ist nicht installiert. {install_hint}"
        )


def ensure_module_available_for_interpreter(
    python_exe: str, module_name: str, install_hint: str
) -> None:
    """Check module availability for a specific python interpreter."""
    try:
        subprocess.run(
            [python_exe, "-c", f"import {module_name}"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        raise ModuleNotFoundError(
            f"Das Modul '{module_name}' ist nicht in {python_exe} installiert. {install_hint}"
        ) from exc


def run(cmd, cwd=ROOT):
    print(f"\n>>> Running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def clean_spec_files(exe_name: str):
    spec_file = ROOT / f"{exe_name}{PYINSTALLER_SPEC_SUFFIX}"
    if spec_file.exists():
        spec_file.unlink()


def build_python_packages(version: str, out_dir: Path):
    ensure_module_available("build", "Installiere es z.B. mit 'pip install build'.")
    out_dir.mkdir(parents=True, exist_ok=True)
    run([sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", str(out_dir)])


def build_python_packages_with_interpreter(
    version: str, out_dir: Path, python_exe: str, requirements_override: Path | None = None
):
    """Build wheel/sdist using a specific Python interpreter (e.g., python3.9)."""
    ensure_module_available_for_interpreter(
        python_exe, "build", f"Installiere es z.B. mit '{python_exe} -m pip install build'."
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n>>> Building with interpreter: {python_exe}")
    # If we need a different requirements set, temporarily swap requirements.txt
    requirements_file = ROOT / "requirements.txt"
    backup_file = requirements_file.with_suffix(".txt.bak_py39")

    try:
        if requirements_override:
            if not requirements_override.exists():
                raise FileNotFoundError(f"requirements_override not found: {requirements_override}")
            # backup original
            if requirements_file.exists():
                shutil.copy(requirements_file, backup_file)
            shutil.copy(requirements_override, requirements_file)

        run([python_exe, "-m", "build", "--sdist", "--wheel", "--outdir", str(out_dir)])
    finally:
        # restore original requirements if backup exists
        if backup_file.exists():
            shutil.move(backup_file, requirements_file)


def build_windows_exe(version: str, out_dir: Path, pyinstaller_cmd: str):
    if os.name != "nt":
        print("WARNUNG: PyInstaller kann unter Windows zuverlässiger EXE-Dateien bauen.")
    ensure_module_available("PyInstaller", "Installiere es z.B. mit 'pip install pyinstaller'.")

    out_dir.mkdir(parents=True, exist_ok=True)
    exe_name = f"kuasarr-{version}"

    data_sep = ";" if os.name == "nt" else ":"
    version_data_arg = f"{VERSION_FILE}{data_sep}."

    # Use full interpreter invocation to avoid PATH issues on Windows
    base_cmd = [pyinstaller_cmd] if pyinstaller_cmd else [sys.executable, "-m", "PyInstaller"]

    run(base_cmd + [
        "--clean",
        "--onefile",
        "--name",
        exe_name,
        "--add-data",
        version_data_arg,
        "Kuasarr.py",
    ])

    built_exe = ROOT / "dist" / f"{exe_name}.exe"
    if not built_exe.exists():
        raise FileNotFoundError(f"Erstellte EXE nicht gefunden: {built_exe}")

    target = out_dir / built_exe.name
    shutil.move(str(built_exe), target)
    print(f"EXE gespeichert unter: {target}")

    # Aufräumen der PyInstaller-Artefakte (optional)
    clean_spec_files(exe_name)


def parse_args():
    parser = argparse.ArgumentParser(description="Build Kuasarr Releases")
    parser.add_argument(
        "--skip-python", action="store_true", help="Python-Wheel/SDist überspringen"
    )
    parser.add_argument(
        "--python39",
        default=None,
        help="Pfad zu einem Python 3.9 Interpreter, um zusätzlich ein 3.9-kompatibles Wheel/Sdist zu bauen (optional)",
    )
    parser.add_argument(
        "--python39-req",
        default=str((ROOT / "scripts" / "requirements-py39.txt")),
        help="Pfad zu requirements-Datei für den 3.9-Build (Standard: scripts/requirements-py39.txt)",
    )
    parser.add_argument(
        "--skip-exe", action="store_true", help="Windows-EXE-Build überspringen"
    )
    parser.add_argument(
        "--pyinstaller",
        default=None,
        help="PyInstaller-Befehl (Default: current python -m PyInstaller)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    version = read_version()
    release_dir = RELEASE_ROOT / f"kuasarr-{version}"

    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True)

    print(f"Baue Kuasarr Version {version}\nArtefakte: {release_dir}\n")

    if args.python39:
        # Nur 3.9-Build erzeugen, wenn explizit angefordert
        python39_dir = release_dir / "python39"
        req_override = Path(args.python39_req) if args.python39_req else None
        build_python_packages_with_interpreter(version, python39_dir, args.python39, req_override)
    elif not args.skip_python:
        # Standard-Build (aktueller Interpreter)
        python_dir = release_dir / "python"
        build_python_packages(version, python_dir)

    # EXE nur bauen, wenn explizit nicht übersprungen und kein reiner Python39-Build
    if not args.skip_exe and not args.python39:
        windows_dir = release_dir / "windows"
        build_windows_exe(version, windows_dir, args.pyinstaller)

    print("\nFertig!")


if __name__ == "__main__":
    main()
