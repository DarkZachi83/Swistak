# Świstak — PROJECT_STATUS

**Ostatnia weryfikacja:** 2026-11-11  
**Repozytorium:** `DarkZachi83/Swistak` · **gałąź:** `main`  
**Punkt odniesienia:** commit `eab7aabe86a0c391c2a0ad9954b7c49a95c87f04` (przed dodaniem tego pliku).  
**Wersja w `wersja.py`:** `0.1.0b1` / `0.1.0 Beta 1`.

> To dokument przekazania prac między sesjami programistycznymi i asystentami AI. **Kod na bieżącym HEAD `main` jest nadrzędny**; przed wznowieniem trzeba porównać ten dokument z repozytorium i ostatnimi commitami. Sam wpis „wykonane” nie zastępuje testu na komputerze użytkownika.

## Zrealizowane i obecne w kodzie `main`

- Lokalny rejestr SQLite, wersjonowane migracje, oryginalne PDF-y przechowywane w prywatnym archiwum, SHA-256 i rozpoznawanie identycznego importu.
- Podgląd PDF, lokalny odczyt tekstu i OCR (Tesseract), analiza przez lokalną Ollamę; edycja propozycji AI i formularza przed świadomym zapisem.
- Interfejs PySide6 w językach polskim i angielskim; etapy: Odczyt PDF → Analiza AI → Edycja danych → Faktura → Dokumenty.
- Inteligentne wzorce faktur W1–W4: dopasowywanie na podstawie sprzedawcy/układu, zatwierdzanie, edycja w formularzu zamiast ręcznego JSON, wyłączanie i przywracanie rewizji. Osobne reguły sprawdzają pełny miesiąc rozliczeniowy, jeśli źródło jednoznacznie wskazuje `MM/RRRR`.
- **Ochrona przed ponownym zapisem faktury (2026-11-11):** `RejestrRachunkow.znajdz_duplikat` i `zapisz_rachunek(..., nadpisz_id=...)` rozpoznają ten sam dokument lub dostawcę i numer faktury. Zapis istniejącej pozycji bez jawnego potwierdzenia jest blokowany w warstwie bazy. GUI pyta „Czy nadpisać?” z domyślnym **Nie**; potwierdzona aktualizacja zachowuje identyfikator faktury, bez dopisywania drugiej.
- Testy syntetyczne zapisów i duplikatów: `testy/test_rejestr.py`, `testy/test_duplikaty_baza.py`, `testy/test_duplikaty_faktur.py`; workflow `.github/workflows/duplikaty-sqlite.yml` dla testów bez Qt.
- Linux Beta: dokumentacja paczki źródłowej i eksperymentalnego pakietu binarnego. Nie traktować tego jako gotowej, oficjalnej wersji dla użytkowników końcowych.

## Stan weryfikacji

Powyższe funkcje sprawdzono przez **odczyt kodu, dokumentacji i commitów** na GitHubie. W tej sesji nie uruchomiono lokalnie testów, aplikacji ani rzeczywistego PDF/OCR. Samo istnienie testów lub workflow nie oznacza potwierdzonego wyniku CI. Przed uznaniem etapu za zakończony należy wykonać test GUI na komputerze docelowym.

## Następne zadania — kolejność

1. **Tabela faktur (kolejny etap funkcjonalny, jeszcze niezrealizowany).** Obecne `gui/okno_glowne.py::_zbuduj_liste` i `_odswiez_liste` pokazują dokumenty w `QListWidget`, nie tabelę zapisanych faktur. Przygotować osobny widok faktur (lub wyraźne rozróżnienie od archiwum PDF), odczytywany z SQLite, z kolumnami: dostawca, numer, data wystawienia, termin płatności, kwota, kategoria, status i powiązany PDF. Zapewnić sortowanie, filtrowanie, otwieranie do podglądu/edycji i odświeżanie po zapisie/nadpisaniu. W miarę możliwości dodać testy syntetyczne modelu danych i GUI. Nie zmieniać archiwalnych PDF-ów.
2. **Weryfikacja end-to-end:** fikcyjny PDF z warstwą tekstową i fikcyjny skan → OCR → Ollama → korekta → zapis → ponowny import → odmowa/potwierdzenie nadpisania. Prawdziwy dokument wyłącznie lokalnie, poza GitHubem.
3. **Kopie zapasowe i historia/statystyki** (etap 4 według `docs/PLAN.md`): spójna kopia SQLite razem z archiwum PDF i sprawdzone przywracanie; przed wykorzystaniem do ważnych danych zapewnić bezpieczną kopię.
4. **Porządek dokumentacji:** uaktualnić `docs/PLAN.md`, który nadal nazywa część zaimplementowanego etapu 3 „gałęzią roboczą”. Uzupełniać status po każdym większym etapie, także przy zmianie interfejsu i testów.

## Testy do uruchamiania

```bash
# Baza i duplikaty — Python bez bibliotek GUI
python3 -m unittest testy.test_rejestr testy.test_duplikaty_baza -v

# W środowisku projektu z zainstalowanym PySide6:
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest   testy.test_duplikaty_faktur testy.test_wzorce   testy.test_wzorce_integracja testy.test_okres_wzorca_formularz   testy.test_menedzer_wzorcow -v

# Pełny zestaw testów, jeśli zależności są dostępne:
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s testy -v
```

Do testów interaktywnych na Linuxie używać `./uruchom.sh --test`, który wybiera odrębny katalog danych. Nie uruchamiać testów zapisu na bazie użytkownika.

## Niezmienne zasady

- Prace prowadzić na `main`, zgodnie z ustalonym trybem współpracy, z małymi logicznymi commitami i testami; przed zapisem zawsze ponownie sprawdzić aktualny kod.
- **Nie publikować na GitHubie prawdziwych faktur, skanów, plików SQLite, danych nabywcy ani danych finansowych.** W repozytorium wyłącznie fikcyjne dane i syntetyczne dokumenty.
- Archiwalnego PDF nie wolno modyfikować; przetwarzanie rachunków i Ollama pozostają lokalne.
- AI wyłącznie proponuje dane. To użytkownik potwierdza ich zapis, aktualizację i zapis wzorców; odrzucenie nadpisania nie może zmieniać bazy.
- Zachować kompatybilność istniejących baz i migracji; nie modyfikować historycznych migracji bez szczególnego uzasadnienia.
- Po każdym etapie odświeżyć ten plik: **zrobione / sprawdzone / otwarte / następny krok / commit HEAD**.

## Instrukcja wznowienia dla kolejnej sesji

1. Odczytaj `PROJECT_STATUS.md`, `README.md`, `docs/PLAN.md`, aktualny `main` i ostatnie commity.
2. Zweryfikuj, czy niniejszy status nadal zgadza się z kodem (w szczególności listą/tabelą faktur i ochroną duplikatów).
3. Kontynuuj od pierwszego niezakończonego zadania, tylko na syntetycznych danych.
4. Wykonaj adekwatne testy, zapisz commit i uaktualnij ten dokument. Gdy nie możesz uruchomić testów, wpisz to jawnie.
