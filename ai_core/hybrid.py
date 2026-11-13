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
ADVISORY_ROLES = ("verifier", "financial_analyst", "cycle_analyst")


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
    specialists: tuple[dict, ...] = ()  # odrębne, zweryfikowane kontrole


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
        specialist_models: dict[str, str] | None = None,
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
        choices = specialist_models or {}
        if (not isinstance(choices, dict)
                or any(k not in {"extractor", *ADVISORY_ROLES}
                       or not isinstance(v, str) or len(v.strip()) > 120
                       for k, v in choices.items())):
            raise ValueError("Niepoprawna konfiguracja specjalistów")
        # Ekstrakcja PDF ma osobny worker. Agent używa tylko 3 ról
        # kontrolnych; brak przypisania zachowuje poprzedni tryb.
        self.specialist_models = {
            role: choices[role].strip() for role in ADVISORY_ROLES
            if choices.get(role)
        }
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
              tools: bool, role: str = "main",
              main_codes: tuple[str, ...] = ()) -> dict:
        if role not in {"main", *ADVISORY_ROLES}:
            raise ValueError("Nieznana rola kontrolna")
        scope = ("Wyłącznie faktura o identyfikatorze " + str(invoice_id)
                 if mode == "change" else "Wszystkie aktywne rachunki")
        if role == "main":
            instruction = (
                "Jako agent główny oceń stan płatności, należności i "
                "oczekiwanych dokumentów Świstaka, wyłącznie przez narzędzia. "
                "Nie zgaduj kwot, statusów ani dat. Propozycje tylko do "
                "przeglądu przez człowieka. " + scope + ". Nie zapisuj danych."
            )
        else:
            role_instructions = {
                "verifier": "Niezależnie sprawdź fakty i kody ustaleń "
                            "Agenta głównego przy użyciu narzędzi.",
                "financial_analyst": "Zbadaj wyłącznie należności, terminy "
                                     "i statusy płatności.",
                "cycle_analyst": "Zbadaj wyłącznie cykle, oczekiwane rachunki "
                                 "i kompletność dokumentów.",
            }
            instruction = (
                "Jako specjalista doradczy: " + role_instructions[role]
                + " Nie wykonuj zapisów i nie proponuj automatycznych zmian. "
                + scope + ". Zwróć osobny AnalysisResult."
            )
        allowed = (
            ["invoice.details", "payment.inspect", "date.evaluate"]
            if mode == "change" else
            ["invoice.search", "payment.inspect", "date.evaluate",
             "finance.aggregate", "plan.expected", "cycle.evaluate"]
        )
        if role == "financial_analyst":
            allowed = (["invoice.details", "payment.inspect", "date.evaluate"]
                       if mode == "change" else
                       ["invoice.search", "payment.inspect", "date.evaluate",
                        "finance.aggregate"])
        elif role == "cycle_analyst":
            allowed = ["plan.expected", "cycle.evaluate", "finance.aggregate"]
        elif role == "verifier":
            allowed = (["invoice.details", "payment.inspect", "date.evaluate"]
                       if mode == "change" else
                       ["invoice.search", "payment.inspect", "date.evaluate",
                        "cycle.evaluate"])
        return {
            "contract_version": "1.0",
            "task_id": uuid.uuid4().hex,
            "role": role,
            "instruction": instruction,
            "context": {
                "reference_date": self.reference_date,
                "scope_invoice_id": invoice_id,
                "mode": mode,
                # Wyłącznie kody uprzednio zweryfikowane przez gateway.
                "main_finding_codes": list(main_codes[:10]) if role == "verifier"
                                      else [],
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
                # Główna rola nie zastępuje milcząco niedostępnego
                # specjalisty. Jeżeli specjalista nie działa, pomijamy go.
                ModelBinding("ollama", self.model_id,
                             roles=frozenset({"main"})),
                {
                    role: ModelBinding("ollama", name,
                                       roles=frozenset({role}))
                    for role, name in self.specialist_models.items()
                },
            )
            task = self._task(mode, invoice_id, revision, tools=True)
            advisory: list[dict] = []
            with AgentOrchestrator(router, gateway=self.gateway) as runner:
                with self._lock:
                    self._orchestrator, self._task_id = runner, task["task_id"]
                try:
                    self._check()
                    response = runner.submit(task).result(timeout=35)
                    if response["status"] in ("completed", "partial"):
                        verified_codes = tuple(
                            item["code"] for item in response["findings"]
                            if item["verification"] == "verified"
                        )[:10]
                        for role in ADVISORY_ROLES:
                            if role not in self.specialist_models:
                                continue
                            self._check()
                            if self.gateway.revision() != revision:
                                raise InvalidResponse("Dane zmieniły się podczas analizy")
                            model_name = self.specialist_models[role]
                            entry = {"role": role, "model_id": model_name,
                                     "status": "unavailable",
                                     "findings": (), "uncertainties": ()}
                            if role == "cycle_analyst" and mode == "change":
                                entry["status"] = "scope"
                                advisory.append(entry)
                                continue
                            if progress:
                                progress("specialist")
                            try:
                                available = (
                                    provider.health_check(model_name, timeout=2.5)
                                    if isinstance(provider, OllamaProvider)
                                    else provider.health_check(model_name)
                                )
                                if not available:
                                    advisory.append(entry)
                                    continue
                                specialist_task = self._task(
                                    mode, invoice_id, revision, tools=True,
                                    role=role, main_codes=verified_codes,
                                )
                                with self._lock:
                                    self._task_id = specialist_task["task_id"]
                                result = runner.submit(specialist_task).result(timeout=35)
                                self._check()
                                if self.gateway.revision() != revision:
                                    raise InvalidResponse(
                                        "Dane zmieniły się podczas pracy specjalisty"
                                    )
                                if result["status"] in ("completed", "partial"):
                                    entry["status"] = "ready"
                                    # Ustalenia przeszły normalną walidację
                                    # AnalysisResult + Tool Gateway. Propozycji
                                    # działania specjalisty nie przekazujemy do UI.
                                    entry["findings"] = tuple(result["findings"][:8])
                                    entry["uncertainties"] = tuple(
                                        result["uncertainties"][:8]
                                    )
                                else:
                                    entry["status"] = "error"
                            except TaskCancelled:
                                raise
                            except InvalidResponse:
                                if self.gateway.revision() != revision:
                                    raise
                                entry["status"] = "error"
                            except Exception:
                                self._check()
                                if self.gateway.revision() != revision:
                                    raise InvalidResponse(
                                        "Dane zmieniły się podczas pracy specjalisty"
                                    )
                                entry["status"] = "error"
                            advisory.append(entry)
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
                specialists=tuple(advisory),
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
