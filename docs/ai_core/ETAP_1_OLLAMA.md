# Świstak AI Core — Etap 1: wykonanie i odbiór

**Cel:** pierwszy uruchamialny szkielet AI Core. Pierwszy adapter: Ollama, w architekturze pozwalającej zastąpić model i backend.

## Moduły
- `ai_core/provider.py`: protokół `LLMProvider` i zdarzenia strumienia.
- `ai_core/ollama.py`: lokalny adapter dla `/api/tags`, `/api/show`, `/api/chat`.
- `ai_core/router.py`: jedna rola główna i opcjonalni specjaliści, fallback do zgodnego modelu głównego.
- `ai_core/orchestrator.py`: kolejka na `ThreadPoolExecutor`, wykonywanie, anulowanie, odrzucanie spóźnionych wyników.
- `ai_core/contracts.py`: pełna walidacja JSON Schema v1 i blokada nieuprawnionego `verified`.
- `ai_core/errors.py`: standaryzowane błędy bez wycieku danych.

## Granica etapu
**Nie ma jeszcze Tool Gateway, integracji z GUI, migracji ani zapisu finansów.** Zadania z `allowed_tools` są odrzucane jawnie. Natywne `tool_calls` z Ollamy nie są wykonywane. Wnioski modelu bez narzędzi są oznaczane jako `unverified`, a model nie może sam nadać sobie potwierdzenia.

Przy połączeniu z prawdziwym modelem **pierwszy test ma być wykonywany wyłącznie na syntetycznych danych** i w odrębnym trybie, bez prywatnych faktur. Adapter nie instaluje modeli.

## Kompatybilność
- Nie zmieniono starej ścieżki importu `uslugi/analiza_llm.py`.
- Nie ma modyfikacji SQLite ani GUI.
- Wersja `TaskRequest` i `AnalysisResult`: `1.0`.
- Transport adaptera ograniczony do HTTP localhost/loopback, bez proxy i bez API zewnętrznych.
- `get_capabilities` zwraca deklarację możliwości oraz `verified=false`; faktyczny test zgodności ról jest osobnym zadaniem.
- W razie braku Ollamy podstawowe funkcje istniejącego programu pozostają bez zmian.

## Testy
```bash
python -m unittest testy.test_ai_core_contracts testy.test_ai_core_stage1 -v
```
Testy adaptera uruchamiają jedynie fikcyjny HTTP server na `127.0.0.1` i fikcyjne odpowiedzi zgodne z kontraktem. Nie wymagają Ollamy, GPU, PDF ani sieci zewnętrznej.

## Kryteria odbioru
- [x] Interfejs wymiennego dostawcy LLM i pełna walidacja v1.
- [x] Adapter Ollamy: lista modeli, health check, możliwości, generate, stream, cancel.
- [x] Router modelu głównego i specjalistów bez automatycznego zewnętrznego API.
- [x] Orkiestrator: kolejka, anulowanie, odrzucanie spóźnionych wyników.
- [x] Brak nieuprawnionego zapisu, Tool Gateway odroczony.
- [ ] Testy syntetyczne i pełna regresja zielone na Python 3.11 i 3.13.
- [ ] Odbiór użytkownika.

**Etap 2:** kontrolowane narzędzia do odczytu SQLite i innych usług, walidacja wywołań i łączenie dowodów.
