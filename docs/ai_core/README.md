# Świstak AI Core 1.0 — Etap 0

**Status:** specyfikacja AI Core 1.0 zaakceptowana przez autora 13.11.2026; dokumenty kontraktowe Etapu 0 są podstawą implementacji.  
**Źródło wymagań:** zatwierdzony dokument „Świstak AI Core 1.0 — Specyfikacja architektury i plan implementacji”.  
**Zakres Etapu 0:** wyłącznie kontrakty i testy bazowe — nie implementujemy jeszcze adaptera, orkiestratora, Tool Gateway ani migracji SQLite.

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
| 8 | Integracja, bezpieczeństwo, odbiór |

Zmiana kontraktu v1 po rozpoczęciu implementacji wymaga świadomego wersjonowania i testów kompatybilności. Dokumentacja nie oznacza, że opisywane funkcje już działają.

## Etap 1 — uruchamialny szkielet AI Core

[Ollama, router, orkiestrator, testy i kryteria odbioru](ETAP_1_OLLAMA.md).

Adaptery i orkiestrator znajdują się w `ai_core/`. Nie są jeszcze podłączone do GUI i nie mają dostępu do narzędzi bazy — ten dostęp powstanie w Etapie 2.
