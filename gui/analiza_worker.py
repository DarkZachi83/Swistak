# SPDX-License-Identifier: GPL-3.0-only
"""Asynchroniczna analiza przez lokalną Ollamę: żadnych zmian w bazie."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from uslugi.analiza_llm import analizuj_lokalnie


class SygnalyAnalizy(QObject):
    gotowe = Signal(int, object)  # dokument_id, AnalizaModelu
    blad = Signal(int, str)
    anulowano = Signal(int)


class ZadanieAnalizy(QRunnable):
    def __init__(self, dokument_id: int, tekst: str, kategorie: list[str], model: str):
        super().__init__()
        self.dokument_id = dokument_id
        self.tekst = tekst
        self.kategorie = list(kategorie)
        self.model = model
        self.przerwij = threading.Event()
        self.sygnaly = SygnalyAnalizy()

    @Slot()
    def run(self) -> None:
        if self.przerwij.is_set():
            self.sygnaly.anulowano.emit(self.dokument_id)
            return
        try:
            wynik = analizuj_lokalnie(self.tekst, self.kategorie, self.model)
        except Exception as blad:
            if self.przerwij.is_set():
                self.sygnaly.anulowano.emit(self.dokument_id)
            else:
                self.sygnaly.blad.emit(self.dokument_id, str(blad))
        else:
            if self.przerwij.is_set():
                self.sygnaly.anulowano.emit(self.dokument_id)
            else:
                self.sygnaly.gotowe.emit(self.dokument_id, wynik)
