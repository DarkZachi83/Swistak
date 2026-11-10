# Świstak

**Świstak** — lokalna aplikacja do prowadzenia rejestru domowych rachunków.
Kod jest publiczny, ale **dokumenty finansowe oraz baza są prywatne i nie
są przechowywane w repozytorium GitHub**.

> **Etap 3 (gałąź robocza)**: analiza odczytanego PDF przez lokalną Ollamę
> (`gemma3:4b`), propozycje JSON, podgląd dowodów i ostrzeżeń, przenoszenie
> wybranych przez użytkownika sugestii do formularza oraz osobny zapis.
> Numer konta bankowego jest przechowywany oddzielnie od numeru faktury.

## Instalacja i uruchomienie

Python 3.11+; Linux lub Windows z dostępem do PySide6.

```bash
git clone https://github.com/DarkZachi83/Swistak.git
cd Swistak
git switch feature/etap-3-ollama-formularz
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Windows: aktywacja środowiska przez `.venv\Scripts\activate`.
Można otworzyć wskazany PDF od razu: `python main.py /sciezka/do/rachunku.pdf`.

### Lokalne narzędzia OCR (Etap 2)

Python instaluje biblioteki `pdfplumber`, `pdf2image` i `pytesseract`,
ale skany wymagają dodatkowo **Popplera** i **Tesseract OCR** z językiem
`pol` (oraz opcjonalnie `eng`). Na Ubuntu/Debian:

```bash
sudo apt install poppler-utils tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng
```

W innych dystrybucjach zainstaluj odpowiednie pakiety systemowe.
Windows: doinstaluj Poppler i Tesseract oraz udostępnij ich programy
w zmiennej `PATH`.

Po imporcie dokumentu wybierz zakładkę **Odczyt PDF**. Przycisk
**Odczytaj cały PDF** pobiera tekst ze wszystkich stron (do 50),
wykorzystując OCR tylko tam, gdzie warstwa tekstowa jest pusta albo
bardzo krótka. **Odczytaj zaznaczenie** czyta fragment wskazany myszą.
Operacja działa w tle i można ją anulować. Tekst jest pokazywany na
ekranie, **nie jest zapisywany do bazy**.

## Analiza rachunku przez lokalną Ollamę (Etap 3)

Świstak nie korzysta z chmurowego API. Uruchom lokalną Ollamę i upewnij
się, że model jest już pobrany:

```bash
ollama list
```

Model testowy: `gemma3:4b`. Możesz wpisać nazwę innego zainstalowanego
modelu w zakładce **Analiza AI**.

**Wykonaj kolejno:**

1. **Importuj PDF** i otwórz zakładkę **Odczyt PDF**.
2. Kliknij **Odczytaj cały PDF**. Dla skanów potrzebne są Poppler i Tesseract.
3. Kliknij **Analizuj tekst przez AI (Ollama)** lub przejdź do **Analiza AI**
   i wybierz **Analizuj rachunek przez AI**.
4. Obejrzyj propozycje i fragmenty źródłowe. Świstak sprawdza
   składnię JSON, powiązanie z fragmentami tekstu, kwoty, daty,
   konto NRB/IBAN i kategorie. **To nie gwarantuje trafności modelu.**
5. Kliknij **Przenieś zweryfikowane pola do formularza** i potwierdź
   operację. Pola niepewne i brakujące nie są automatycznie przenoszone.
6. W zakładce **Rachunek** porównaj dane z oryginałem, popraw je
   i dopiero wtedy kliknij **Zapisz rachunek**.

Ważne: **analiza i przeniesienie sugestii nie zapisują rachunku do bazy.**
Kwoty z LLM mogą trafić do formularza dopiero po potwierdzeniu PLN.
Niepoprawnego konta bankowego nie przenosimy ani nie zapisujemy.
Ollama działa na żądanie w wątku roboczym; **Anuluj** zatrzymuje
wykorzystanie wyniku po zakończeniu żądania sieciowego, ale nie przerywa
natychmiast obliczeń modelu.

Przed uruchomieniem nowej gałęzi na istniejącej bazie **zrób kopię
katalogu danych Świstaka po zamknięciu aplikacji**. Przy pierwszym
uruchomieniu etapu 3 wykonywana jest migracja `002_numer_konta.sql`.
Nie zmienia ani nie kasuje istniejących rachunków czy oryginałów PDF.
Na początek polecam testy na osobnej bazie, np.:

```bash
SWISTAK_DATA_DIR=/tmp/swistak-test-ai python main.py
```

To jest wersja testowa; nie uznawaj zweryfikowanej składni JSON za
potwierdzenie prawidłowego numeru rachunku lub kwoty.

## Pierwsze kroki

1. Kliknij **Importuj PDF** i wybierz lokalny rachunek.
   Świstak sprawdza go w podglądzie, kopiuje niezmieniony oryginał do
   prywatnego archiwum i przypisuje mu identyfikator SHA-256.
2. Na karcie **Rachunek** wpisz dostawcę, kwotę, kategorię oraz
   opcjonalnie daty, numer i status. Zapisz.
3. Na karcie **Dokumenty** znajdziesz importowane pliki. Kliknięcie
   ponownie otwiera **oryginał z archiwum** i zapisane pola.
4. Ponowny import identycznego PDF nie tworzy duplikatu.

Pola dat: `RRRR-MM-DD`; kwota: np. `123,45`. Kwoty
w bazie zapisane są jako całkowita liczba groszy, bez błędów binarnych float.
W etapie 1 każdy rachunek ma jedną pozycję przypisaną do jednej kategorii.

## Gdzie są dane?

- Linux: `~/.local/share/Swistak/` (lub `$XDG_DATA_HOME/Swistak/`).
- Windows: `%LOCALAPPDATA%\Swistak\`.
- macOS: `~/Library/Application Support/Swistak/`.
- Własny katalog: ustaw zmienną `SWISTAK_DATA_DIR` na istniejącą lub nową lokalizację.

Baza: `swistak.sqlite3`, oryginały: `dokumenty/xx/<sha256>.pdf`.
Przy imporcie plik jest kopiowany atomowo i nie zmieniamy oryginału na dysku.
Aplikacja weryfikuje sumę pliku z archiwum przy ponownym otwarciu.
W razie błędu bazy lub dysku zatrzymujemy operację bez usuwania oryginałów.

**Uwaga:** pełny mechanizm kopii zapasowej i przywracania jest zaplanowany
na etap 4. Do tego czasu używaj danych testowych albo samodzielnie
zabezpieczaj cały katalog danych po zamknięciu Świstaka. Nie publikuj
ani nie dodawaj tego katalogu do repozytorium.

## Testy

```bash
python -m unittest discover -s testy -v
python -m compileall -q main.py baza gui uslugi testy
```

Testy modułów danych nie wymagają PySide6. Wykonaj również ręczny test GUI:
zaimportuj dwa pliki, zapisz rachunek, zamknij aplikację i uruchom ponownie.

## Test lokalnej Gemmy 3 4B (bez zapisu rachunków)

Przy uruchomionej Ollamie i zainstalowanym modelem `gemma3:4b`:

```bash
ollama list
python -m tools.test_gemma --demo
```

To jest **syntetyczna faktura testowa**, bez prywatnych danych. Aby
sprawdzić własny PDF **lokalnie** (tekst z PDF/OCR → LLM → JSON):

```bash
python -m tools.test_gemma --pdf "/ścieżka/do/rachunku.pdf"
```

Skrypt wysyła tekst **wyłącznie do `127.0.0.1:11434`**.
Nie zapisuje odpowiedzi w SQLite ani w pliku. Uwaga: terminal może
pokazać prywatne dane finansowe, dlatego **nie publikuj wyników
rzeczywistych rachunków**. Model może podać błędną kwotę lub konto;
każdą propozycję trzeba zweryfikować przed użyciem.
To wstępny eksperyment z formatem JSON, nie ukończona integracja.

## Kolejne etapy

Plan: [docs/PLAN.md](docs/PLAN.md).
Etapy 0–2 zostały scalone z `main`. Etap 3 jest testowany w osobnej gałęzi:
model Ollama interpretuje tekst PDF i proponuje wartości do formularza.
Użytkownik sprawdza i zatwierdza każdą zmianę przed zapisem. Ręczne
zaznaczanie fragmentów i edycja danych pozostają dostępne.
[Specyfikacja Ollamy](docs/ETAP_3_OLLAMA.md).

**Świstak jest projektowany jako aplikacja LLM-first:** Ollama i lokalny model będą głównym sposobem interpretacji rachunków. Reguły i ręczne zaznaczanie PDF to rozwiązania awaryjne, uruchamiane, gdy model nie zadziała lub pomyli dane. Pozyskanie tekstu/OCR odbywa się wcześniej wyłącznie w celu przygotowania wejścia dla LLM, a walidacja JSON i numerów kont obowiązuje zawsze.

Do wyboru lokalnego modelu wykorzystamy **[AI Bobra](https://github.com/DarkZachi83/Bobr)**:
testy sprzętu i szybkości, polszczyzny, JSON oraz planowane testy wiedzy
z nauk ścisłych. Końcową decyzję zweryfikujemy na syntetycznych rachunkach.
[Projekt doboru modelu](docs/WYBOR_MODELU_AI_BOBR.md).
AI Bóbr będzie narzędziem do benchmarków, **nie obowiązkową zależnością Świstaka**.

Bez Ollamy program zachowa możliwość ręcznej obsługi rachunków, ale nie pełną funkcjonalność AI. Nie wysyłamy dokumentów do chmury, nie wykonujemy przelewów ani nie dodajemy telemetrii.

## Licencja

Copyright (C) 2026 Rafał Zacharski.

**GPL-3.0-only** — pełna treść w [LICENSE](LICENSE).
Przed dystrybucją paczek wykonywalnych zweryfikuj warunki
licencyjne PySide6/Qt i ewentualnych dołączonych bibliotek.
