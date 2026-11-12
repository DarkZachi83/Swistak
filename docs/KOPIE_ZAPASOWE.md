# Kopie zapasowe i przywracanie — Świstak

## Zakres kopii

Menu **Plik → Utwórz kopię zapasową…** tworzy jedno archiwum **ZIP**.
Zawiera lokalne dane:
- **swistak.sqlite3** — spójna migawka przez SQLite Backup API, nie surowa kopia otwartej bazy;
- **dokumenty/** — oryginalne archiwalne PDF-y;
- **wzorce/** — zatwierdzone wzorce JSON i historia poprzednich rewizji;
- **kopie_migracji/** — wcześniejsze kopie migracyjne, jeśli istnieją;
- **config/settings.json** — język i model Ollama, jeśli ustawienia są dostępne;
- **manifest.json** — wersja formatu, data UTC, lista plików, rozmiary i SHA-256.

Archiwum nie obejmuje pobranych modeli Ollama, Tesseract ani programu.

## Tworzenie

1. Wybierz **Plik → Utwórz kopię zapasową…**.
2. Podaj nową nazwę ZIP poza katalogiem danych Świstaka. Istniejąca kopia nie zostanie nadpisana.
3. Potwierdź ostrzeżenie o prywatności, następnie zachowaj kopię w bezpiecznym miejscu.

**UWAGA: standardowe archiwum ZIP nie jest szyfrowane.** Zawiera prywatne
dokumenty i dane finansowe. Przechowuj na zaszyfrowanym nośniku lub
w chronionym katalogu; nie dodawaj kopii ani faktur do GitHuba.

## Przywracanie

1. Wybierz **Plik → Przywróć kopię zapasową…** i wskaż ZIP.
2. Aplikacja przed zmianą danych sprawdzi manifest i SHA-256 każdego pliku,
   integralność bazy SQLite, klucze obce i odwołania do archiwalnych PDF-ów.
   ZIP z niedozwolonymi ścieżkami (np. z próbą wyjścia poza katalog) zostanie odrzucony.
3. Po kontroli pojawi się pytanie z domyślną odpowiedzią **Nie**.
4. Po potwierdzeniu program zwolni uchwyty SQLite/PDF, zachowa cały bieżący
   katalog danych w sąsiednim folderze **Swistak-przed-przywroceniem-…**,
   podmieni dane i otworzy nowe okno.
5. Sprawdź faktury, dokumenty, kategorie oraz wzorce. Nie usuwaj zachowanego
   katalogu, dopóki nie upewnisz się, że wszystko jest w porządku.

W razie błędu przywracania Świstak podejmie próbę cofnięcia podmiany.
Po przerwaniu pracy systemu między podmianami katalogów aplikacja
nie powinna utworzyć nowej, pustej bazy, jeśli obok istnieje zachowany katalog.

## Testy i ograniczenia

Najpierw wykonaj próbę **wyłącznie w trybie testowym** przez uruchomienie
**./uruchom.sh --test**. Zaimportuj fikcyjny PDF, zapisz fakturę, utwórz ZIP,
zmień dane i przywróć ZIP. Porównaj wartości i liczbę dokumentów.

Testy automatyczne:
- python3 -m unittest testy.test_kopie_zapasowe -v
- QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest testy.test_menu_kopie_zapasowe -v

Kopiowanie dużych archiwów jest na razie synchroniczne — interfejs może
pozostać zajęty przez dłuższą chwilę. Nie wdrożono jeszcze harmonogramu
automatycznych kopii ani szyfrowania ZIP. Do ważnych danych stosuj również
zewnętrzną, niezależną kopię na bezpiecznym nośniku.

## Wyczyszczenie bazy danych

Nowa pozycja **Plik → Wyczyść bazę danych…** jest operacją destrukcyjną.
Po ostrzeżeniu „UWAGA! Komenda spowoduje wymazanie wszystkich danych!
Utwórz najpierw kopię zapasową.” użytkownik wskazuje miejsce na **nowe ZIP**.
Program wykonuje pełną kopię i jej walidację, a dopiero następnie wymaga
wpisania hasła potwierdzającego (`USUŃ WSZYSTKO` w języku polskim) i
ostatniej zgody. Anulowanie dowolnego kroku pozostawia bieżącą bazę bez zmian.

Czyszczenie usuwa lokalne rekordy, PDF-y, wzorce, historię rewizji i własne
kategorie z aktywnego katalogu danych. Nowa baza ma tylko kategorie
fabryczne. **Ustawienia modelu Ollama i języka są zachowane.** Zewnętrzne,
obowiązkowe archiwum ZIP pozostaje dostępne do przywrócenia.

Program chroni się przed wymazaniem przypadkowego katalogu zawierającego
obce pliki. W razie nieudanej podmiany próbuje odzyskać poprzedni stan.
Jeśli usunięcie starego katalogu nie powiedzie się, informuje o jego ścieżce;
nie twierdzi wtedy, że wszystkie dane zostały usunięte. Pliki usunięte
standardowo nie są nadpisywane kryptograficznie, więc nie jest to
funkcja bezpiecznego niszczenia danych na nośniku.

Testuj najpierw z `./uruchom.sh --test`.
