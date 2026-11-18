# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Kolejka monitora Agenta i aktualizacja jego widoku w Qt."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal

from ai_core.hybrid import AgentLog, MonitorReport
from ai_core.hybrid_queue import MonitorJob, MonitorQueue
from gui.agent_worker import ZadanieMonitora
from gui.panel_agenta import PanelAgenta
from i18n import current_language


class MonitorAgenta(QObject):
    """Zarządza jedną kolejką Agenta w wątku GUI i aktualizuje jego panel."""

    status_zmieniony = Signal(str, object)

    def __init__(
        self, baza: Path, pobierz_ustawienia: Callable[[], tuple[str, dict[str, str]]],
        parent: QObject,
    ):
        super().__init__(parent)
        self._baza = baza
        self._pobierz_ustawienia = pobierz_ustawienia
        self._log = AgentLog()
        self._queue = MonitorQueue()
        self._task: ZadanieMonitora | None = None
        self._current_job: MonitorJob | None = None
        self.report: MonitorReport | None = None
        self._closed = False
        self._startup_scheduled = False
        self.status_key = "agent.state.waiting"
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.zlec("startup"))
        self.panel = PanelAgenta(embedded=True)
        self.panel.manualRequested.connect(lambda: self.zlec("manual"))
        self.panel.cancelRequested.connect(self.anuluj)
        self.odswiez_panel()

    @property
    def pracuje(self) -> bool:
        return self._task is not None

    def przerwij_tlo(self) -> None:
        if (self._task is not None and self._current_job is not None
                and self._current_job.mode != "manual"):
            self._task.anuluj()

    def zaplanuj_start(self) -> None:
        if not self._startup_scheduled and not self._closed:
            self._startup_scheduled = True
            # Po pokazaniu okna, nigdy nie blokuj jego inicjalizacji.
            self._timer.start(1200)

    def zamknij(self) -> None:
        self._closed = True
        self._timer.stop()
        self._queue.clear()
        if self._task is not None:
            self._task.anuluj()

    def _set_status(self, key: str) -> None:
        self.status_key = key
        self.status_zmieniony.emit(key, self.report)

    def odswiez_panel(self) -> None:
        self.panel.update_content(
            self.report, self._log.text(),
            self._task is not None,
        )

    def zlec(self, mode: str, invoice_id: int | None = None) -> None:
        if self._closed:
            return
        if mode == "manual":
            # Nie uruchamiaj ponownie kontroli startowej tuż po zakończeniu
            # pełnej analizy ręcznej.
            self._timer.stop()
        job = MonitorJob(mode, invoice_id)
        # Nawet jeśli użytkownik ręcznie uruchamia analizę, tylko jego
        # świadomy zapis formularza może zmieniać SQLite.
        if mode == "change":
            self.report = None
            self.status_zmieniony.emit(self.status_key, None)
            self.odswiez_panel()
        if self._current_job == job:
            return
        if self._queue.add(job):
            self._log.append(mode, "queued", invoice_id)
        if mode == "manual" and self._task is not None:
            # Ręczne polecenie ma pierwszeństwo przed długim LLM w tle.
            if self._current_job and self._current_job.mode != "manual":
                self._task.anuluj()
        self._dispatch()
        self.odswiez_panel()

    def _dispatch(self) -> None:
        if self._closed or self._task is not None:
            return
        job = self._queue.take()
        if job is None:
            self._set_status("agent.state.ready")
            self.odswiez_panel()
            return
        model, modele_specjalistyczne = self._pobierz_ustawienia()
        worker = ZadanieMonitora(
            self._baza, model, job, locale=current_language(),
            specialists=modele_specjalistyczne,
        )
        self._task = worker
        self._current_job = job
        self._log.append(job.mode, "started", job.invoice_id)
        self._set_status("agent.state.working")
        worker.sygnaly.etap.connect(self._progress)
        worker.sygnaly.gotowe.connect(self._completed)
        worker.sygnaly.blad.connect(self._error)
        worker.sygnaly.anulowano.connect(self._cancelled)
        QThreadPool.globalInstance().start(worker)

    def _progress(self, stage: str) -> None:
        if self._closed:
            return
        if stage in {"local", "health", "llm"}:
            job = self._current_job
            if job is not None:
                event = {
                    "local": "local_check",
                    "health": "model_check",
                    "llm": "model_run",
                }[stage]
                self._log.append(job.mode, event, job.invoice_id)
            self._set_status("agent.state." + stage)
            self.odswiez_panel()

    def _finish(self, state: str, report: MonitorReport | None = None) -> None:
        if self._closed:
            return
        job = self._current_job
        self._task = None
        self._current_job = None
        if job is not None:
            self._log.append(job.mode, state, job.invoice_id)
        if report is not None:
            self.report = report
        if state == "error":
            self._set_status("agent.state.error")
        elif state == "cancelled":
            self._set_status("agent.state.cancelled")
        elif report is not None:
            self._set_status({
                "local_only": "agent.state.offline",
                "model_idle": "agent.state.model_idle",
                "model_no_tools": "agent.state.model_no_tools",
                "model_ready": "agent.state.ready",
                "model_error": "agent.state.model_error",
            }[report.model_status])
        else:
            self._set_status("agent.state.ready")
        self.odswiez_panel()
        # Jedno zadanie na raz: następne startuje dopiero po zakończeniu
        # poprzedniego. Użytkownik może je anulować w dowolnym momencie.
        if len(self._queue):
            self._dispatch()

    def _completed(self, report: MonitorReport) -> None:
        event = {"model_ready": "ai_done", "local_only": "offline"}.get(
            report.model_status, report.model_status
        )
        self._finish(event, report)

    def _error(self, _code: str) -> None:
        self._finish("error")

    def _cancelled(self) -> None:
        self._finish("cancelled")

    def anuluj(self) -> None:
        self._queue.clear()
        if self._task is not None:
            self._task.anuluj()
        self.odswiez_panel()
