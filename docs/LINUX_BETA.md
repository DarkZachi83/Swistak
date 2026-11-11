# Świstak Linux Beta — pakiet źródłowy do testów

**Status:** pakiet beta do wewnętrznych testów, bez oficjalnego tagu/release.

Wersja aplikacji: **0.1.0 Beta 1**. Nazwa archiwum:
`swistak-linux-0.1.0b1-source.tar.gz`.

## Dlaczego źródłowy, a nie od razu AppImage / samodzielny plik ELF?

Pakiet zawiera kod projektu, nie dołącza binarnych bibliotek PySide6/Qt,
PDFium, Tesseract ani modelu Ollama. To pozwala testować instalację,
zanim zakończymy audyt licencji i dystrybucji zależności binarnych.
**Nie jest to program działający bez Pythona i internetu podczas instalacji.**

## Wymagania

- Linux, Python **3.11+** wraz z modułem `venv` i `pip`;
- dostęp do indeksu pakietów podczas uruchamiania `instaluj.sh`;
- dla OCR skanów: systemowy **Tesseract** z językami `pol` i `eng`;
- opcjonalnie: osobno zainstalowana **Ollama** i model do analizy AI.

Dla Ubuntu/Debian:

```bash
sudo apt install python3-venv tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng
```

## Pierwsze uruchomienie

```bash
tar -xzf swistak-linux-0.1.0b1-source.tar.gz
cd Swistak-Linux-0.1.0b1
./instaluj.sh
./start.sh --test
```

`instaluj.sh` zakłada środowisko `.venv` **tylko w rozpakowanym katalogu**
i instaluje tam pakiety z `requirements.txt`. Nie wymaga uprawnień root.
Nie dotyka katalogu danych Świstaka.

`start.sh --test` korzysta z osobnej lokalizacji danych
`~/.local/share/Swistak-Test-<nazwa-katalogu>` (lub pod
`XDG_DATA_HOME`). Jest to preferowany tryb na czas beta-testów.

**Bez `--test` aplikacja używa zwykłej bazy użytkownika.** Przed takim
uruchomieniem zabezpiecz istniejące dane, ponieważ może być wymagana
migracja schematu.

```bash
./start.sh                # normalna prywatna baza
./start.sh --test          # bezpieczniejsza baza testowa
./start.sh --test plik.pdf # testowy dokument PDF
```

**Nie umieszczaj własnych dokumentów PDF w katalogu rozpakowanego pakietu.**
Program zapisuje je w oddzielnym prywatnym katalogu danych.

## Zbudowanie pakietu z repozytorium

```bash
python3 -m tools.build_linux_beta
```

Archiwum trafia do `dist/`. Budowanie korzysta wyłącznie ze standardowej
biblioteki Pythona i dołącza *wyłącznie* pliki jawnie wymienione w
skrypcie. Nie zbiera bazy, dokumentów użytkownika, `.venv`,
`.env` ani żadnych nieznanych plików.

Pakiet zawiera aktualną ilustrację **JPEG** Świstaka, migracje SQL,
tłumaczenia, kod GUI, aktualny tekst licencji i informacje o zależnościach.
Nie zmienia zawartości ani skrótów istniejących migracji SQL.

## Ograniczenia

- Testy funkcjonalne i bezpieczeństwa są niezbędne przed publikacją.
- Uruchomienie Tesseract / Ollama wymaga odrębnej instalacji usług.
- Brak automatycznego aktualizatora i wygodnego desktop installera.
- Pełna dystrybucja binarna (np. AppImage) wymaga osobnej analizy
  licencji PySide6/Qt, PDFium i pozostałych zależności.
