"""Windowless launcher — double-click this, or point a Startup shortcut at it.

The .pyw extension makes Windows run it with pythonw.exe, so no console window
appears behind the tray icon.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from poketokenbar.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
