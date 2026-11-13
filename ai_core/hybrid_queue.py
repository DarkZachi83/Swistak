# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Deterministyczna kolejka Etapu 5: ręczne zadania mają pierwszeństwo."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MonitorJob:
    mode: str
    invoice_id: int | None = None

    def __post_init__(self):
        if self.mode not in {"startup", "change", "manual"}:
            raise ValueError("Nieznany tryb zadania")
        if self.mode == "change":
            if type(self.invoice_id) is not int or self.invoice_id <= 0:
                raise ValueError("Brak poprawnego numeru faktury")
        elif self.invoice_id is not None:
            raise ValueError("Tryb całościowy nie przyjmuje identyfikatora faktury")


class MonitorQueue:
    """Lista w pamięci sesji, bez logowania prywatnych danych faktury."""

    def __init__(self, limit: int = 16):
        if not 1 <= limit <= 100:
            raise ValueError("Nieprawidłowy limit kolejki")
        self.limit = limit
        self._jobs: list[MonitorJob] = []

    def add(self, job: MonitorJob) -> bool:
        if job in self._jobs:
            return False
        if job.mode == "manual":
            # Zastępuje starszą analizę pełną ze startu, ale zachowuje
            # analizy pojedynczych faktur zapisanych przez użytkownika.
            self._jobs = [x for x in self._jobs if x.mode not in {"startup", "manual"}]
            self._jobs.insert(0, job)
        elif job.mode == "startup":
            if any(x.mode in {"manual", "startup"} for x in self._jobs):
                return False
            self._jobs.append(job)
        else:
            # Gdy bufor się zapełnia, preferuj ostatnie zmiany faktur.
            self._jobs.append(job)
        if len(self._jobs) > self.limit:
            # Usuwamy najstarszą pracę automatyczną, nie ręczną.
            index = next((i for i in range(len(self._jobs) - 1, -1, -1)
                          if self._jobs[i].mode != "manual"), None)
            if index is not None:
                self._jobs.pop(index)
        return True

    def take(self) -> MonitorJob | None:
        return self._jobs.pop(0) if self._jobs else None

    def clear(self) -> None:
        self._jobs.clear()

    def __len__(self) -> int:
        return len(self._jobs)
