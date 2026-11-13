# Świstak AI Core — Etap 5: agent hybrydowy, panel i dziennik

**Status:** wdrożone na `main`, oczekuje na test Python 3.14.10 i odbiór użytkownika.  
**Cel:** aktywna kontrola rachunków bez utraty działania programu, gdy lokalny LLM jest niedostępny.

## Co dodano

- `ai_core/hybrid.py`: raport z odczytu SQLite, opcjonalna analiza przez
  lokalny model, kontrola nieaktualności danych, anulowanie oraz
  niewrażliwy dziennik pracy bieżącej sesji.
- `ai_core/hybrid_queue.py`: kolejka, scalanie takich samych zadań,
  pierwszeństwo ręcznej pełnej analizy; jedno zadanie wykonuje się naraz.
- `gui/agent_worker.py`: Qt QRunnable — wszystkie operacje DB i LLM
  poza głównym wątkiem, bez współdzielenia połączenia SQLite z GUI.
- `gui/panel_agenta.py`: Panel Agenta z wynikami, logiem, przyciskiem
  pełnej analizy, anulowaniem oraz kopiowaniem/eksportem logu.
- `gui/okno_glowne.py`: przycisk panelu w nagłówku i istniejącej
  zakładce AGENT, zlecenie analizy po starcie i po zapisie faktury.
- `i18n/pl.json`, `i18n/en.json`: tłumaczenia nowych kontrolek i wyników.

**Nie tworzymy siódmej karty nawigacji.** Obecny układ sześciu ekranów
i dwóch kart wewnątrz ANALIZA AI pozostaje bez zmian.

## Trzy tryby

1. **Przy starcie:** zadanie uruchamiane poza GUI po wyświetleniu okna.
   Najpierw deterministyczne odczyty; następnie sprawdzenie obecności
   wybranego lokalnego modelu i ewentualna analiza LLM.
2. **Po zapisie:** tylko wskazana faktura, na podstawie jej ID;
   `Tool Gateway` odrzuca próby otwarcia innych ID w tej sesji.
   Zadania tej samej faktury są scalane w kolejce.
3. **Ręcznie:** przycisk „Pełna analiza teraz”; ma pierwszeństwo przed
   zadaniami automatycznymi i anuluje bieżącą automatyczną analizę.

Kolejka ma limit 16 oczekujących prac. Zamknięcie okna lub świadome
anulowanie przerywa pracę best-effort i odrzuca spóźnione wyniki.
Sprawdzenie dostępności Ollamy ma osobny limit 2,5 s; generowanie LLM
zachowuje limit budżetu zadania, bez blokowania wątku GUI.

## Tryb awaryjny i deterministyczne liczby

Bez Ollamy pozostają dostępne:
- liczba aktywnych faktur;
- łączna kwota do zapłaty w całkowitych groszach;
- liczba faktur **po** terminie (od następnego dnia);
- liczba faktur płatnych dziś lub w ciągu 7 dni;
- liczba opłaconych faktur bez znanej daty zapłaty;
- liczba oczekiwanych, nierozstrzygniętych dokumentów.

Kontrola dnia wykorzystuje datę lokalną `Europe/Warsaw`, a datę
w JSON zadania narzuca aplikacja. Brak modelu nie oznacza kwot zero
dla istniejących rachunków.

## Granica bezpieczeństwa

1. Wszystkie dane pochodzą z otwartego `Tool Gateway` (`mode=ro`,
   `query_only=ON`); brak swobodnego SQL w modelu.
2. Model może żądać wyłącznie narzędzi o efekcie `read`.
3. Wynik jest związany z `data_revision`. Po zmianie bazy
   spóźnione, nieaktualne wnioski nie są pokazywane jako nowe.
4. Propozycje `mark_paid`, `withdraw_invoice` itd. wyświetlane są
   **wyłącznie jako tekst do przeglądu**. Nie dodano przycisku ich
   wykonania ani ścieżki zapisu.
5. Dziennik zawiera UTC, tryb, kroki (kontrola SQLite, stan Ollamy,
   analiza LLM), rodzaj zdarzenia i opcjonalne ID faktury.
   Nie przechowuje treści PDF, OCR, kont, SQL ani odpowiedzi modelu.
   Jest pamięciowy (bieżąca sesja), z limitowanym buforem 100 wpisów;
   użytkownik może skopiować lub ręcznie zapisać log do pliku TXT.
6. Żaden plik z danymi prywatnymi nie jest wysyłany do GitHub
   ani zewnętrznego dostawcy AI.

## Celowo poza Etapem 5

- Płatności i wycofywanie bezpośrednio z Panelu Agenta (niebezpieczne,
  bo wymagałoby niezależnego ekranu akceptacji).
- Pełny Plan rachunków i historia cykli w GUI — Etap 6.
- Automatyczne analizy po zmianach wykonanych **poza** bieżącym GUI
  (np. zewnętrznym skryptem).
- Długoterminowy dziennik wszystkich uruchomień LLM w bazie —
  bieżący log to wyłącznie metadane sesji.
- Test z prawdziwą Ollamą i modelem na komputerze użytkownika.

## Testy

```bash
python -m unittest testy.test_ai_core_stage5 -v
python -m unittest discover -s testy -v
```

Testy obejmują symulowaną niedostępność modelu, poprawne sumowanie,
pojedynczą fakturę, odrzucanie innych ID przez Tool Gateway,
próbę anulowania, priorytety kolejki, brak automatycznego zapisu
oraz dostępność Panelu Agenta w Qt. Używają wyłącznie syntetycznych danych.

## Odbiór

- [x] Trzy tryby analiz i nieblokujące GUI.
- [x] Ręczna analiza ma pierwszeństwo, zadania są scalane.
- [x] Tryb awaryjny oblicza prawdziwe wartości z SQLite.
- [x] Lokalny LLM korzysta z kontroli narzędzi i rewizji danych.
- [x] Panel z metadanymi i logiem, bez zapisów finansowych.
- [x] Zachowane działające formularze faktur, OCR, QR i W1–W4.
- [ ] Pełne CI na Pythonie 3.11 i 3.13.
- [ ] Test lokalny Python 3.14.10.
- [ ] Akceptacja użytkownika.

**Następnie Etap 6:** Plan rachunków, Historia i miesięczne zamknięcie
z wyjaśnieniem braków.
