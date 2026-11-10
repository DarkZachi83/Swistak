# Porównanie rasteryzacji: PDFium vs Poppler

**Status: eksperyment w gałęzi `experiment/pdfium-ocr`.**

## Cel

Wyznaczyć, czy skany rachunków można obsługiwać bez wymogu instalacji
systemowego Popplera. Wybrano `pypdfium2` z PDFium jako domyślny
rasteryzator, zachowując opcję uruchomienia Popplera w testach.

**Nie zmieniamy modelu działania LLM-first.** Rasteryzacja jedynie
tworzy obraz dla lokalnego Tesseract; interpretację rachunku wykonuje
Ollama i wybrany LLM, a użytkownik zatwierdza wynik.

## Dwie ścieżki techniczne

1. **Produkcyjna:** PDF → PDFium (pypdfium2) → obraz PIL → Tesseract
   `pol+eng` → tekst → Ollama → propozycja JSON.
2. **Tylko porównanie:** PDF → Poppler (pdftoppm + pdf2image) →
   obraz PIL → identyczny Tesseract → tekst.

Kod używa tych samych ustawień DPI, języka i PSM Tesseract w obu
wariantach. Do tekstowych PDF-ów nadal wykorzystywana jest warstwa
tekstowa przez pdfplumber — oba rasteryzatory nie są tam uruchamiane.

## Powtarzalny test

```bash
python -m pip install -r requirements-compare.txt
# Linux: sudo apt install tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng poppler-utils
python -m tools.porownaj_ocr --json raport_ocr.json
```

Narzędzie samodzielnie tworzy dwa fikcyjne dokumenty:

- `czytelny` — duża czcionka, tekst oraz numer konta testowego;
- `drobniejszy` — nieco mniejszy, szary tekst, dwie różne kwoty:
  brutto i do zapłaty.

To **PDF-y zawierające tylko obraz**, bez warstwy tekstowej. Każdy
silnik przetwarza dokładnie ten sam plik.

Raport zawiera czas w sekundach, przybliżone podobieństwo OCR do
tekstu wzorcowego, sprawdzenie obecności kwoty, terminu i **cyfr**
rachunku bankowego. Porównanie cyfr ignoruje odstępy, lecz
nie ignoruje ich zamiany lub utraty.

**UWAGA:** benchmark nie sprawdza poprawności interpretacji przez LLM,
nie mierzy wprost wartości biznesowej, nie daje gwarancji działania na
każdym skanie. Czas obejmuje otwarcie PDF, render, OCR i narzut Pythona,
a nie sam renderer. Wynik porównujemy na tej samej maszynie.

## Pierwszy test lokalny (środowisko pomocnicze, 10.11.2026)

| Przypadek | PDFium: podobieństwo | Poppler: podobieństwo | Pola łącznie |
|---|---:|---:|---|
| Czytelny | 100% | 100% | 3/3 dla obu |
| Drobniejszy | 100% | 100% | 3/3 dla obu |

W drugim przykładzie PDFium wykonał lokalną próbę nieco szybciej,
ale **to za mało pomiarów, aby deklarować przewagę wydajności**.
GitHub Actions zbierze powtarzalne wyniki z wersji Python 3.11 i 3.13.
Wyniki są załączane do przebiegów CI jako `raport-ocr-python-*`.

## Znane ograniczenia i dalsze testy

- Skany krzywe, zaszumione, obrócone, wielostronicowe, z polskimi
  znakami i ciasno rozłożonymi tabelami mogą dawać inne wyniki.
- Przed uznaniem PDFium za gotowy do dystrybucji trzeba przetestować
  **zaznaczanie obszaru** i ręczne porównanie OCR na komputerze autora.
- Modele binarne PDFium mają własne obowiązki licencyjne; obowiązuje
  [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md).
- Do komercyjnej paczki **nie** dołączamy opcjonalnego Popplera.

## Bezpieczeństwo wielowątkowości i czasu życia obiektów

Według dokumentacji **PDFium nie jest thread-safe**; równoległe wywołania
nawet na różnych dokumentach mogą uszkodzić pamięć lub zakończyć proces.

Moduł \`uslugi/rasteryzacja.py\` ma procesową blokadę \`RLock\` wokół
całego wywołania PDFium: inicjalizacji, otwarcia dokumentu, renderu,
kopiowania bitmapy do niezależnego obrazu PIL oraz zamknięcia
bitmapy, strony i dokumentu. Obraz PIL i Tesseract działają poza blokadą.

Dodany test testuje cztery symultaniczne zadania na sztucznym rendererze
i wymaga tylko jednej aktywnej sesji PDFium naraz. To **nie zastępuje**
testów stresowych z rzeczywistymi dokumentami.

**Ważne ograniczenie:** mutex chroni tylko odwołania pypdfium2 przez
nasz moduł; nie obejmuje innych bibliotek/instancji PDFium
(np. ewentualnego silnika QtPdf). Przed dystrybucją należy sprawdzić
współbieżność GUI (podgląd) i workerów OCR, a do równoległego renderingu
PDFium rozważyć izolowane procesy zamiast wątków.

Źródła: [threading](https://pypdfium2.readthedocs.io/en/stable/python_api.html#incompatibility-with-threading)
oraz [memory management](https://pypdfium2.readthedocs.io/en/stable/python_api.html#memory-management).
