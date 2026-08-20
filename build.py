"""Build PokeTokenBar.exe with PyInstaller.

    python build.py

Produces `dist/PokeTokenBar.exe` — a single windowless executable with no
Python install required on the target machine.

The window/tray egg and the executable icon both come from
`poketokenbar/assets/egg.png`, which is bundled into the binary. Pokemon
*sprites* are still fetched from PokeAPI at runtime and cached under
%LOCALAPPDATA% -- only the egg ships inside the exe.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
ICON = BUILD / "egg.ico"


def make_icon() -> Path:
    """Build a multi-resolution .ico from the egg asset."""
    from poketokenbar.app import _draw_egg

    # Deliberately the drawn egg, not the PokeAPI sprite: the icon is compiled
    # into the binary, and no Pokemon artwork should be.
    BUILD.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    _draw_egg(256).save(ICON, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"icon      -> {ICON}")
    return ICON


def is_locked(path: Path) -> bool:
    """True if `path` exists but cannot be replaced (the app is running).

    Tested with an exclusive open rather than a rename: Windows lets you rename
    a running executable but not overwrite or delete it, so a rename probe
    reports "free" and the build then fails anyway.
    """
    if not path.exists():
        return False
    try:
        with open(path, "r+b"):
            pass
    except OSError:
        return True
    return False


def main() -> int:
    icon = make_icon()

    # Rebuilding while the app runs fails on Windows because the exe is locked.
    # Rather than demand it be closed (or kill it), write beside it.
    name = "PokeTokenBar"
    target = ROOT / "dist" / "PokeTokenBar.exe"
    if is_locked(target):
        name = "PokeTokenBar-new"
        print("note      -> PokeTokenBar.exe is running and locked;\n"
              "             building as PokeTokenBar-new.exe instead.")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",                      # no console window behind the tray
        "--name", name,
        "--icon", str(icon),
        # pystray and Pillow pick their backends at runtime, so PyInstaller's
        # static analysis misses them.
        "--hidden-import", "pystray._win32",
        "--hidden-import", "PIL._tkinter_finder",
        "--collect-submodules", "pystray",
        # Nothing here needs numpy/scipy/matplotlib; excluding them keeps the
        # binary from ballooning if they happen to be installed.
        "--exclude-module", "numpy",
        "--exclude-module", "scipy",
        "--exclude-module", "matplotlib",
        "--exclude-module", "pandas",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(BUILD / "work"),
        "--specpath", str(BUILD),
        str(ROOT / "run.pyw"),
    ]
    print("running   -> PyInstaller")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    exe = ROOT / "dist" / f"{name}.exe"
    if exe.exists():
        print(f"\nbuilt     -> {exe}  ({exe.stat().st_size / 1_048_576:.1f} MB)")
        if name != "PokeTokenBar":
            print("             close the running app, then replace "
                  "PokeTokenBar.exe with this file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
