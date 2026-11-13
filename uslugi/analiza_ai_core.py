# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Etap 4: PDF/OCR → ModelRouter/LLMProvider → walidacja → edycja.

Nie czyta prywatnych dokumentów z repozytorium ani nie zapisuje SQLite.
Zachowuje W1–W4, reguły dat, dowody tekstowe i świadomą akceptację GUI.
"""
from __future__ import annotations

import threading
import uuid
from typing import Callable

from ai_core.errors import ModelUnavailable, TaskCancelled
from ai_core.ollama import OllamaProvider
from ai_core.router import ModelBinding, ModelRouter
from uslugi.analiza_llm import (
    AnalizaModelu, OcenaPola, ocena_json, przygotuj_zapytanie,
)
from uslugi.okres_rozliczeniowy import popraw_okres_modelu


def analizuj_przez_ai_core(
    tekst: str, kategorie: list[str], model: str = "gemma3:4b",
    timeout: int = 180, *, wzorzec: dict | None = None,
    model_ekstrakcji: str | None = None,
    postep: Callable[[str], None] | None = None,
    przerwij: threading.Event | None = None,
    podlacz_provider: Callable[[OllamaProvider, str], None] | None = None,
    provider: OllamaProvider | None = None,
) -> AnalizaModelu:
    """Ekstrakcja przez wymienny interfejs AI Core, bez Tool Gateway.

    Model ekstrakcji jest opcjonalny. Gdy go nie ma, używany jest model
    główny. Wybrany model musi należeć do lokalnego adaptera.
    """
    if not isinstance(tekst, str) or not tekst.strip():
        raise ValueError("Najpierw odczytaj tekst dokumentu")
    if len(tekst) > 30000:
        raise ValueError("Tekst przekracza 30 000 znaków")
    if not isinstance(model, str) or not 0 < len(model.strip()) <= 120:
        raise ValueError("Wybierz lokalny model Ollama")
    if model_ekstrakcji is not None and (
        not isinstance(model_ekstrakcji, str)
        or not 0 < len(model_ekstrakcji.strip()) <= 120
    ):
        raise ValueError("Niepoprawny model ekstrakcji")
    if przerwij is not None and przerwij.is_set():
        raise TaskCancelled("Anulowano analizę")

    adapter = provider if provider is not None else OllamaProvider(timeout=timeout)
    primary = ModelBinding(
        "ollama", model.strip(), roles=frozenset({"main", "extractor"})
    )
    specialists = (
        {"extractor": ModelBinding(
            "ollama", model_ekstrakcji.strip(), roles=frozenset({"extractor"})
        )} if model_ekstrakcji else None
    )
    router = ModelRouter({"ollama": adapter}, primary, specialists)
    active_provider, binding = router.select("extractor")
    # Model może być zmieniony przed analizą; instrukcja powstaje z aktualnych
    # danych, nigdy nie przechowuje poprzedniej faktury.
    request = przygotuj_zapytanie(tekst, list(kategorie), binding.model_id, wzorzec)
    task_id = "extract:" + uuid.uuid4().hex
    if podlacz_provider is not None:
        podlacz_provider(active_provider, task_id)
    if przerwij is not None and przerwij.is_set():
        active_provider.cancel(task_id)
        raise TaskCancelled("Anulowano analizę")
    if postep is not None:
        postep("ollama")
    try:
        # Jeśli opcjonalny specjalista jest niedostępny, odtwórz identyczny
        # prompt z nowym modelem; bez wycieku do chmury.
        try:
            values = active_provider.generate_structured(
                task_id=task_id, model_id=binding.model_id,
                messages=request["messages"], schema=request["format"],
                timeout=timeout,
            )
        except ModelUnavailable:
            fallback = router.fallback_main("extractor")
            if fallback is None:
                raise
            active_provider, binding = fallback
            request = przygotuj_zapytanie(tekst, list(kategorie), binding.model_id, wzorzec)
            # Po nieudanej próbie odśwież token i kontrolę anulowania.
            task_id = "extract:" + uuid.uuid4().hex
            if podlacz_provider is not None:
                podlacz_provider(active_provider, task_id)
            if przerwij is not None and przerwij.is_set():
                active_provider.cancel(task_id)
                raise TaskCancelled("Anulowano analizę")
            values = active_provider.generate_structured(
                task_id=task_id, model_id=binding.model_id,
                messages=request["messages"], schema=request["format"],
                timeout=timeout,
            )
        if przerwij is not None and przerwij.is_set():
            raise TaskCancelled("Anulowano analizę")
        if postep is not None:
            postep("validate")
        values, changed = popraw_okres_modelu(values, tekst)
        scores = ocena_json(values, tekst, list(kategorie))
        for field in changed:
            previous = scores[field]
            if previous.poprawne:
                scores[field] = OcenaPola(
                    previous.wartosc, previous.dowod, True,
                    "Okres wyliczony z miesiąca rozliczeniowego w PDF — sprawdź",
                )
        if przerwij is not None and przerwij.is_set():
            raise TaskCancelled("Anulowano analizę")
        return AnalizaModelu(binding.model_id, scores)
    finally:
        if podlacz_provider is not None:
            podlacz_provider(active_provider, "")
