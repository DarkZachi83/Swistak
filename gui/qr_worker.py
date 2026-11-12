# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""QRunnable dla lokalnego skanowania QR bez blokowania GUI."""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from uslugi.kody_qr import OdczytQRAnulowany, odczytaj_kody_qr


class SygnalyQR(QObject):
    gotowe = Signal(object)
    blad = Signal(str)
    anulowano = Signal()


class ZadanieQR(QRunnable):
    def __init__(self, sciezka: Path):
        super().__init__()
        self.sciezka = Path(sciezka)
        self.przerwij = threading.Event()
        self.sygnaly = SygnalyQR()

    @Slot()
    def run(self) -> None:
        try:
            wynik = odczytaj_kody_qr(self.sciezka, przerwij=self.przerwij)
        except OdczytQRAnulowany:
            self.sygnaly.anulowano.emit()
        except Exception as exc:
            self.sygnaly.blad.emit(str(exc))
        else:
            self.sygnaly.gotowe.emit(wynik)
