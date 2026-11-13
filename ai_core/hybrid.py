# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Etap 5 — lokalny monitor, dobrowolny LLM i jawne, ograniczone zadania.

Jedyna droga do danych: Tool Gateway + tylko-odczytowa sesja SQLite.
Wyniki monitora nie są poleceniem zapisu, nie uruchamiają płatności.
"""
from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from ai_core.errors import InvalidResponse, TaskCancelled
from ai_core.gateway import ToolGateway
from ai_core.ollama import OllamaProvider
from ai_core.orchestrator import AgentOrchestrator
from ai_core.router import ModelBinding, ModelRouter

WARSAW = ZoneInfo("Europe/Warsaw")
MODES = frozenset({"startup", "change", "manual"})


def today_warsaw() -> str:
    return datetime.now(WARSAW).date().isoformat()


@dataclass(frozen=True)
class MonitorReport:
    mode: str
    invoice_id: int | None
    reference_date: str
    data_revision: str
    summary: dict[str, int]
    model_status: str  # local_only | model_ready | model_error
    model_id: str | None = None
    findings: tuple[dict, ...] = ()
    proposals: tuple[dict, ...] = ()
    uncertainties: tuple[str, ...] = ()


class AgentLog:
    """Niewrażliwy dziennik bieżącej sesji, bez treści faktur/SQL/LLM."""

    def __init__(self, limit: int = 100):
        if not 1 <= limit <= 1000:
            raise ValueError("Nieprawidłowy limit logu")
        self._items: deque[str] = deque(maxlen=limit)
        self._lock = threading.RLock()

    def append(self, mode: str, event: str, invoice_id: int | None = None) -> None:
        if mode not in MODES or event not in {
            "queued", "started", "local_done", "ai_done", "offline",
            "cancelled", "error", "stale", "local_check",
            "model_check", "model_run",
        }:
            raise ValueError("Nieznane zdarzenie dziennika")
        stamp = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        scope = f" invoice_id={invoice_id}" if invoice_id is not None else ""
        with self._lock:
            self._items.append(f"{stamp} [{mode}] {event}{scope}")

    def text(self) -> str:
        with self._lock:
            return "\n".join(self._items)


class HybridAgent:
    """Jedno użycie per worker. Bez współdzielenia uchwytów SQLite z GUI."""

    def __init__(
        self, database_path: Path | str, model_id: str,
        *, provider_factory: Callable[[], OllamaProvider] | None = None,
        reference_date: str | None = None, locale: str = "pl",
    ):
        if not isinstance(model_id, str) or not 0 < len(model_id.strip()) <= 120:
            raise ValueError("Nieprawidłowy lokalny model")
        if locale not in {"pl", "en"}:
            raise ValueError("Nieznany język")
        self.gateway = ToolGateway(database_path)
        self.model_id = model_id.strip()
        self.locale = locale
        self.reference_date = reference_date or today_warsaw()
        # Data jest wyznaczana przez aplikację, nie przez model.
        from datetime import date
        date.fromisoformat(self.reference_date)
        self.provider_factory = provider_factory or (lambda: OllamaProvider(timeout=120))
        self._cancel = threading.Event()
        self._lock = threading.RLock()
        self._orchestrator: AgentOrchestrator | None = None
        self._task_id: str | None = None

    def cancel(self) -> None:
        self._cancel.set()
        with self._lock:
            runner, ident = self._orchestrator, self._task_id
        if runner is not None and ident is not None:
            runner.cancel(ident)

    def _check(self) -> None:
        if self._cancel.is_set():
            raise TaskCancelled("Anulowano pracę monitora")

    def _task(self, mode: str, invoice_id: int | None, revision: str, *,
              tools: bool) -> dict:
        role = "main"
        scope = ("Wyłącznie faktura o identyfikatorze " + str(invoice_id)
                 if mode == "change" else "Wszystkie aktywne rachunki")
        instruction = (
            "Sprawdź stan płatności, należności i oczekiwanych dokumentów "
            "Świstaka, używając wyłącznie przydzielonych narzędzi. "
            "Nie korzystaj z niezweryfikowanych faktów ani fikcyjnych dowodów. "
            "Zwróć AnalysisResult i zaproponuj działania tylko do przeglądu; "
            "każde działanie wymaga osobnej zgody użytkownika. "
            + scope + ". Nie wykonuj zapisów."
        )
        allowed = (
            ["invoice.details", "payment.inspect", "date.evaluate"]
            if mode == "change" else
            ["invoice.search", "payment.inspect", "date.evaluate",
             "finance.aggregate", "plan.expected", "cycle.evaluate"]
        )
        return {
            "contract_version": "1.0",
            "task_id": uuid.uuid4().hex,
            "role": role,
            "instruction": instruction,
            "context": {
                "reference_date": self.reference_date,
                "scope_invoice_id": invoice_id,
                "mode": mode,
            },
            "allowed_tools": allowed if tools else [],
            "response_schema": "AnalysisResult",
            "data_revision": revision,
            "locale": self.locale, "timezone": "Europe/Warsaw",
            "limits": {"max_steps": 8, "timeout_ms": 30000, "max_records": 50},
        }

    def _local_summary(self, task: dict, invoice_id: int | None) -> dict[str, int]:
        """Deterministyczny odczyt; nigdy nie zgadujemy terminów płatności."""
        with self.gateway.session(task) as session:
            where = "r.wycofano_utc IS NULL"
            params: tuple = ()
            if invoice_id is not None:
                where += " AND r.id=?"
                params = (invoice_id,)
            row = session.db.execute(
                "SELECT "
                "COUNT(*) AS invoices, "
                "COALESCE(SUM(CASE WHEN r.status='do_zaplaty' "
                "THEN r.kwota_grosze ELSE 0 END),0) AS unpaid_grosze, "
                "COALESCE(SUM(CASE WHEN r.status='do_zaplaty' "
                "AND r.termin_platnosci<? THEN 1 ELSE 0 END),0) AS overdue, "
                "COALESCE(SUM(CASE WHEN r.status='do_zaplaty' "
                "AND r.termin_platnosci>=? "
                "AND r.termin_platnosci<=date(?,'+7 days') THEN 1 ELSE 0 END),0) AS due_soon, "
                "COALESCE(SUM(CASE WHEN r.status='oplacony' "
                "AND r.data_oplacenia IS NULL THEN 1 ELSE 0 END),0) AS paid_without_date "
                "FROM rachunki r WHERE " + where,
                (self.reference_date,) * 3 + params,
            ).fetchone()
            if invoice_id is not None:
                # Nie mieszamy globalnych oczekiwań z analizą jednego rekordu.
                missing = 0
            else:
                missing = session.db.execute(
                    "SELECT COUNT(*) FROM oczekiwane_dokumenty o "
                    "JOIN profile_rachunkow p ON p.id=o.profil_id "
                    "WHERE p.aktywny=1 AND o.oczekiwany_od<=? "
                    "AND (o.wyjatek IS NULL OR o.wyjatek='niepewne') "
                    "AND NOT EXISTS (SELECT 1 FROM powiazania_oczekiwanych l "
                    "JOIN rachunki r ON r.id=l.rachunek_id "
                    "WHERE l.oczekiwany_id=o.id AND r.wycofano_utc IS NULL)",
                    (self.reference_date,),
                ).fetchone()[0]
            return {
                "invoices": int(row["invoices"]),
                "unpaid_grosze": int(row["unpaid_grosze"]),
                "overdue": int(row["overdue"]),
                "due_soon": int(row["due_soon"]),
                "paid_without_date": int(row["paid_without_date"]),
                "missing_expected": int(missing),
            }

    def run(
        self, mode: str, invoice_id: int | None = None,
        *, progress: Callable[[str], None] | None = None,
    ) -> MonitorReport:
        if mode not in MODES:
            raise ValueError("Nieznany tryb monitora")
        if mode == "change":
            if type(invoice_id) is not int or invoice_id <= 0:
                raise ValueError("Analiza zmiany wymaga identyfikatora faktury")
        elif invoice_id is not None:
            raise ValueError("Całościowa analiza nie przyjmuje identyfikatora faktury")
        self._check()
        revision = self.gateway.revision()
        local_task = self._task(mode, invoice_id, revision, tools=False)
        if progress:
            progress("local")
        summary = self._local_summary(local_task, invoice_id)
        self._check()
        if self.gateway.revision() != revision:
            raise InvalidResponse("Dane zmieniły się podczas kontroli")

        base = dict(
            mode=mode, invoice_id=invoice_id,
            reference_date=self.reference_date, data_revision=revision,
            summary=summary,
        )
        # Nie przesyłamy pustych rekordów do modelu. Brak Ollamy nie blokuje
        # deterministycznych sum i terminów.
        if not summary["invoices"] and not summary["missing_expected"]:
            return MonitorReport(**base, model_status="local_only")
        if progress:
            progress("health")
        try:
            provider = self.provider_factory()
            self._check()
            if isinstance(provider, OllamaProvider):
                # Test dostępności 2,5 s; generowanie zachowuje swój budżet.
                available = provider.health_check(self.model_id, timeout=2.5)
            else:
                available = provider.health_check(self.model_id)
            if not available:
                return MonitorReport(**base, model_status="local_only")
            self._check()
            if progress:
                progress("llm")
            router = ModelRouter(
                {"ollama": provider},
                ModelBinding("ollama", self.model_id),
            )
            task = self._task(mode, invoice_id, revision, tools=True)
            with AgentOrchestrator(router, gateway=self.gateway) as runner:
                with self._lock:
                    self._orchestrator, self._task_id = runner, task["task_id"]
                try:
                    self._check()
                    response = runner.submit(task).result(timeout=35)
                finally:
                    with self._lock:
                        self._orchestrator = None
                        self._task_id = None
            self._check()
            if self.gateway.revision() != revision:
                raise InvalidResponse("Dane zmieniły się podczas analizy AI")
            return MonitorReport(
                **base,
                model_status=(
                    "model_ready" if response["status"] in ("completed", "partial")
                    else "model_error"
                ),
                model_id=self.model_id,
                findings=tuple(response["findings"][:20]),
                proposals=tuple(response["proposed_actions"][:20]),
                uncertainties=tuple(response["uncertainties"][:20]),
            )
        except TaskCancelled:
            raise
        except InvalidResponse as exc:
            # Stare ustalenia nigdy nie wracają jako aktualne.
            if self.gateway.revision() != revision:
                raise
            return MonitorReport(**base, model_status="model_error")
        except Exception:
            self._check()
            if self.gateway.revision() != revision:
                raise InvalidResponse("Dane zmieniły się podczas analizy")
            return MonitorReport(**base, model_status="model_error")
