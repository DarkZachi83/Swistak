# Świstak AI Core — Etap 4: połączenie ekstrakcji PDF/OCR, QR i W1–W4

**Zakres:** wymiana transportu analizy dokumentu na AI Core, bez naruszania ręcznej akceptacji.  
**Status:** wdrożenie na `main`, oczekuje na lokalny odbiór użytkownika.

## Zmiana architektury

Ścieżka uruchamiana w GUI po kliknięciu „Analizuj”:

```text
PDF/skan → istniejący lokalny OCR → ręczna edycja tekstu
    → dopasowanie zatwierdzonego wzorca W1–W4
    → ZadanieAnalizy (wątek Qt, anulowanie)
    → ModelRouter (rola extractor)
    → OllamaProvider.generate_structured
    → JSON Schema pól + deterministyczna kontrola dat/kwot/dowodów
    → tabela sugestii i formularz edycji
    → OSOBNA zgoda użytkownika na przeniesienie
    → OSOBNY zapis do SQLite
```

Wszystkie dane dokumentów przekazywane są wyłącznie do lokalnego API HTTP
Ollamy na adresie loopback; połączenie jest bez proxy. Model nie wykonuje
`tool_calls` podczas ekstrakcji, nie ma dostępu do swobodnego SQL
i nie zapisuje żadnych operacji finansowych.

Moduły:
- `uslugi/analiza_ai_core.py`: integracja ról i wyników faktury, wymienny provider,
  ochrona przed anulowanymi/spóźnionymi wynikami;
- `ai_core/ollama.py`: metoda `generate_structured`, ścisły JSON Schema i limit czasu;
- `gui/analiza_worker.py`: dotychczasowy wątek Qt teraz korzysta z AI Core
  i może przerwać aktywne żądanie sieciowe;
- `uslugi/analiza_llm.py`: jedna definicja promptu i schematu ekstrakcji
  wykorzystywana przez starą ścieżkę zgodności i nowy provider.

## Wymienne modele

Domyślnie używany jest model wybrany w ustawieniu `ollama_model`
(domyślnie `gemma3:4b`). `ModelRouter` może dodatkowo wybrać
`extractor` przez parametr `model_ekstrakcji`, **jeśli** taki lokalny
model został skonfigurowany przez kod integracyjny. Gdy specjalista nie
odpowiada, aplikacja wraca do zgodnego modelu głównego.

**Nie ma jeszcze nowego selektora roli `extractor` w GUI.**
To osobna funkcja panelu ustawień AI Core w kolejnych etapach;
nie należy przedstawiać jej jako już dostępnego przełącznika.

## Wzorce W1–W4

- W1: zapis po zatwierdzeniu faktury i osobnym zaakceptowaniu wzorca.
- W2: wersjonowanie i aktualizacja wzorca po świadomej akceptacji.
- W3: dopasowanie po cechach sprzedawcy/układu, bez wykorzystywania NIP nabywcy.
- W4: zastosowanie zatwierdzonych wskazówek *przed* interpretacją modelu.

Prompt wzorca nie zawiera historycznych kwot, dat, numerów kont ani danych
nabywcy. Wszystkie dane muszą wynikać z aktualnego dokumentu i przejść
`ocena_json`, w tym kontrolę kalendarzowego okresu MM/RRRR.

## QR

Odczyt QR zachowuje dotychczasowy mechanizm: osobny lokalny dialog
i świadoma zgoda użytkownika na przeniesienie **tylko** kwoty i numeru
konta do edytowanego formularza. QR nie jest dodawany bez wiedzy użytkownika
do kontekstu LLM i nie inicjuje płatności. W etapie 4 nie wprowadzamy
automatycznego łączenia pól QR z odpowiedzią modelu.

## Granice i kryteria

- [x] GUI korzysta z nowego `ModelRouter` i `OllamaProvider` podczas analizy.
- [x] Zachowana wspólna definicja schematu pól i zasad dowodowych.
- [x] W1–W4 zachowane, oddzielna zgoda na każdą aktualizację wzorca.
- [x] PDF/OCR i QR nadal wyłącznie lokalne; brak automatycznego zapisu.
- [x] Anulowanie żądania Ollamy na poziomie workera i odrzucanie spóźnionego wyniku.
- [x] Syntetyczne testy wymiany modeli, specjalisty, błędnego JSON,
      niedozwolonych narzędzi, W1–W4, QR i anulowania.
- [ ] Końcowe testy GitHub Actions Python 3.11 i 3.13.
- [ ] Test lokalny Python 3.14.10 użytkownika.
- [ ] Odbiór użytkownika i dopiero potem Etap 5.

## Uruchomienie testów

```bash
python -m unittest testy.test_ai_core_stage4 -v
python -m unittest discover -s testy -v
```

Testy HTTP korzystają z lokalnego syntetycznego symulatora Ollamy
na `127.0.0.1`, bez prawdziwej faktury i bez instalowania modelu.

**Test z rzeczywistym modelem** nie był częścią CI. Pozostaje do wykonania
na komputerze użytkownika w trybie ręcznym z fikcyjną fakturą.

**Etap 5 (po odbiorze):** agent hybrydowy, panel stanu i analizy
uruchamiane po zmianach oraz przy starcie aplikacji.
