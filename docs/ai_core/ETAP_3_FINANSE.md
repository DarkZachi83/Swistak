# Świstak AI Core — Etap 3: model finansowy SQLite

**Stan:** implementacja modelu i testów syntetycznych na `main`; do odbioru użytkownika po CI.  
**Data:** 13.11.2026  
**Zakres:** schemat `003–005`, logika finansów, Plan rachunków, Historia cykli i audyt.

## 1. Zasada architektury

Świstak pozostaje **LLM-first**, ale SQLite jest źródłem prawdy. Agent czyta dane
przez `Tool Gateway` (bez prawa modyfikowania czegokolwiek). Użytkownik wyraźnie
zatwierdza zmianę, a usługa domenowa dokonuje jej w transakcji i zapisuje zdarzenie.

Nie dodajemy jeszcze formularzy płatności ani Panelu Agenta do GUI. Dotychczasowy
import PDF/OCR/Ollama działa niezależnie. Integracja z AI Core w etapach 4–5.

## 2. Migracje bazy

| Migracja | Zmiany |
|---|---|
| `003_platnosci_wycofanie.sql` | `data_oplacenia`, `wycofano_utc`, `powod_wycofania`, `wersja_rekordu`; indeksy |
| `004_plan_rachunkow.sql` | profile, wersje harmonogramów, oczekiwane dokumenty, powiązania faktur z oczekiwaniami |
| `005_cykle_audyt.sql` | potwierdzenia kompletności cykli i dziennik istotnych zmian |

Historyczne `001` i `002` pozostają **nienaruszone**. Istniejąca baza otrzymuje
spójny snapshot SQLite **przed każdą aktualizacją schematu**; dla nowej/pustej
bazy zbędny snapshot nie powstaje. Migracje są transakcyjne, sprawdzają SHA
oraz integralność kluczy obcych i `PRAGMA quick_check`.

Dotychczasowe opłacone faktury bez daty dostają **`data_oplacenia=NULL`**.
Program nie przypisuje im daty na podstawie terminu, OCR ani AI.

## 3. Operacje finansowe — `uslugi/finanse.py`

`Finanse.ustaw_oplacona(id, data)` — świadome oznaczenie opłacenia z faktyczną
datą; korekta daty tworzy osobne zdarzenie audytu.

`Finanse.cofnij_oplacenie(id, powod)` — przywraca status `do_zaplaty`,
czyści datę i rejestruje powód. Nie zmienia potwierdzenia kompletności
dokumentów; zmienia stan finansowego rozliczenia.

`Finanse.wycofaj(id, powod)` — **logiczne wycofanie**, zachowuje rekord,
oryginał PDF, status i datę płatności; faktura znika z aktywnego rejestru.
Nie ma trwałego usuwania pojedynczej faktury.

`Finanse.przywroc(id, powod)` — przywraca ten sam rekord i PDF po
sprawdzeniu możliwych konfliktów. Wycofanie/przywrócenie unieważniają
potwierdzoną kompletność odpowiednich miesięcy, w tym cykli powiązanych
z oczekiwaniami dokumentów.

Operacje mogą wymagać `expected_version`; nieaktualna wersja faktury
jest odrzucana.

### Zachowanie importu

W `RejestrRachunkow.zapisz_rachunek` ponowny import nie może
cofnąć wcześniej zapisanej płatności ani usunąć `data_oplacenia`.
Zmiana kwoty faktury już opłaconej wymaga świadomej flagi
`potwierdz_korekte_oplaconej=True`.

Próba nadpisania wycofanej faktury zostaje odrzucona —
użytkownik musi ją najpierw przywrócić.

## 4. Plan rachunków — `uslugi/plan_rachunkow.py`

Profile są tworzone **świadomie przez użytkownika**, oddzielnie dla każdej
zobowiązanej usługi. Nie tworzą automatycznie faktury ani należności.

Obsługiwane są harmonogramy miesięczne, co N miesięcy oraz nieregularne,
z datą aktywacji, kotwicą cyklu i przesunięciem początku oczekiwania.

Domyślnie oczekiwanie na rachunek za październik zaczyna się **1 listopada**.
Profile nieregularne nie tworzą automatycznych alarmów.

`generuj_oczekiwania(cykl)` jest idempotentną operacją domenową. Nie
wytwarza oczekiwań dla miesięcy sprzed aktywacji; na razie uruchamiana
jest jawnie. Automatyczne wywołanie przy starcie i zmianie miesiąca
to zadanie kolejnych etapów (Panel/Agent hybrydowy).

Można powiązać **kilka faktur z jednym oczekiwanym dokumentem**.
Dopasowanie jest osobną decyzją. Wyjątki `nie_wystawiono` i `niepewne`
dotyczą konkretnego okresu, nie tworzą zerowych kwot. Stan `niepewne`
nie jest uznany za rozstrzygnięcie braku.

Nowa wersja harmonogramu obowiązuje od wskazanego miesiąca; dawne
wersje i zmaterializowane oczekiwania pozostają śladem historycznym,
a zmiana retroaktywna unieważnia dotknięte potwierdzenia kompletności.

## 5. Historia i kompletność miesięcy

`Finanse.ocena_cyklu(RRRR-MM)` osobno oblicza:
- zakończenie miesiąca kalendarzowego,
- potwierdzenie kompletności przez użytkownika,
- liczbę aktywnych rachunków i nieopłacone kwoty,
- liczbę nierozstrzygniętych oczekiwań,
- stan `closed` — tylko gdy wszystkie wymagane warunki są spełnione.

`potwierdz_kompletnosc` materializuje wymagane oczekiwania
przed oceną, dlatego nie da się przypadkowo potwierdzić pustego
miesiąca mimo aktywnego harmonogramu. Nieopłacone faktury mogą
występować w miesiącu z potwierdzonym kompletem dokumentów, ale
taki miesiąc nie ma stanu `closed`.

Pusty miesiąc wymaga osobnego `brak_rachunkow=True`.
Zmiana zbioru dokumentów lub istotne zmiany profilu unieważniają
potwierdzenie, a zmiana samego statusu płatności tylko przelicza
rozliczenie finansowe.

Koszty przypisywane są do miesiąca końca okresu `okres_do`,
z zastępczym miesiącem wystawienia przy braku okresu.
Płatności do miesiąca rzeczywistej daty `data_oplacenia`.
Legacy `oplacony` bez daty nie trafia na wykres płatności.

## 6. Dziennik istotnych zmian

`dziennik_zdarzen` zawiera UTC, obiekt, operację, poprzednie i nowe
**kluczowe** wartości oraz powód. Zapis zdarzenia jest atomowy
z operacją, którą dokumentuje.

Dziennik nie przechowuje pełnych tekstów OCR/PDF ani numeru konta.
Poprzednia historia nie jest sztucznie odtwarzana.

Dodatkowo rejestrowane są istotne zmiany powiązań oczekiwań,
harmonogramów i scalania kategorii faktur.

## 7. Narzędzia AI

Tool Gateway nadal jest **wyłącznie odczytowy**. W nowym schemacie
działają wszystkie 12 narzędzi katalogu v1, także:
`plan.expected`, `plan.match`, `cycle.evaluate`, `audit.read`,
oraz agregacja `paid_date`.

Wyniki `verified` pochodzą tylko z weryfikacji deterministycznych,
rzeczywiście wykonanych narzędzi. Nie ma żadnej ścieżki `write SQL`
udostępnionej modelowi.

## 8. Testy i ograniczenia

```bash
python -m unittest testy.test_finanse_stage3 -v
python -m unittest discover -s testy -v
```

Testy wykorzystują wyłącznie fikcyjne rachunki i pliki PDF.
Szczegółowe przypadki: migracja `002→005`, backup przy migracji,
zachowanie daty płatności, logiczne wycofanie i przywrócenie,
zdarzenia, wersje rekordów, harmonogramy, oczekiwania,
pusty miesiąc, wyjątki oraz poprawność agregacji.

**Nie w tym etapie:** GUI płatności, pełna automatyka przy starcie,
test prawdziwej Ollamy z lokalnym modelem, płatności częściowe,
systemowe powiadomienia. Potrzebna nadal jest lokalna weryfikacja
na Pythonie 3.14 i świadomy odbiór użytkownika.

## 9. Kryteria odbioru

- [x] Migracje 003–005 bez zmian 001–002.
- [x] Automatyczna kopia starej SQLite przed migracją.
- [x] Płatności, wycofanie, przywrócenie i audyt transakcyjny.
- [x] Zabezpieczenie ponownego importu opłaconej faktury.
- [x] Plan rachunków, wersjonowane harmonogramy i powiązania.
- [x] Oddzielenie kompletności od opłacenia miesiąca.
- [x] Tool Gateway obsługuje nowy schemat i pozostaje tylko do odczytu.
- [ ] Końcowe GitHub Actions zaliczone na Pythonie 3.11 i 3.13.
- [ ] Testy lokalne Python 3.14 zgłoszone przez użytkownika.
- [ ] Akceptacja odbioru przez użytkownika.

**Etap 4 po odbiorze:** integracja istniejącego importu PDF/OCR/QR
z AI Core i wymiennymi modelami.
