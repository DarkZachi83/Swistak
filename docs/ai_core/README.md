# Świstak AI Core 1.0 — architektura i zrealizowane etapy 0–8

**Stan na 14.11.2026:** implementacja AI Core 1.0 i automatyczna regresja
zakończone, pozostaje lokalny odbiór na Pythonie 3.14.10 i realnej Ollamie.
Kontrakty v1 zatwierdzono 13.11.2026. Ten katalog dokumentuje zarówno
oryginalne kontrakty, jak i ich implementację, a nie wyłącznie przyszły plan.

**Zamknięcie AI Core:** [Etap 8 — audyt, integracja i wydanie](ETAP_8_ZAMKNIECIE.md).  
**Dalszy rozwój:** [Plan głównego menu i statystyk](../PLAN_ROZWOJU_GUI.md).


## Gdzie czego szukać

- [Kontrakty techniczne i reguły](KONTRAKTY_V1.md) — semantyka, granice uprawnień, obsługa błędów i kryteria zgodności.
- [JSON Schema v1](contracts_v1.schema.json) — formalne koperty: `TaskRequest`, `ToolCall`, `ToolResult`, `AnalysisResult`, `ModelProfile`.
- [Katalog narzędzi v1](tools_v1.json) — 12 kontrolowanych operacji odczytowych.
- [Przykłady syntetyczne](../../testy/dane_syntetyczne/ai_core_v1.json) — przykłady wiadomości, faktur, dat i oczekiwanych wyników.
- [Testy kontraktów](../../testy/test_ai_core_contracts.py) — testy formatu i podstawowych niezmienników; nie wymagają Ollamy.
- [Plan odbioru Etapu 0](ETAP_0_ODBIOR.md).

## Zasady nienaruszalne

1. **LLM-first:** model główny planuje analizę i dobiera narzędzia; modele specjalistyczne są opcjonalne.
2. **Model-independent:** domena, SQLite i PySide6 nie importują konkretnego adaptera modelu.
3. **Local-first:** Ollama jest pierwszym adapterem; połączenia sieciowe wymagają osobnego projektowania i zgody.
4. **Human-in-control:** `proposed_actions` nigdy nie wykonują zapisu; decyzje finansowe zatwierdza użytkownik.
5. **Verifiable:** wyniki dotyczące kwot, terminów i statusów pochodzą z narzędzi deterministycznych i SQLite.
6. **Graceful degradation:** brak modelu nie blokuje podstawowego rejestru, PDF i obsługi ręcznej.
7. **Privacy:** do repozytorium trafiają wyłącznie fikcyjne przykłady.

## Etapy AI Core (odrębne od historycznych etapów importu)

| Etap | Zakres |
|---|---|
| **0** | Kontrakty i testy bazowe |
| 1 | Orkiestrator, router modeli, adapter Ollamy |
| 2 | Tool Gateway i walidacja wywołań |
| 3 | Model finansowy, SQLite, dziennik |
| 4 | Integracja importu z AI Core |
| 5 | Agent hybrydowy i Pulpit |
| 6 | Plan rachunków i Historia |
| 7 | Modele specjalistyczne |
| **8** | **Integracja, bezpieczeństwo, odbiór — zakończone w kodzie/CI** |

Zmiana kontraktu v1 po rozpoczęciu implementacji wymaga świadomego wersjonowania i testów kompatybilności. Dokumentacja nie oznacza, że opisywane funkcje już działają.

## Etap 8 — zamknięcie AI Core 1.0

[Audyt, paczki Linux, end-to-end, testy i kryteria odbioru](ETAP_8_ZAMKNIECIE.md).

## Etap 7 — opcjonalne modele specjalistyczne

[Konfiguracja ról, bezpieczeństwo, fallback i odbiór](ETAP_7_SPECJALISCI.md).

## Etap 6 — Plan rachunków i Historia

[Obsługa profili, miesięczna Historia, płatności i potwierdzanie kompletności](ETAP_6_PLAN_HISTORIA.md).

## Etap 5 — agent hybrydowy i Panel Agenta

[Tryby monitoringu, dziennik pracy i kryteria odbioru](ETAP_5_AGENT_HYBRYDOWY.md).

## Etap 4 — połączenie importu PDF/OCR/QR i W1–W4 z AI Core

[Model Router, lokalna ekstrakcja, walidacja i odbiór etapu 4](ETAP_4_INTEGRACJA.md).

## Etap 3 — model finansowy, Plan rachunków i Historia

[Dokumentacja migracji, operacji finansowych i kryteria odbioru](ETAP_3_FINANSE.md).

## Etap 2 — narzędzia kontrolowanego odczytu

[Tool Gateway, dostęp do SQLite i weryfikacja dowodów](ETAP_2_TOOL_GATEWAY.md).

## Etap 1 — uruchamialny szkielet AI Core

[Ollama, router, orkiestrator, testy i kryteria odbioru](ETAP_1_OLLAMA.md).

Adaptery i orkiestrator znajdują się w `ai_core/` i są podłączone do GUI.
Tool Gateway od etapu 2 udostępnia wyłącznie kontrolowane narzędzia odczytu.
AI Core 1.0 działa również w trybie bez Ollamy; zmiany finansowe wykonują
tylko istniejące usługi po świadomym działaniu użytkownika.
