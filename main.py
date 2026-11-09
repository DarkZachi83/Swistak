# SPDX-License-Identifier: GPL-3.0-only
"""Punkt wejścia prototypu Świstaka."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from gui.motyw import ustaw_motyw
from gui.okno_glowne import OknoGlowne


def main() -> int:
    aplikacja = QApplication(sys.argv)
    aplikacja.setApplicationName("Świstak")
    ustaw_motyw(aplikacja)
    okno = OknoGlowne()
    okno.show()
    if len(sys.argv) > 1:
        okno.otworz_pdf(sys.argv[1])
    return aplikacja.exec()


if __name__ == "__main__":
    raise SystemExit(main())
