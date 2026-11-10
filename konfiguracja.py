# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Lokalizacja prywatnych danych, niezależna od katalogu kodu."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def katalog_danych() -> Path:
    """Katalog użytkownika; SWISTAK_DATA_DIR pozwala go wybrać np. w testach."""
    wybrany = os.environ.get("SWISTAK_DATA_DIR")
    if wybrany:
        return Path(wybrany).expanduser().resolve()
    if sys.platform == "win32":
        baza = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return baza / "Swistak"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Swistak"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "Swistak"
