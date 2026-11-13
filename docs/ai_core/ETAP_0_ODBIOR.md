# AI Core — odbiór Etapu 0

**Zatwierdzona specyfikacja bazowa:** Świstak AI Core 1.0 (13.11.2026).  
**Etap 0:** kontrakty, dokumentacja i testy syntetyczne. **Nie ma implementacji agenta ani migracji.**

## Lista weryfikacyjna

- [x] Sprawdzono aktualny układ repozytorium i dotychczasowy plan etapów.
- [x] Ustalono wersję kontraktu `1.0` i zdefiniowano koperty w JSON Schema.
- [x] Opisano semantykę `LLMProvider` i pięć ról modeli.
- [x] Zdefiniowano katalog 12 kontrolowanych narzędzi v1.
- [x] Oddzielono proponowane akcje od wykonywania operacji finansowych.
- [x] Przygotowano syntetyczne faktury i oczekiwane wyniki.
- [x] Dodano automatyczne testy formatu i niezmienników.
- [ ] Potwierdzono wynik nowych testów w CI dla Python 3.11 i 3.13.
- [ ] Zatwierdzono odbiór Etapu 0 przez użytkownika.

## Testy

```bash
python -m unittest testy.test_ai_core_contracts -v
python -m unittest discover -s testy -v
```

Pierwsze polecenie nie potrzebuje PySide6, Ollamy ani dostępu do sieci. Drugie jest pełnym testem regresyjnym i może wymagać zależności repozytorium.

## Ograniczenia obecnych testów

Testy w Etapie 0 sprawdzają schematy, przykłady i reguły liczenia fikcyjnych danych. Nie zastępują jeszcze pełnego walidatora JSON Schema w aplikacji, testów modelu ani zdalnego integracyjnego testu Ollamy. Tę funkcjonalność przewidziano w Etapach 1–2.

## Definicja zakończenia

Po zielonym CI (lub jawnie udokumentowanym braku jego uruchomienia), weryfikacji zmian na `main` i akceptacji użytkownika oznaczamy Etap 0 jako zakończony. Nie rozpoczynamy Etapu 1 automatycznie.
