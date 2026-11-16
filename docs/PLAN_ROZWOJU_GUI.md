# Świstak — plan następnych prac: główne menu, pulpit i statystyki

**Status:** GUI-1 i GUI-2 odebrane. GUI-3 sprawdzony wstępnie. GUI-4 wdrożony. Przed wydaniem pozostaje odbiór całego przepływu na lokalnych rachunkach.

**Repozytorium:** https://github.com/DarkZachi83/Swistak · `main`  
**Poprzedni etap:** [AI Core 1.0 — zamknięcie etapu 8](ai_core/ETAP_8_ZAMKNIECIE.md).

## Stan po GUI-1

**Pulpit główny** otwiera się po uruchomieniu. Kreator **Nowa faktura** udostępnia **Odczyt PDF / skanu → Analiza AI → Edycja danych → Faktura → Dokumenty**. Rejestr zapisanych rachunków jest dostępny jako **Moje faktury**.

Pulpit sumuje aktywne należności w groszach. Zakres bliskich terminów obejmuje dziś i siedem kolejnych dni. Wydatki za miesiąc usługi są przypisane według końca okresu, a przy jego braku według daty wystawienia. Kwota faktycznie zapłacona w miesiącu obejmuje faktury z zapisaną datą płatności. Oczekiwania pochodzą z zapisów utworzonych w Planie dla wybranego miesiąca.

Odbiór na odrębnej bazie przez `./uruchom.sh --test`: wczytaj testowy PDF, wpisz dane w formularzu i wróć do niego po przejściu przez Pulpit i Moje faktury. Zweryfikuj sumy dla zapisanych testowych faktur, przełącz PL/EN i sprawdź pulpit przy wyłączonej Ollamie.

## Statystyki (GUI-2)

Widok udostępnia zakres dat, grupowanie miesięczne lub roczne, podział kwot według statusu oraz wykresy słupkowe okresów, kategorii i dostawców. Dla pełnego miesiąca lub roku porównaniem jest poprzedni miesiąc lub rok kalendarzowy. Dla dowolnego zakresu porównaniem jest bezpośrednio poprzedzający go okres o tej samej liczbie dni.

Podstawa „Miesiąc usługi” używa końca okresu usługi lub daty wystawienia. Podstawa „Faktyczna płatność” obejmuje opłacone faktury z zapisaną datą płatności. Filtr kategorii ogranicza kwoty do przypisanych pozycji. Brakujące przypisanie jest widoczne jako osobna pozycja, a łączna kwota faktury pochodzi z nagłówka. Do odbioru użyj bazy testowej i porównaj wynik dla faktury, której miesiąc usługi i miesiąc płatności są różne.

## Integracja modułów (GUI-3)

Moje faktury, Plan rachunków, Historia, Agent AI i Ustawienia są dostępne w głównym oknie. Plan i Historia pamiętają osobno wybrany miesiąc, a skróty na Pulpicie przekazują miesiąc lub filtr należności. Zakładka zamknięcia miesiąca jest w Historii. Otwarcie innego dokumentu wymaga potwierdzenia, jeśli formularz zawiera niezapisane zmiany. Ustawienia utrwalają zmiany po wybraniu „Zapisz”.

## Dopracowanie i odbiór (GUI-4)

Boczne menu pokazuje ikony w wąskim oknie, a skróty `Alt+1`–`Alt+9` odpowiadają kolejności modułów. Przy małej szerokości podgląd PDF układa się nad formularzem. Przyciski i karty zawijają się, a dłuższe widoki przewijają pionowo. `Ctrl+O` otwiera import PDF na Linuxie.

Odbiór na prawdziwych rachunkach wykonaj lokalnie w `./uruchom.sh --test`, korzystając z osobnej bazy. Przejdź przez import, OCR, analizę modelem w lokalnej Ollamie, korektę i zapis. Dla rachunku z kodem sprawdź QR. Zweryfikuj ponowne rozpoznanie dostawcy, datę płatności w Historii, kwoty na Pulpicie i w Statystykach, kopię i przywrócenie oraz zamknięcie programu. Sprawdź przełączenie PL/EN podczas edycji dokumentu. Prywatne PDF-y i kopie pozostają na komputerze użytkownika.

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

### GUI-1 — Menu główne i Pulpit (odebrany)

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

### GUI-2 — Statystyki (odebrany)

- Wydatki miesięczne i roczne, porównanie okresów, kategorie/dostawcy,
  udział kategorii, płatności opłacone/nieopłacone.
- Filtry zakresu dat, kategorii, dostawcy, podstawy czasowej i statusu.
- Wykresy z danych SQLite, bez podwójnego sumowania nagłówków faktury
  przy pozycjach. Kwoty liczyć w groszach, formatować dopiero w UI.
- Wycofane faktury nie wchodzą do aktywnych sum; brak daty płatności
  nie może być uzupełniony datą wystawienia.
- Obsłuż pustą bazę i brak wybranych danych bez wyjątku.
- Testy obliczeń syntetycznych i poprawności filtrów.

### GUI-3 — Integracja modułów i lepsza nawigacja (wstępnie sprawdzony)

- Włącz istniejącą tabelę `Faktury` do `Moje faktury`.
- Docelowo przenieś zawartość dialogu `Plan / Historia` do właściwych
  ekranów, bez powielania usług, bez utraty transakcyjnego audytu.
- Panel Agenta przenieś pod `Agent AI`, zachowując ręczne anulowanie i log.
- Konfigurację modeli, katalogów i specjalistów zachowaj w Ustawieniach.
- Spójne przejścia z powiadomień pulpitu do konkretnej faktury, planu
  i historii; bez automatycznych zapisów lub zatwierdzeń.

### GUI-4 — Dopracowanie i akceptacja (testy na prawdziwych rachunkach do wykonania)

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
