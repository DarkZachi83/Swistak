# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Świstak: wejście aplikacji i inicjalizacja prywatnej bazy rachunków."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from gui.motyw import ustaw_motyw
from gui.okno_glowne import OknoGlowne
from uslugi.rachunki import RejestrRachunkow


def main() -> int:
    aplikacja = QApplication(sys.argv)
    aplikacja.setApplicationName("Świstak")
    ustaw_motyw(aplikacja)
    try:
        rejestr = RejestrRachunkow()
    except Exception as blad:
        QMessageBox.critical(
            None, "Świstak — błąd bazy",
            f"Nie można otworzyć lokalnej bazy danych:\n{blad}\n"
            "Sprawdź uprawnienia i kopię zapasową. Program nie zmieni istniejących danych."
        )
        return 1
    try:
        okno = OknoGlowne(rejestr)
        okno.show()
        if len(sys.argv) > 1:
            okno.otworz_pdf(sys.argv[1])
        return aplikacja.exec()
    finally:
        rejestr.zamknij()


if __name__ == "__main__":
    raise SystemExit(main())
