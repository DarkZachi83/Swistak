# Świstak AI Core — Etap 6: Plan rachunków, Historia i zamknięcie miesiąca

**Status:** funkcje wdrożone na `main`; oczekują na lokalny odbiór użytkownika.  
**Zakres:** graficzna obsługa tabel z migracji 003–005, bez nowej migracji SQLite.

## 1. Gdzie znaleźć nowe funkcje?

W głównym oknie wybierz przycisk **Plan / Historia** (nagłówek) albo
**Ustawienia → Plan rachunków i Historia**. Otwiera się jedno okno
`gui/dialog_plan_historia.py` z trzema kartami: **Plan rachunków**,
**Historia** i **Zamknięcie miesiąca**.

Dotychczasowa nawigacja OCR → ANALIZA AI → EDYCJA → FAKTURA →
DOKUMENTY → FAKTURY pozostaje bez zmian. Okno ma wersje językowe PL i EN.

## 2. Plan rachunków

**Profil rachunku** opisuje oczekiwany dokument, nie kwotę do zapłaty.
Każdy profil może mieć nazwę, dostawcę, kategorię i harmonogram:

- **Miesięczny:** co miesiąc;
- **Co N miesięcy:** od wskazanej kotwicy cyklu (np. co dwa);
- **Nieregularny:** bez automatycznego zgłoszenia braków.

Miesiąc obowiązywania, kotwica i przesunięcie dnia oczekiwania
można ustawić w formularzu. Domyślnie dla dokumentu za październik
oczekiwanie zaczyna się **1 listopada**, ale to nie jest termin zapłaty.

Użytkownik może stworzyć profil, dodać **nową wersję** harmonogramu,
wstrzymać albo wznowić profil. Starsze wersje, istniejące oczekiwania
i faktury **nie są usuwane**. Po zmianie danych aplikacja odświeża
podglądy i zleca kontrolę hybrydową z Etapu 5.

Po wybraniu miesiąca przycisk **Utwórz oczekiwania** materializuje
brakujące wiersze w bazie. Jest to jawna, idempotentna operacja
— **nie tworzy nowej faktury ani kwoty zerowej**.

Oczekiwany dokument może mieć status:
`received` (powiązana aktywna faktura),
`not_issued` (świadomie wyjaśniony brak),
`uncertain` (wymaga weryfikacji),
`missing` (minął początek oczekiwania) albo
`waiting` (jeszcze oczekujemy).

Można połączyć kilka aktywnych faktur **z tego samego okresu**
z jednym oczekiwaniem, odłączyć powiązanie, wyjaśnić brak
lub cofnąć wcześniejsze wyjaśnienie. Wszystkie takie zmiany
wymagają świadomego działania użytkownika. Połączenie z fakturą
z innego miesiąca lub z wycofaną fakturą jest blokowane.

## 3. Historia i finanse

Historia jest przeliczana bez zgadywania daty opłacenia:

- **Suma faktur:** wszystkie aktywne faktury przypisane do miesiąca
  końca okresu rozliczenia (zastępczo miesiąca wystawienia).
- **Opłacone za miesiąc usługi:** faktury z tego okresu
  ze statusem `oplacony` (nawet jeśli data płatności była nieznana).
- **Pozostało do zapłaty:** aktywne faktury z tego okresu
  o statusie `do_zaplaty`.
- **Płatności dokonane w danym miesiącu:** tylko opłacone
  faktury z rzeczywiście znaną datą `data_oplacenia` w tym miesiącu,
  niezależnie od miesiąca usługi.
- **Faktury wycofane:** nadal widoczne w Historii ze znacznikiem;
  wyłączone z aktywnych sum.
- **Dziennik zmian:** czasy UTC, rodzaj zdarzenia, powód,
  zmiany faktur dotyczących okresu lub płatnych w wybranym miesiącu,
  oczekiwań i odpowiednich profili.

Faktury z wcześniejszym statusem `oplacony`, ale bez rzeczywistej
daty zapłaty, pozostają bez tej daty; program jej nie zgaduje.

W Historii dostępne są świadome operacje:
**Oznacz jako opłacony** (wybór rzeczywistej daty),
**Cofnij opłacenie** (wymagany powód),
**Wycofaj fakturę** (logicznie) i **Przywróć fakturę**.
Każda operacja wymaga osobnego potwierdzenia; SQLite kontroluje
`wersja_rekordu` i zapisuje wpis dziennika w tej samej transakcji.
Sama otwarta Historia nie modyfikuje bazy.

## 4. Zamknięcie miesiąca — dwa niezależne warunki

**Potwierdzenie kompletu dokumentów NIE oznacza opłacenia rachunków.**

1. Wybierz zakończony miesiąc.
2. Sprawdź oczekiwania (w razie potrzeby wygeneruj je z profili).
3. Dopasuj otrzymane rachunki lub świadomie oznacz wyjątki
   `nie_wystawiono` wraz z powodem.
4. Stan `niepewne` i każdy niepowiązany, niewyjaśniony dokument
   blokują potwierdzenie kompletności — **także wtedy, gdy jeszcze
   nie nadszedł początek oczekiwania**.
5. Jeśli w danym miesiącu nie ma żadnych faktur, dodatkowo zaznacz
   checkbox świadomego potwierdzenia braku rachunków.
6. Kliknij **Potwierdź komplet dokumentów** i potwierdź
   finalne pytanie. Nastąpi zapis `cykle_rozliczeniowe`
   oraz zdarzenia audytu.

Po potwierdzeniu kompletności miesiąc nadal pozostaje finansowo
**otwarty**, jeśli istnieją aktywne, nieopłacone faktury.
Stan `closed` oznacza dopiero jednocześnie: miesiąc zakończony,
potwierdzone dokumenty, brak nierozstrzygniętych oczekiwań
i brak nieopłaconych faktur.

Późniejsze dodanie/wycofanie faktury, zmiana oczekiwań
lub istotna aktualizacja harmonogramu mogą automatycznie
**unieważnić** wcześniejsze potwierdzenie kompletności.
Zmiana samego statusu płatności nie cofa kompletności dokumentów,
ale przelicza rozliczenie finansowe.

## 5. Bezpieczeństwo i zakres

- LLM **nie posiada** ścieżki zapisu do metod finansowych ani
  powiązań planu. Kliknięcia i potwierdzenia wykonuje człowiek.
- Historia, PDF/OCR i numer konta pozostają lokalne.
- Nowe operacje nie wykonują swobodnego SQL przez model.
- Nie zmieniono migracji 001–005; zachowane są kopie zapasowe
  i ręczny import faktur W1–W4.
- UI nie wykonuje automatycznego importu ani automatycznych płatności.
- Obliczenia działają również bez Ollamy.
- Lista faktur i dziennika ma limity wyświetlania (do 500 faktur
  i 200 zdarzeń na wybrany okres); sumy miesiąca liczone są na
  całych aktywnych rekordach.

## 6. Testy i odbiór

```bash
python -m unittest testy.test_finanse_stage6 -v
python -m unittest discover -s testy -v
```

Testy syntetyczne sprawdzają m.in. sumy według okresu, daty
faktycznych płatności, logiczne wycofanie i przywrócenie,
powiązania między miesiącami, przyszłe oczekiwania,
cofanie wyjątków, rozdzielenie kompletności i opłacenia,
odmowę operacji i trzy karty interfejsu Qt.

- [x] Plan rachunków i wersjonowane harmonogramy w GUI.
- [x] Powiązania, wyjaśnienia braków i odwracanie wyjątków.
- [x] Historia, rzeczywiste daty płatności i transakcyjny audyt.
- [x] Rozdzielenie kompletności od finansowego zamknięcia.
- [x] Dialogi wymagające potwierdzenia zmian; brak samodzielnych zapisów AI.
- [x] Testy syntetyczne na istniejącym schemacie SQLite.
- [x] GitHub Actions `43502518347`: **282 testy OK** na Pythonie 3.11 i 3.13 (commit `0f34855`).
- [ ] Lokalny wynik Python 3.14.10.
- [ ] Odbiór przez użytkownika.

**Etap 7 po odbiorze:** opcjonalne role specjalistycznych modeli;
agent główny zachowuje odpowiedzialność za orkiestrację.
