# Świstak — założenia i etapy

## Zasady
- Dokumenty i baza pozostają **lokalnie**; na GitHub trafiają tylko kod, dokumentacja i syntetyczne testy.
- Użytkownik kontroluje i zatwierdza wszystkie rozpoznane dane. Żaden model AI nie zapisuje zmian samodzielnie.
- Dokument PDF pozostaje nienaruszony w archiwum z SHA-256.
- **LLM-first:** pozyskanie tekstu/OCR to tylko przygotowanie wejścia. Interpretację pól rachunku w pierwszej kolejności wykonuje **lokalny model LLM przez Ollamę**. Reguły wyodrębniania pól i ręczne zaznaczanie są planem awaryjnym, a nie równorzędną ścieżką podstawową. Osobne reguły **walidacji** wyników LLM (np. daty, kwoty, NRB/IBAN) działają zawsze.
- Ręczne zaznaczanie myszą i edytowanie formularza są zawsze dostępne, również bez Ollamy.
- Moduły SQLite i archiwum wzorowane architektonicznie na Nornicy,
  interfejs wizualnie inspirowany AI Bobrem.
- Wszystkie etapy mają testy i osobne commity.

## Etap 0 — wykonany
Wielostronicowy podgląd PDF, zoom, zaznaczanie obszaru z normalizacją współrzędnych.
Ręczne potwierdzenie działania przez użytkownika.

## Etap 1 — baza i archiwum (wykonany, scalony z main)
SQLite: `dokumenty`, `rachunki`, `pozycje_rachunku`, `kategorie`.
Kwoty jako całkowite grosze. Wersjonowane i sprawdzane SHA-256 migracje.
Archiwum PDF w katalogu użytkownika, deduplikacja SHA-256, ścieżki
względne, ponowna weryfikacja przy otwieraniu.
Import, formularz rachunku, ręczne dodawanie kategorii, lista dokumentów.
Przed scaleniem potrzebny test GUI na docelowym komputerze.

## Etap 2 — pozyskanie tekstu z PDF i OCR (wykonany, scalony z main)
- Jeśli PDF ma warstwę tekstową, czytamy ją bez OCR.
- Jeśli to skan: Tesseract/OCR z przygotowaniem obrazu, lokalnie.
- Pierwsza próba obejmuje cały dokument lub sensowną część strony, bez
  konieczności ręcznego zaznaczania każdego pola.
- Użytkownik może zaznaczyć fragment myszą i odczytać go ponownie, gdy
  automatyczna ekstrakcja zawiedzie lub będzie niejednoznaczna.
- Operacje w tle, z możliwością anulowania; uzyskany tekst będzie kierowany **w pierwszej kolejności do lokalnego LLM** w etapie 3, bez wstępnego rozpoznawania znaczenia pól za pomocą reguł. Wynik ekstrakcji można obejrzeć. W etapie 2 tekst nie trafia jeszcze automatycznie do formularza.
- Osobny eksperymentalny test CLI sprawdzi lokalnie model `gemma3:4b` na syntetycznej fakturze i zweryfikuje schemat JSON; nie zapisuje danych do SQLite.

## Etap 3 — główny silnik interpretacji: lokalny LLM przez Ollamę (gałąź robocza)
**Cel:** Świstak jest aplikacją opartą na lokalnym LLM. Model jako **pierwszy** interpretuje rachunek i proponuje wypełnienie formularza na podstawie tekstu z etapu 2. Nie dokonuje żadnego automatycznego zapisu.

**Kolejność interpretacji:** lokalny LLM → ocena/techniczna walidacja JSON → podgląd i potwierdzenie przez użytkownika. Dopiero przy braku Ollamy, błędzie modelu, pustym wyniku lub błędnej sugestii: prostsze reguły, ręczny wybór obszaru i wpisanie pól. Nie uruchamiamy analizy regułowej przed próbą modelu.

Przepływ:
1. Użytkownik importuje PDF, a Świstak pobiera z niego tekst (warstwa
   tekstowa albo Tesseract dla skanu).
2. Świstak domyślnie kieruje tekst do lokalnej Ollamy (`127.0.0.1:11434`) i wybranego modelu po poleceniu analizy. **To podstawowy mechanizm**, nie dodatek po parserze regułowym.
3. Model dostaje tekst jako **dane wejściowe**, a odpowiedzią jest
   **strukturalny JSON według schematu** (API `/api/chat`, pole `format`).
4. Świstak **samodzielnie waliduje** techniczną poprawność wartości (nie zastępuje tym interpretacji LLM), pokazuje źródłowe fragmenty tekstu i oznacza pola niepewne lub brakujące.
5. Użytkownik koryguje i zatwierdza sugestie, dopiero wtedy zapis do SQLite.
6. Dopiero gdy model się myli lub Ollama nie działa, uruchamiamy tryb awaryjny:
   reguły wyodrębniania danych, ręczne zaznaczenie fragmentu PDF, OCR zaznaczenia i ręczny formularz.

Wstępne pola: dostawca, numer dokumentu/faktury, kwota **do zapłaty**,
waluta, data wystawienia, termin płatności, okres rozliczeniowy,
**numer rachunku bankowego** (osobny od numeru faktury), sugerowana kategoria.
Nieznane dane oznaczamy `null`, zamiast zgadywać.

Bezpieczeństwo:
- Bez wysyłania tekstu rachunku poza komputer — domyślnie tylko
  lokalne API Ollamy. Bez automatycznego pobierania modeli.
- Numer konta i kwota muszą zostać sprawdzone przed zatwierdzeniem.
  NRB/IBAN, kwoty i daty weryfikujemy niezależnie od LLM.
- Świstak **nie wykonuje przelewów**, nie składa dyspozycji bankowych i
  nie zapisuje niczego automatycznie na podstawie samego JSON.
- Model może pomylić kwotę zapłaty z saldem lub pomylić numery faktury
  i konta. Dlatego pokazujemy dowody tekstowe i wymagamy kontroli człowieka.
- Pole numeru konta w SQLite powstanie dopiero w osobnej migracji
  przy implementacji etapu 3; nie zmieniamy wstecz migracji 001.
- Model lokalny jest domyślnym i docelowym silnikiem programu; gdy jest niedostępny, aplikacja nadal pozwala pracować ręcznie, bez chmurowego zamiennika.

Dokładny kontrakt JSON, walidacje i testy: [ETAP_3_OLLAMA.md](ETAP_3_OLLAMA.md).

**Wersja testowa etapu 3:** zakładka Analiza AI, lokalne żądania do Gemmy 3 4B, osobne walidacje wartości, przenoszenie propozycji do formularza po potwierdzeniu. Migracja 002 dodaje numer konta bankowego. Automatyczny zapis bez decyzji użytkownika nie jest dopuszczony. Test na komputerze użytkownika i skany OCR są warunkami zamknięcia etapu.

### Dobór modelu: AI Bóbr → Świstak

[AI Bóbr](https://github.com/DarkZachi83/Bobr) jest **zewnętrznym narzędziem
do oceny i porównywania lokalnych modeli**, a Świstak uruchamia wybrany model
przez Ollamę. Dobór obejmuje zgodność z komputerem, szybkość,
polszczyznę, format JSON oraz — po dodaniu w Bobrze — testy nauk ścisłych.
Wybór końcowy wymaga dodatkowego testu **ekstrakcji pól z rachunków**,
którego wyniku nie zastępuje ocena wiedzy ogólnej.

Integracja ma być **luźna**: Świstak nie importuje modułów AI Bobra i
nie wymaga uruchomionego Bobra. Docelowo może odczytać wyeksportowany
raport z wynikami benchmarku, a listę dostępnych modeli pobierze
bezpośrednio z lokalnej Ollamy. Szczegóły:
[WYBOR_MODELU_AI_BOBR.md](WYBOR_MODELU_AI_BOBR.md).

## Etap 4 — historia, statystyki i kopie zapasowe
Filtrowanie rachunków, sumy miesięczne; kopia spójnej migawki SQLite
i oryginałów PDF z manifestem SHA-256 oraz sprawdzane przywracanie.
**Przed zapisaniem prawdziwych danych finansowych trzeba zapewnić
bezpieczną kopię zapasową** — nawet jeśli pełny interfejs backupu
zostanie wykonany na tym etapie.

## Etap 5 — szablony dostawców
Zapamiętywanie układu dokumentu, potwierdzanie odczytu,
dopiero po sprawdzeniu dokładności odczytu z różnych rachunków.

## Poza zakresem
Bankowość/wykonywanie przelewów, chmura, telemetria, automatyczny e-mail,
powiadomienia i rozbudowane hierarchie kategorii.
