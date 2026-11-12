# Świstak — PROJECT_STATUS

**Ostatnia weryfikacja:** 2026-11-12  
**Repozytorium:** `DarkZachi83/Swistak` · **gałąź:** `main`  
**Punkt odniesienia:** commit `2a868f0b0b71a93dece8958f51a688b5a2ad486f` (wyszukiwanie modeli lokalnych i testy, przed aktualizacją tego dokumentu).  
**Wersja w `wersja.py`:** `0.1.0b1` / `0.1.0 Beta 1`.

> To dokument przekazania prac między sesjami programistycznymi i asystentami AI. **Kod na bieżącym HEAD `main` jest nadrzędny**; przed wznowieniem trzeba porównać ten dokument z repozytorium i ostatnimi commitami. Sam wpis „wykonane” nie zastępuje testu na komputerze użytkownika.

## Zrealizowane i obecne w kodzie `main`

- Lokalny rejestr SQLite, wersjonowane migracje, oryginalne PDF-y przechowywane w prywatnym archiwum, SHA-256 i rozpoznawanie identycznego importu.
- Podgląd PDF, lokalny odczyt tekstu i OCR (Tesseract), analiza przez lokalną Ollamę; edycja propozycji AI i formularza przed świadomym zapisem.
- Interfejs PySide6 w językach polskim i angielskim; etapy: Odczyt PDF → Analiza AI → Edycja danych → Faktura → Dokumenty.
- Tabela **Faktury** (nowy widok): filtrowanie i sortowanie zapisanych rekordów, statusy, suma widocznych, otwieranie do edycji; pierwotne **Dokumenty** pozostają archiwum PDF. Dane wyłącznie z SQLite, bez nowej migracji.
- AGENT: przycisk „Szukaj modeli lokalnych…” — gotowe modele przez lokalne Ollama /api/tags, osobna informacyjna lista modeli GGUF i magazynów Ollamy znalezionych w znanych lokalizacjach Bobra; wybrać można tylko modele dostępne w API. Wybór zapisuje ustawienie `ollama_model`; bez pobierania, ładowania modeli i bez przetwarzania faktur podczas skanowania.
- Interfejs ANALIZA AI: wewnętrzne zakładki **DANE** (maksymalna tabela 5 kolumn, komentarze edytowane dwuklikiem, INFO i akcje na dole) i **AGENT** (Ollama, wybór wzorca, ogólne wskazówki). Sama przebudowa układu nie zmienia algorytmu LLM; aktualne notatki są używane podczas propozycji wzorca, nie jako nowy prompt bieżącego zapytania.
- Odczyt kodów QR z PDF: lokalny PDFium + ZXing-C++, okno z danymi płatności i potwierdzanym przenoszeniem kwoty oraz numeru konta. Żadnych przelewów ani automatycznego zapisu. **Licencja ZXing-C++: Apache-2.0, dopuszcza wykorzystanie komercyjne**; zawartość docelowego binarnego wheel wymaga audytu przed wydaniem Business.
- Inteligentne wzorce faktur W1–W4: dopasowywanie na podstawie sprzedawcy/układu, zatwierdzanie, edycja w formularzu zamiast ręcznego JSON, wyłączanie i przywracanie rewizji. Osobne reguły sprawdzają pełny miesiąc rozliczeniowy, jeśli źródło jednoznacznie wskazuje `MM/RRRR`.
- **Ochrona przed ponownym zapisem faktury (2026-11-11):** `RejestrRachunkow.znajdz_duplikat` i `zapisz_rachunek(..., nadpisz_id=...)` rozpoznają ten sam dokument lub dostawcę i numer faktury. Zapis istniejącej pozycji bez jawnego potwierdzenia jest blokowany w warstwie bazy. GUI pyta „Czy nadpisać?” z domyślnym **Nie**; potwierdzona aktualizacja zachowuje identyfikator faktury, bez dopisywania drugiej.
- Testy syntetyczne zapisów i duplikatów: `testy/test_rejestr.py`, `testy/test_duplikaty_baza.py`, `testy/test_duplikaty_faktur.py`; workflow `.github/workflows/duplikaty-sqlite.yml` dla testów bez Qt.
- Linux Beta: dokumentacja paczki źródłowej i eksperymentalnego pakietu binarnego. Nie traktować tego jako gotowej, oficjalnej wersji dla użytkowników końcowych.

## Stan weryfikacji

**GitHub Actions — pełny zestaw testów ukończony pomyślnie** na Pythonie 3.11 i 3.13 (run `43182694952`, stan kodu `9a0fe7697be5de7a53b927ee4a04bfd2604331a4`). Testy QR korzystają wyłącznie z fikcyjnego kodu i syntetycznego PDF-u. Naprawiono też obsługę polskiego „ł” w nazwach okresów rozliczeniowych oraz izolację języka w teście sortowania kwot. **Nie wykonano testu GUI na komputerze użytkownika ani testu nowego dekodera na jego prywatnej fakturze**; są to kolejne testy akceptacyjne.

**Wyszukiwanie modeli lokalnych:** GitHub Actions `43197033453` zakończone sukcesem na Pythonie 3.11 i 3.13. Testy korzystają z fikcyjnych manifestów Ollamy, plików GGUF oraz symulowanego API `/api/tags`, bez prywatnych danych. Rzeczywisty skan katalogów na komputerze użytkownika pozostaje do sprawdzenia.

## Dystrybucja i licencje

- Aktualny kod `main`: **PolyForm Noncommercial 1.0.0**. Business wymaga osobnej licencji dla klientów; wcześniejsze wersje GPL pozostają na swoich warunkach.
- Biblioteka QR `zxing-cpp` (`>=3.1.1,<4`): podstawowa licencja Apache-2.0 **pozwala na użycie komercyjne**. Przed sprzedażą instalatora zweryfikować konkretny wheel, notices i inne dołączane komponenty Qt/PDFium oraz zapisać listę wersji/hashów.
- Szczegóły: `THIRD_PARTY_LICENSES.md` i `docs/LICENCJONOWANIE.md`.

## Następne zadania — kolejność

1. **Test akceptacyjny QR:** sprawdzić syntetyczne kody, odczyt PDF na komputerze użytkownika, przypadki nieznanych formatów, brak QR, przeniesienie danych tylko po potwierdzeniu; testy CI nie używają prywatnego PDF.
2. **Test akceptacyjny tabeli faktur:** sprawdzić na komputerze docelowym różne statusy, daty, sortowanie kwot, wyszukiwanie, zapis i nadpisanie; zweryfikować zachowanie podglądu PDF po otwarciu z tabeli. Wykonać pełny zestaw testów syntetycznych w CI i lokalnie.
3. **Weryfikacja end-to-end:** fikcyjny PDF z warstwą tekstową i fikcyjny skan → OCR → Ollama → korekta → zapis → ponowny import → odmowa/potwierdzenie nadpisania. Prawdziwy dokument wyłącznie lokalnie, poza GitHubem.
4. **Kopie zapasowe i historia/statystyki** (etap 4 według `docs/PLAN.md`): spójna kopia SQLite razem z archiwum PDF i sprawdzone przywracanie; przed wykorzystaniem do ważnych danych zapewnić bezpieczną kopię.
5. **Porządek dokumentacji:** uaktualnić `docs/PLAN.md`, który nadal nazywa część zaimplementowanego etapu 3 „gałęzią roboczą”. Uzupełniać status po każdym większym etapie, także przy zmianie interfejsu i testów.

## Testy do uruchamiania

```bash
# Baza i duplikaty — Python bez bibliotek GUI
python3 -m unittest testy.test_rejestr testy.test_duplikaty_baza testy.test_rejestr_faktur -v

# W środowisku projektu z zainstalowanym PySide6:
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest   testy.test_duplikaty_faktur testy.test_tabela_faktur testy.test_wzorce   testy.test_wzorce_integracja testy.test_okres_wzorca_formularz   testy.test_menedzer_wzorcow -v

# Nowe testy lokalnego odczytu QR (tylko dane fikcyjne):
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest testy.test_kody_qr -v

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
