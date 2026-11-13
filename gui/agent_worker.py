# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Monitor w osobnym wątku Qt: nie dotyka widgetów ani połączenia GUI SQLite."""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from ai_core.errors import TaskCancelled
from ai_core.hybrid import HybridAgent
from ai_core.hybrid_queue import MonitorJob


class SygnalyMonitora(QObject):
    etap = Signal(str)
    gotowe = Signal(object)
    blad = Signal(str)
    anulowano = Signal()


class ZadanieMonitora(QRunnable):
    def __init__(self, database_path: Path, model: str, job: MonitorJob,
                 locale: str = "pl", specialists: dict[str, str] | None = None):
        super().__init__()
        self.database_path = Path(database_path)
        self.model = model
        self.job = job
        self.locale = locale
        self.specialists = dict(specialists or {})
        self.sygnaly = SygnalyMonitora()
        self._lock = threading.RLock()
        self._cancelled = threading.Event()
        self._engine: HybridAgent | None = None

    def anuluj(self) -> None:
        self._cancelled.set()
        with self._lock:
            agent = self._engine
        if agent is not None:
            agent.cancel()

    @Slot()
    def run(self) -> None:
        if self._cancelled.is_set():
            self.sygnaly.anulowano.emit()
            return
        try:
            engine = HybridAgent(
                self.database_path, self.model, locale=self.locale,
                specialist_models=self.specialists,
            )
            with self._lock:
                self._engine = engine
                if self._cancelled.is_set():
                    engine.cancel()
            result = engine.run(
                self.job.mode, self.job.invoice_id,
                progress=self.sygnaly.etap.emit,
            )
            if self._cancelled.is_set():
                self.sygnaly.anulowano.emit()
            else:
                self.sygnaly.gotowe.emit(result)
        except TaskCancelled:
            self.sygnaly.anulowano.emit()
        except Exception:
            # Nie przekazuj treści dokumentów ani komunikatów SQL do dziennika.
            if self._cancelled.is_set():
                self.sygnaly.anulowano.emit()
            else:
                self.sygnaly.blad.emit("failed")
        finally:
            with self._lock:
                self._engine = None
