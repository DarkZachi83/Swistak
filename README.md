# Świstak

**Świstak** — lokalna aplikacja do prowadzenia rejestru domowych rachunków.
Kod jest publiczny, ale **dokumenty finansowe oraz baza są prywatne i nie
są przechowywane w repozytorium GitHub**.

> **Etap 1 (gałąź robocza)**: import oryginalnych PDF-ów do prywatnego katalogu
> danych, lokalna SQLite, kategorie, ręczny formularz rachunku, lista dokumentów.
> Wyświetlanie wielostronicowych PDF-ów, zoom i zaznaczanie obszaru działa
> już od etapu 0. **OCR i automatyczne wypełnianie pól nie są jeszcze dostępne.**

## Instalacja i uruchomienie

Python 3.11+; Linux lub Windows z dostępem do PySide6.

```bash
git clone https://github.com/DarkZachi83/Swistak.git
cd Swistak
git switch feature/etap-1-baza-i-archiwum
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Windows: aktywacja środowiska przez `.venv\Scripts\activate`.
Można otworzyć wskazany PDF od razu: `python main.py /sciezka/do/rachunku.pdf`.

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

## Kolejne etapy

Plan: [docs/PLAN.md](docs/PLAN.md).
W etapie 2 pojawi się odczyt warstwy tekstowej PDF oraz OCR Tesseract
dla skanów. W nowym **etapie 3** lokalny model przez **Ollamę** zaproponuje
wypełnienie formularza jako JSON: dostawca, kwota do zapłaty, termin
płatności, numer dokumentu i numer konta bankowego. Użytkownik zawsze
sprawdza i zatwierdza wartości. Zaznaczanie fragmentów PDF pozostaje
metodą zapasową. [Specyfikacja Ollamy](docs/ETAP_3_OLLAMA.md).

Ollama jest **opcjonalna**. Nie wysyłamy dokumentów do chmury, nie
wykonujemy przelewów ani nie dodajemy telemetrii.

## Licencja

Copyright (C) 2026 Rafał Zacharski.

**GPL-3.0-only** — pełna treść w [LICENSE](LICENSE).
Przed dystrybucją paczek wykonywalnych zweryfikuj warunki
licencyjne PySide6/Qt i ewentualnych dołączonych bibliotek.
