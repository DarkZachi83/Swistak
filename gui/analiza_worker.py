# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Asynchroniczna analiza przez lokalną Ollamę: żadnych zmian w bazie."""
from __future__ import annotations

import threading
import copy

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from uslugi.analiza_ai_core import analizuj_przez_ai_core


class SygnalyAnalizy(QObject):
    etap = Signal(int, str)  # prepare / ollama / validate
    gotowe = Signal(int, object)  # dokument_id, AnalizaModelu
    blad = Signal(int, str)
    anulowano = Signal(int)


class ZadanieAnalizy(QRunnable):
    def __init__(self, dokument_id: int, tekst: str, kategorie: list[str],
                 model: str, wzorzec: dict | None = None):
        super().__init__()
        self.dokument_id = dokument_id
        self.tekst = tekst
        self.kategorie = list(kategorie)
        self.model = model
        self.wzorzec = copy.deepcopy(wzorzec)
        self.przerwij = threading.Event()
        self._lock = threading.Lock()
        self._provider = None
        self._task_id = ""
        self.sygnaly = SygnalyAnalizy()

    def _podlacz_provider(self, provider, task_id: str) -> None:
        with self._lock:
            self._provider = provider if task_id else None
            self._task_id = task_id
            cancelled = self.przerwij.is_set()
        if cancelled and task_id:
            provider.cancel(task_id)

    def anuluj(self) -> None:
        """Best effort: przerwij sieć Ollamy oraz odrzuć spóźniony wynik."""
        self.przerwij.set()
        with self._lock:
            provider, task_id = self._provider, self._task_id
        if provider is not None and task_id:
            provider.cancel(task_id)

    @Slot()
    def run(self) -> None:
        if self.przerwij.is_set():
            self.sygnaly.anulowano.emit(self.dokument_id)
            return
        try:
            self.sygnaly.etap.emit(self.dokument_id, "prepare")
            wynik = analizuj_przez_ai_core(
                self.tekst, self.kategorie, self.model, wzorzec=self.wzorzec,
                postep=lambda etap: self.sygnaly.etap.emit(self.dokument_id, etap),
                przerwij=self.przerwij, podlacz_provider=self._podlacz_provider,
            )
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
