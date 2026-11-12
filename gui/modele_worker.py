# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Asynchroniczne wykrywanie lokalnych modeli bez blokowania GUI."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from uslugi.modele_lokalne import BladOllama, modele_na_dysku, modele_ollama


class SygnalyModeli(QObject):
    gotowe = Signal(object, object, str)


class ZadanieModeli(QRunnable):
    def __init__(self):
        super().__init__()
        self.przerwij = threading.Event()
        self.sygnaly = SygnalyModeli()

    @Slot()
    def run(self) -> None:
        names, error = [], ""
        try:
            names = modele_ollama()
        except BladOllama as exc:
            error = str(exc)
        if self.przerwij.is_set():
            return
        try:
            disk = modele_na_dysku(stop=self.przerwij)
        except OSError:
            disk = []
        if not self.przerwij.is_set():
            self.sygnaly.gotowe.emit(names, disk, error)
