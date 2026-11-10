# Dobór modelu Świstaka z pomocą AI Bobra

**Status: projekt integracji, bez zaimplementowanego połączenia.**

Projekty:
- [AI Bóbr](https://github.com/DarkZachi83/Bobr): ocena zgodności sprzętowej,
  benchmarki wydajności i jakości lokalnych modeli.
- [Świstak](https://github.com/DarkZachi83/Swistak): lokalna aplikacja do
  analizy rachunków metodą **LLM-first**, z Ollamą jako silnikiem.

## Współpraca

```text
AI Bóbr
   ├─ oszacowanie RAM/VRAM, kwantyzacji i kontekstu
   ├─ benchmark szybkości na komputerze użytkownika
   ├─ test polszczyzny, poprawności JSON i formatu
   └─ planowane testy z nauk ścisłych
                  ↓
         Krótka lista modeli
                  ↓
Benchmark Świstaka: ekstrakcja informacji z rachunków
                  ↓
Wybór modelu + ustawień dla lokalnej Ollamy
                  ↓
Świstak: analiza PDF → JSON → walidacja → akceptacja
```

Bóbr nie musi być uruchomiony podczas korzystania ze Świstaka. Świstak
nie importuje modułów Pythona z Bobra, nie łączy się z jego bazą SQLite
i nie powinien zależeć od prywatnych ścieżek katalogów innego programu.
W pierwszej wersji wystarczy **ręczny wybór modelu z Ollamy**, wsparty
wynikami Bobra. Import raportu z benchmarku dodamy dopiero po
uzgodnieniu stabilnego formatu wymiany danych.

## Stan AI Bobra sprawdzony przy planowaniu

Na dzień 2026-11-09 w repozytorium AI Bobra widoczne są:
- kalkulator pamięci i zgodności modelu ze sprzętem;
- benchmark wydajności z metrykami czasu/generowania;
- testy jakości w `aibobr/bench/quality.py`, m.in. polszczyzny,
  JSON i składni kodu;
- zestawy `data/benchmarks/pl_jezyk_v1.json` oraz
  `data/benchmarks/en_format_v1.json`;
- eksport metryk jakości i wydajności do CSV w
  `aibobr/bench/export.py`.

**Planowane testy wiedzy z nauk ścisłych** traktujemy jako przyszłe
rozszerzenie, nie jako istniejący już wynik. Testy gramatyczne i
ogólnej wiedzy pomagają porównać modele, ale same nie potwierdzają
poprawności ekstrakcji pól finansowych.

## Model bazowy do pierwszego testu

**`gemma3:4b`**, wybrany jako lokalny model testowy. Jego wynik na rachunkach syntetycznych stanie się punktem odniesienia dla kolejnych modeli. Docelowo wyniki zbierzemy wraz z identyfikatorem modelu, kwantyzacją i ustawieniami; nie kopiujemy rzeczywistych rachunków do AI Bobra.

## Wskaźniki potrzebne Świstakowi

1. **Możliwość uruchomienia:** model mieści się w pamięci z zapasem;
   znana jest kwantyzacja i rozmiar kontekstu.
2. **Wydajność:** czas przetworzenia typowego polskiego rachunku,
   szczególnie czas do pełnego JSON-a, nie tylko tokeny na sekundę.
3. **Poprawny JSON:** zgodność z wymaganym schematem, brak dodatkowej
   treści i obsługa brakujących wartości przez `null`.
4. **Jakość danych:** poprawne rozróżnienie kwoty do zapłaty od salda,
   nadpłaty i sumy pozycji; termin od daty wystawienia; numeru faktury
   od numeru konta; dat i okresów.
5. **Odporność:** fragmenty OCR z błędami, różne układy faktur,
   wielostronicowy PDF i brak pewnych danych.
6. **Powtarzalność:** model nie zmienia odpowiedzi w sposób, który
   uniemożliwia bezpieczne zatwierdzenie; zapisujemy identyfikator
   modelu, ustawienia, wersję testu i liczbę prób.

## Zestaw `rachunki_v1` — propozycja przyszłego benchmarku

Utworzyć **wyłącznie syntetyczne** przykłady rachunków:
energia, gaz, czynsz, telefon, fundusz remontowy. Każdy przykład
ma oczekiwane pola JSON i warianty: tekstowy PDF, skan/OCR,
kilka kwot, brak terminu, zerowe saldo lub nadpłata, nietypowy układ.

Wynik oceniać **osobno dla każdego pola**, m.in.:
- odsetek dokładnie poprawnych wartości;
- liczba błędów kwoty do zapłaty i rachunku bankowego;
- odsetek odpowiedzi zgodnych ze schematem;
- liczba zgadywanych wartości, których nie było w źródle;
- średni i maksymalny czas analizy.

Szczególnie poważne błędy (np. błędne konto lub kwota) nie powinny być
maskowane dobrą średnią ocen z języka i wiedzy. Nie ustalamy progów
kwalifikacji bez pomiarów na pierwszym korpusie testowym.

## Docelowy format wymiany

Gdy będziemy gotowi do wymiany wyników, uzgodnić wersjonowany plik
raportu (docelowo JSON z możliwością importu). Powinien zawierać:
- identyfikator modelu, tag/digest i kwantyzację;
- wielkość kontekstu, informacje o sprzęcie i dacie testu;
- wersje zestawów testowych, wyniki jakości i wydajności;
- ograniczenia oraz ostrzeżenia (np. częściowe uruchomienie w RAM).

**Nie umieszczamy w raporcie oryginalnych rachunków, tekstu OCR ani
numerów kont użytkownika.** Eksport powinien przenosić tylko metryki
i syntetyczne przykłady.

## Bezpieczeństwo i granice integracji

- Świstak odczytuje dostępne modele **lokalnie przez Ollamę**.
- Wynik benchmarku służy do rekomendacji, nie do automatycznych
  przelewów i nie znosi zatwierdzania pól przez człowieka.
- Walidatory kwot, dat i NRB/IBAN działają niezależnie od LLM.
- Gdy AI Bóbr lub Ollama nie są dostępne, zachowujemy możliwość
  ręcznej obsługi dokumentów. Nie ma fallbacku do chmurowego API.
- Nie kopiujemy między projektami całych modułów bez wyraźnej potrzeby.
