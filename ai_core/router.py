# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Wybór głównego LLM i opcjonalnych modeli wyspecjalizowanych."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .errors import ModelUnavailable
from .provider import LLMProvider

ROLES = frozenset({"main", "extractor", "verifier", "financial_analyst", "cycle_analyst"})


@dataclass(frozen=True)
class ModelBinding:
    provider_id: str
    model_id: str
    # Kompetencje deklarowane przez konfigurację; testy zgodności modeli
    # i ich faktycznych zdolności będą wykonywane w dalszych etapach.
    roles: frozenset[str] = field(default_factory=lambda: ROLES)

    def __post_init__(self) -> None:
        if not self.provider_id or not self.model_id or not self.roles or not self.roles <= ROLES:
            raise ValueError("Nieprawidłowe przypisanie modelu lub ról")


class ModelRouter:
    def __init__(
        self,
        providers: Mapping[str, LLMProvider],
        main: ModelBinding,
        specialists: Mapping[str, ModelBinding] | None = None,
    ):
        self.providers = dict(providers)
        self.main = main
        self.specialists = dict(specialists or {})
        if "main" not in main.roles:
            raise ValueError("Model główny musi obsługiwać rolę main")
        for role, binding in self.specialists.items():
            if role not in ROLES - {"main"} or role not in binding.roles:
                raise ValueError("Nieprawidłowa rola modelu specjalistycznego")
        for binding in [main, *self.specialists.values()]:
            provider = self.providers.get(binding.provider_id)
            if provider is None:
                raise ValueError("Nieznany adapter modelu: " + binding.provider_id)
            if not provider.is_local:
                # Zewnętrzne API wymagają osobnej akceptacji w przyszłej wersji.
                raise ValueError("AI Core 1.0 dopuszcza wyłącznie lokalne adaptery")

    def select(self, role: str) -> tuple[LLMProvider, ModelBinding]:
        if role not in ROLES:
            raise ValueError("Nieznana rola agenta")
        binding = self.specialists.get(role)
        if binding is None:
            if role not in self.main.roles:
                raise ModelUnavailable("Brak zgodnego modelu dla roli: " + role)
            binding = self.main
        return self.providers[binding.provider_id], binding

    def fallback_main(self, role: str) -> tuple[LLMProvider, ModelBinding] | None:
        if role not in self.main.roles or role not in self.specialists:
            return None
        return self.providers[self.main.provider_id], self.main
