r"""Installer for the Mank Scourge of War Editor.

Creates a local virtual environment in .venv\, removes any existing one,
upgrades pip, and installs the runtime dependencies declared in
pyproject.toml.

Usage:
    python install.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent
VENV_DIR = REPO_ROOT / ".venv"
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIRED_MAJOR = 3
REQUIRED_MINOR = 10
PIP_TAIL_LINES = 25


def banner(title: str) -> None:
    line = "=" * 64
    print(line)
    print(f"  {title}")
    print(line)


def status(msg: str) -> None:
    print(f"[*] {msg}")


def ok(msg: str) -> None:
    print(f"[+] {msg}")


def warn(msg: str) -> None:
    print(f"[!] WARNING: {msg}")


def fail(msg: str, hint: Optional[str] = None) -> "None":
    print(f"\nERROR: {msg}")
    if hint:
        print(f"  -> {hint}")
    sys.exit(1)


def parse_dependencies(pyproject_path: Path) -> List[str]:
    if not pyproject_path.is_file():
        fail(
            f"pyproject.toml not found at {pyproject_path}.",
            "Run this script from the repository root.",
        )

    try:
        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        fail(f"pyproject.toml is not valid TOML: {e}")

    project = data.get("project")
    if not isinstance(project, dict):
        fail(
            "pyproject.toml is missing the [project] table.",
            "Add a [project] section with a 'dependencies' list.",
        )

    deps = project.get("dependencies")
    if not isinstance(deps, list) or not deps:
        fail(
            "pyproject.toml has no [project] dependencies list.",
            "Add 'dependencies = [\"PySide6>=6.6\", ...]' under [project].",
        )

    cleaned: List[str] = []
    for dep in deps:
        if not isinstance(dep, str):
            fail(f"Dependency entry is not a string: {dep!r}")
        dep = dep.strip()
        if dep:
            cleaned.append(dep)

    if not cleaned:
        fail("All dependency entries in pyproject.toml are empty.")

    return cleaned


def find_python() -> Tuple[str, str]:
    """Return (python_executable, version_string) for an acceptable interpreter.

    Preference order:
      1. sys.executable (the interpreter running this script)
      2. 'py -3' (Windows launcher)
      3. 'python' on PATH
    """
    candidates: List[Tuple[List[str], str]] = []

    candidates.append(([sys.executable], "current interpreter"))

    if os.name == "nt":
        candidates.append((["py", "-3"], "Windows Python launcher (py -3)"))
    candidates.append((["python"], "python on PATH"))

    for cmd, label in candidates:
        try:
            result = subprocess.run(
                [*cmd, "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            fail(
                f"Found '{label}' but it failed to report a version.",
                f"Output: {stderr or '(no stderr)'}",
            )
        version_text = (result.stdout or result.stderr or "").strip()
        if not is_version_acceptable(version_text):
            continue
        return cmd[0] if len(cmd) == 1 else " ".join(cmd), version_text

    fail(
        f"Python {REQUIRED_MAJOR}.{REQUIRED_MINOR}+ was not found on this system.",
        "Install Python from https://www.python.org/downloads/ and make sure "
        "'Add Python to PATH' is checked during installation.",
    )
    return "", ""  # unreachable


_VERSION_RE = re.compile(r"Python\s+(\d+)\.(\d+)(?:\.(\d+))?", re.IGNORECASE)


def is_version_acceptable(version_text: str) -> bool:
    match = _VERSION_RE.search(version_text)
    if not match:
        return False
    major = int(match.group(1))
    minor = int(match.group(2))
    if (major, minor) < (REQUIRED_MAJOR, REQUIRED_MINOR):
        warn(
            f"Skipping {version_text!r}: requires Python "
            f"{REQUIRED_MAJOR}.{REQUIRED_MINOR}+."
        )
        return False
    return True


def check_python_version() -> str:
    info = sys.version_info
    version_str = f"Python {info.major}.{info.minor}.{info.micro}"
    if (info.major, info.minor) < (REQUIRED_MAJOR, REQUIRED_MINOR):
        fail(
            f"{version_str} is installed, but "
            f"Python {REQUIRED_MAJOR}.{REQUIRED_MINOR}+ is required.",
            "Install a newer Python from https://www.python.org/downloads/.",
        )
    return version_str


def remove_existing_venv() -> None:
    if not VENV_DIR.exists():
        return
    status(f"Existing virtual environment found at {VENV_DIR}.")
    status("Removing it so we can build a fresh one...")
    try:
        shutil.rmtree(VENV_DIR)
    except PermissionError as e:
        fail(
            f"Permission denied while removing {VENV_DIR}: {e}",
            "Close any process or editor that is using files inside .venv "
            "(including this script's own Python if running from inside it), "
            "then re-run install.py.",
        )
    except OSError as e:
        fail(
            f"Could not remove {VENV_DIR}: {e}",
            "Make sure no shells or tools have the folder open, then retry.",
        )
    ok(f"Removed {VENV_DIR}.")


def create_venv(python_cmd: str) -> None:
    status(f"Creating virtual environment at {VENV_DIR} ...")
    cmd = python_cmd.split() if " " in python_cmd else [python_cmd]
    try:
        result = subprocess.run(
            [*cmd, "-m", "venv", str(VENV_DIR)],
            check=False,
        )
    except FileNotFoundError:
        fail(
            f"Could not launch '{python_cmd}' to build the venv.",
            "Verify your Python installation and PATH.",
        )
    if result.returncode != 0:
        fail(
            f"'python -m venv' exited with code {result.returncode}.",
            "Check the messages above for the underlying error "
            "(disk space, permissions, antivirus interference, etc.).",
        )
    ok(f"Created virtual environment at {VENV_DIR}.")


def venv_python() -> Path:
    if os.name == "nt":
        candidate = VENV_DIR / "Scripts" / "python.exe"
    else:
        candidate = VENV_DIR / "bin" / "python"
    if not candidate.is_file():
        fail(
            f"Expected venv interpreter not found at {candidate}.",
            "The venv appears to be corrupted. Delete the .venv folder "
            "and re-run install.py.",
        )
    return candidate


def upgrade_pip(venv_py: Path) -> None:
    status("Upgrading pip inside the virtual environment...")
    try:
        result = subprocess.run(
            [str(venv_py), "-m", "pip", "install", "--upgrade", "pip"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        fail(
            f"Could not launch {venv_py} to upgrade pip.",
            "Re-create the virtual environment by deleting .venv and re-running.",
        )

    if result.returncode != 0:
        tail = "\n".join((result.stderr or "").splitlines()[-PIP_TAIL_LINES:])
        warn(
            f"'pip install --upgrade pip' failed (continuing anyway):\n{tail}"
        )
        return

    version_match = re.search(
        r"Successfully installed pip ([0-9.]+)",
        result.stdout or "",
    )
    if version_match:
        ok(f"pip upgraded to {version_match.group(1)}.")
    else:
        ok("pip is up to date.")


def install_dependency(venv_py: Path, dep: str) -> None:
    status(f"Installing {dep} ...")
    try:
        result = subprocess.run(
            [str(venv_py), "-m", "pip", "install", dep],
            check=False,
        )
    except FileNotFoundError:
        fail(
            f"Could not launch {venv_py} to install {dep}.",
            "Re-create the virtual environment by deleting .venv and re-running.",
        )
    if result.returncode != 0:
        fail(
            f"pip failed to install {dep} (exit code {result.returncode}).",
            "Common causes: no internet connection, corporate firewall, "
            "or an interrupted previous install. Re-run install.py to retry.",
        )
    ok(f"Installed {dep}.")


def verify_imports(venv_py: Path, deps: List[str]) -> None:
    status("Verifying that all modules can be imported...")
    module_map = {
        "PySide6": "PySide6",
        "pandas": "pandas",
        "numpy": "numpy",
        "Pillow": "PIL",
        "matplotlib": "matplotlib",
    }
    modules_to_check: List[str] = []
    for dep in deps:
        pkg = re.split(r"[<>=!~]", dep, 1)[0].strip()
        mod = module_map.get(pkg)
        if mod:
            modules_to_check.append(mod)

    if not modules_to_check:
        warn("No known modules to verify; skipping import check.")
        return

    code = (
        "import importlib, sys\n"
        "failed = []\n"
        "for m in " + repr(modules_to_check) + ":\n"
        "    try:\n"
        "        importlib.import_module(m)\n"
        "    except Exception as e:\n"
        "        failed.append((m, repr(e)))\n"
        "if failed:\n"
        "    for m, err in failed:\n"
        "        print(f'MISSING:{m}:{err}')\n"
        "    sys.exit(2)\n"
        "print('OK')\n"
    )

    try:
        result = subprocess.run(
            [str(venv_py), "-c", code],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        fail(
            f"Could not launch {venv_py} to verify modules.",
            "Re-create the virtual environment and re-run install.py.",
        )

    if result.returncode == 0 and "OK" in result.stdout:
        ok("All dependencies verified.")
        return

    missing_lines = [
        line for line in (result.stdout or "").splitlines()
        if line.startswith("MISSING:")
    ]
    if missing_lines:
        details = "\n  ".join(missing_lines)
        fail(
            "One or more modules failed to import after install:\n  " + details,
            "Re-run install.py to repair, or check for incompatible "
            "package versions in pyproject.toml.",
        )

    tail = (result.stderr or result.stdout or "").strip().splitlines()
    tail_text = "\n  ".join(tail[-PIP_TAIL_LINES:])
    fail(
        f"Import verification failed (exit code {result.returncode}).",
        "Details:\n  " + tail_text,
    )


def main() -> int:
    os.chdir(REPO_ROOT)
    banner("Mank Scourge of War Editor - Installer")
    print(
        "This will set up a Python virtual environment in .venv\\ and\n"
        "install all required dependencies.\n"
    )

    status(f"Running {check_python_version()}.")
    ok(f"Python version check passed (requires {REQUIRED_MAJOR}.{REQUIRED_MINOR}+).")

    python_cmd, _ = find_python()
    status(f"Using Python interpreter: {python_cmd}")

    deps = parse_dependencies(PYPROJECT)
    status(f"Found {len(deps)} dependencies in pyproject.toml:")
    for dep in deps:
        print(f"     - {dep}")

    remove_existing_venv()
    create_venv(python_cmd)
    venv_py = venv_python()
    upgrade_pip(venv_py)

    for dep in deps:
        install_dependency(venv_py, dep)

    verify_imports(venv_py, deps)

    print()
    banner("Installation complete")
    print(
        "The editor is ready to run. Double-click run.bat (or run it\n"
        "from a terminal) to start the application.\n"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[!] Installation cancelled by user.")
        sys.exit(130)
