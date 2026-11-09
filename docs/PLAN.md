# Świstak — założenia i etapy

## Zasady
- Dokumenty i baza pozostają **lokalnie**; na GitHub trafiają tylko kod, dokumentacja i syntetyczne testy.
- Użytkownik kontroluje i zatwierdza wszystkie rozpoznane dane. Żaden model AI nie zapisuje zmian samodzielnie.
- Dokument PDF pozostaje nienaruszony w archiwum z SHA-256.
- Najpierw pozyskujemy tekst, potem interpretujemy go regułami lub opcjonalnym lokalnym LLM.
- Ręczne zaznaczanie myszą i edytowanie formularza są zawsze dostępne, również bez Ollamy.
- Moduły SQLite i archiwum wzorowane architektonicznie na Nornicy,
  interfejs wizualnie inspirowany AI Bobrem.
- Wszystkie etapy mają testy i osobne commity.

## Etap 0 — wykonany
Wielostronicowy podgląd PDF, zoom, zaznaczanie obszaru z normalizacją współrzędnych.
Ręczne potwierdzenie działania przez użytkownika.

## Etap 1 — baza i archiwum (gałąź robocza)
SQLite: `dokumenty`, `rachunki`, `pozycje_rachunku`, `kategorie`.
Kwoty jako całkowite grosze. Wersjonowane i sprawdzane SHA-256 migracje.
Archiwum PDF w katalogu użytkownika, deduplikacja SHA-256, ścieżki
względne, ponowna weryfikacja przy otwieraniu.
Import, formularz rachunku, ręczne dodawanie kategorii, lista dokumentów.
Przed scaleniem potrzebny test GUI na docelowym komputerze.

## Etap 2 — pozyskanie tekstu z PDF i OCR
- Jeśli PDF ma warstwę tekstową, czytamy ją bez OCR.
- Jeśli to skan: Tesseract/OCR z przygotowaniem obrazu, lokalnie.
- Pierwsza próba obejmuje cały dokument lub sensowną część strony, bez
  konieczności ręcznego zaznaczania każdego pola.
- Użytkownik może zaznaczyć fragment myszą i odczytać go ponownie, gdy
  automatyczna ekstrakcja zawiedzie lub będzie niejednoznaczna.
- Operacje w tle, z możliwością anulowania; wynik ekstrakcji zawsze
  można obejrzeć przed dalszą analizą.

## Etap 3 — lokalna analiza rachunku przez Ollamę (NOWY)
**Cel:** model zainstalowany lokalnie proponuje wypełnienie formularza
na podstawie tekstu z etapu 2. Nie dokonuje żadnego automatycznego zapisu.

Przepływ:
1. Użytkownik importuje PDF, a Świstak pobiera z niego tekst (warstwa
   tekstowa albo Tesseract dla skanu).
2. Jeśli Ollama jest dostępna na lokalnym `127.0.0.1:11434`, użytkownik
   wybiera zainstalowany model i uruchamia **Analizuj lokalnie (Ollama)**.
3. Model dostaje tekst jako **dane wejściowe**, a odpowiedzią jest
   **strukturalny JSON według schematu** (API `/api/chat`, pole `format`).
4. Świstak **samodzielnie** waliduje wartości, pokazuje źródłowe fragmenty
   tekstu i oznacza pola niepewne lub brakujące.
5. Użytkownik koryguje i zatwierdza sugestie, dopiero wtedy zapis do SQLite.
6. Jeśli model się myli lub Ollama nie działa, nadal dostępne są:
   ręczne zaznaczenie fragmentu PDF, OCR zaznaczenia i ręczny formularz.

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
- Gdy model jest niedostępny, aplikacja pozostaje w pełni użyteczna ręcznie.

Dokładny kontrakt JSON, walidacje i testy: [ETAP_3_OLLAMA.md](ETAP_3_OLLAMA.md).

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
