# Świstak — plan następnych prac: główne menu, pulpit i statystyki

**Status:** plan zatwierdzony co do kierunku 14.11.2026, **nie zaimplementowany**.  
**Repozytorium:** https://github.com/DarkZachi83/Swistak · `main`  
**Poprzedni etap:** [AI Core 1.0 — zamknięcie etapu 8](ai_core/ETAP_8_ZAMKNIECIE.md).

## Diagnoza obecnego UI

Aktualny główny ekran Świstaka jest przede wszystkim **procesem obsługi faktury** z sześcioma krokami: **Odczyt PDF / skanu → Analiza AI → Edycja danych → Faktura → Dokumenty → Faktury**. Istnieją także okna **Plan / Historia**, **Panel Agenta**, **Ustawienia** i **O programie**, ale nie istnieje jeszcze odrębny, codzienny **pulpit główny**, pełna nawigacja po funkcjach programu ani ekran statystyk z wykresami.

Nie należy przedstawiać dotychczasowej analizy AI ani dialogu Plan / Historia jako gotowego docelowego pulpitu. Stare sześć kart można zachować jako wewnętrzny kreator **Nowa faktura**.

## Docelowe moduły nawigacji

1. **Pulpit główny** — podsumowanie bieżącego miesiąca, stan płatności, terminy, brakujące dokumenty, Agent.
2. **Nowa faktura** — istniejący kompletny kreator PDF/OCR → LLM → edycja → zapis, bez utraty stanu.
3. **Moje faktury** — tabela, wyszukiwanie, filtrowanie, edycja, podgląd archiwalnego PDF.
4. **Statystyki** — miesiące, lata, kategorie i dostawcy, wykresy i porównania.
5. **Plan rachunków** — profile, harmonogramy, oczekiwania i powiązania.
6. **Historia** — daty płatności, wycofania, dziennik zmian, zamknięcie miesiąca.
7. **Agent AI** — raporty kontroli lokalnych i opcjonalnych specjalistów.
8. **Ustawienia** — modele Ollamy, katalogi, role, języki.
9. **O programie** — informacje, licencje, wersja.

**Menu aplikacji**: zachowaj górne `Plik / Ustawienia / Języki / O programie`,
a dodaj spójną nawigację modułów, np. boczny pasek podobny do
obecnej stylistyki Świstaka / AI Bobra.

## Harmonogram realizacji

### GUI-1 — Menu główne i Pulpit (pierwszy następny etap)

- Utwórz docelową nawigację modułów i ekran startowy `Pulpit główny`.
- Wykorzystaj obecne `QStackedWidget`/PySide6 tak, aby nie resetować
  edycji importowanej faktury przy przechodzeniu między modułami.
- Nie usuwaj obecnych dialogów ani kreatora; początkowo można je otwierać
  z nowego pulpitu i menu.
- Pulpit ma pokazywać **prawdziwe liczby z lokalnej SQLite**:
  kwota do zapłaty, faktury po terminie, płatne w ciągu 7 dni,
  wydatki za wybrany miesiąc, brakujące/niepewne oczekiwania.
- Słowa **„opłacone za miesiąc usługi”** i **„faktycznie zapłacone w miesiącu”**
  oznaczają różne daty i należy je rozróżnić.
- Brak Ollamy nie blokuje pulpitu ani obliczeń.
- Testy Qt, nawigacji, pustej bazy i syntetycznych danych; tłumaczenia PL/EN.
- Kryteria: pulpit otwiera się jako pierwszy; żadna kwota nie jest zgadywana;
  kliknięcie `Nowa faktura` zachowuje cały stary proces i dane formularza.

### GUI-2 — Statystyki

- Wydatki miesięczne i roczne, porównanie okresów, kategorie/dostawcy,
  udział kategorii, płatności opłacone/nieopłacone.
- Filtry zakresu dat, kategorii, dostawcy, podstawy czasowej i statusu.
- Wykresy z danych SQLite, bez podwójnego sumowania nagłówków faktury
  przy pozycjach. Kwoty liczyć w groszach, formatować dopiero w UI.
- Wycofane faktury nie wchodzą do aktywnych sum; brak daty płatności
  nie może być uzupełniony datą wystawienia.
- Obsłuż pustą bazę i brak wybranych danych bez wyjątku.
- Testy obliczeń syntetycznych i poprawności filtrów.

### GUI-3 — Integracja modułów i lepsza nawigacja

- Włącz istniejącą tabelę `Faktury` do `Moje faktury`.
- Docelowo przenieś zawartość dialogu `Plan / Historia` do właściwych
  ekranów, bez powielania usług, bez utraty transakcyjnego audytu.
- Panel Agenta przenieś pod `Agent AI`, zachowując ręczne anulowanie i log.
- Konfigurację modeli, katalogów i specjalistów zachowaj w Ustawieniach.
- Spójne przejścia z powiadomień pulpitu do konkretnej faktury, planu
  i historii; bez automatycznych zapisów lub zatwierdzeń.

### GUI-4 — Dopracowanie i akceptacja

- Jednolity ciemny motyw, odstępy, ikony, układ dla mniejszych okien
  i HiDPI; brak ucinanych opisów i przycisków.
- Języki polski/angielski przełączane bez utraty danych formularza.
- Testy na Linuxie Python 3.14.10 i w GitHub Actions Python 3.11/3.13.
- Sprawdzenie PDF, QR, W1–W4, bazy, backupów, resetu i plików wydania.
- Manualny przegląd użytkownika ze zrzutami ekranu i poprawki UX.

## Nienaruszalne zasady

- **AI Core 1.0 zakończony**: nie przebudowuj silnika przy projektowaniu
  wizualnym, chyba że test wykaże rzeczywistą wadę.
- **Local-first i human-in-control**: tylko lokalna Ollama; AI nie wykonuje
  przelewów ani automatycznych zapisów SQLite.
- Prywatne faktury, PDF, rachunki i kopie nie mogą trafić na GitHub.
- Działające migracje 001–005 nie mogą być modyfikowane wstecz.
  Nowa migracja tylko jeśli naprawdę wymaga tego funkcja.
- Wspólny styl PySide6; zachowanie już działających okien jako pomostu.
- Opracowanie i wdrażanie **bezpośrednio na `main`**, testy syntetyczne,
  GitHub Actions, następnie ręczny odbiór użytkownika.
- Pracuj tylko na zmienionych plikach, bez dodatkowych worktree;
  przed migracją/ryzykowną operacją wykonaj backup.
