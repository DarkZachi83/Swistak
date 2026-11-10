# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Praca PDF/OCR poza głównym wątkiem Qt; bez dostępu do elementów GUI."""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from uslugi.geometria import Zaznaczenie
from uslugi.odczyt_pdf import OdczytAnulowany, odczytaj_pdf


class SygnalyOdczytu(QObject):
    gotowe = Signal(object)
    blad = Signal(str)
    anulowano = Signal()


class ZadanieOdczytu(QRunnable):
    def __init__(self, sciezka: Path, obszar: Zaznaczenie | None = None):
        super().__init__()
        self.sciezka = Path(sciezka)
        self.obszar = obszar
        self.przerwij = threading.Event()
        self.sygnaly = SygnalyOdczytu()

    @Slot()
    def run(self) -> None:
        try:
            wynik = odczytaj_pdf(self.sciezka, self.obszar, przerwij=self.przerwij)
        except OdczytAnulowany:
            self.sygnaly.anulowano.emit()
        except Exception as blad:
            self.sygnaly.blad.emit(str(blad))
        else:
            self.sygnaly.gotowe.emit(wynik)
