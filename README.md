# Świstak

**Świstak** — projekt lokalnej aplikacji do zarządzania domowymi rachunkami.

Planowane możliwości: wczytywanie PDF (tekstowych i skanowanych), wskazywanie obszarów myszą,
przypisywanie wartości do pól i kategorii, ręczne zatwierdzanie, lokalne archiwizowanie
oryginałów, historia wydatków i statystyki.

> **Stan projektu: etap 0 / prototyp PDF.** Aplikacja aktualnie *wyświetla* PDF-y
> i pozwala zaznaczać fragmenty strony. **Nie wykonuje jeszcze OCR, nie zapisuje
> rachunków i nie ma bazy SQLite.** Funkcje te powstaną w kolejnych etapach.

## Uruchomienie

Wymagany Python z dostępem do PySide6, system Linux lub Windows.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

W Windows aktywacja środowiska: `.venv\Scripts\activate`.

Można też otworzyć dokument wskazany w wierszu poleceń:

```bash
python main.py /sciezka/do/testowego.pdf
```

W oknie dostępne są: **Otwórz PDF**, poprzednia/następna strona,
powiększenie, **Dopasuj**, zaznaczanie prostokąta lewym przyciskiem myszy.
`Ctrl` + kółko myszy zmienia powiększenie; zwykłe kółko przewija dokument.
W dolnej części okna wyświetlane są współrzędne zaznaczenia (0–1)
niezależne od zoomu. Na tym etapie nie są trwale zapisywane.

## Testy

```bash
python -m unittest discover -s testy -v
```

Testy etapu 0 sprawdzają matematykę zaznaczeń i nie wymagają PySide6.
Test interfejsu trzeba wykonać lokalnie z zainstalowaną biblioteką.

## Plan rozwoju

Szczegóły: [docs/PLAN.md](docs/PLAN.md).

1. **Etap 0:** prototyp podglądu i zaznaczania PDF (w toku).
2. **Etap 1:** SQLite, migracje, kategorie, import i trwała archiwizacja oryginałów.
3. **Etap 2:** odczyt warstwy tekstowej bez OCR, Tesseract dla skanów, przypisanie pól i zatwierdzanie.
4. **Etap 3:** historia, podstawowe statystyki, weryfikowana kopia i przywracanie danych.
5. **Etap 4:** zapamiętywanie szablonów dostawców — dopiero po stabilizacji podstaw.

**Architektura:** modułowy Python; interfejs PySide6, baza SQLite, OCR przez Tesseract
(z OpenCV i Poppler dla skanów). Projekt bazuje koncepcyjnie na strukturze
[Nornicy](https://github.com/DarkZachi83/Nornica) i estetyce
[AI Bobra](https://github.com/DarkZachi83/Bobr).

## Prywatność i bezpieczeństwo

- Wszystkie przyszłe operacje na rachunkach mają działać lokalnie, bez wysyłania danych do chmury.
- Oryginały PDF i baza SQLite będą przechowywane **poza repozytorium z kodem**.
- `.gitignore` wyklucza pliki PDF, bazy, archiwa kopii i inne prywatne dane.
- Do publicznych testów należy używać tylko danych całkowicie syntetycznych.
- Nie należy dołączać do zgłoszeń błędów prywatnych rachunków ani zrzutów z danymi osobowymi.

## Licencja

Copyright (C) 2026 Rafał Zacharski.

Program jest udostępniany na warunkach **GNU General Public License, version 3 only
(SPDX: GPL-3.0-only)**. Pełna treść znajduje się w pliku [LICENSE](LICENSE).

Zależności zewnętrzne zachowują własne licencje; przed publikacją paczek wykonywalnych
należy skontrolować obowiązki licencyjne PySide6/Qt i innych dołączonych komponentów.
