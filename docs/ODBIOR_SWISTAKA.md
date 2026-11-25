# Świstak — odbiór na prawdziwych rachunkach

## Przygotowanie

Przygotuj lokalnie PDF z warstwą tekstową, skan bez warstwy tekstowej i dwie kolejne faktury jednego dostawcy. Jeden plik może spełniać kilka z tych warunków. Jeżeli masz fakturę z obsługiwanym kodem QR płatności, użyj jej w próbie QR. Do porównania Statystyk wybierz fakturę opłaconą w innym miesiącu niż miesiąc usługi.

Poniższe uruchomienie tworzy nowy katalog testowy poza repozytorium. Rozdziela bazę, ustawienia i kopie od dotychczasowych danych Świstaka. Katalog zostaje na dysku po zakończeniu programu, więc możesz wrócić do tej samej sesji.

```bash
cd /mnt/dane/Python/Projekty/Swistak/Swistak
git pull --ff-only origin main
git rev-parse --short HEAD
./.venv/bin/python --version
./.venv/bin/python -m unittest discover -s testy -v
odbior_dir="$(mktemp -d "$HOME/Swistak-odbior.XXXXXX")"
printf 'Katalog odbioru %s\n' "$odbior_dir"
```

Wykonaj poniższą komendę przy pierwszym uruchomieniu i przy każdym wznowieniu. Jeśli otworzysz nowy terminal, najpierw ustaw `odbior_dir` na ścieżkę wypisaną wyżej. Ścieżka w komunikacie startowym powinna wskazywać `data/Swistak-Test-main` wewnątrz tego katalogu.

```bash
XDG_DATA_HOME="${odbior_dir:?Ustaw katalog odbioru}/data" XDG_CONFIG_HOME="$odbior_dir/config" \
  PYTHONFAULTHANDLER=1 ./uruchom.sh --test
```

W **Ustawieniach** wybierz używany model z lokalnej Ollamy i kliknij **Zapisz**. Ustawienia w tym katalogu zaczynają od wartości domyślnych. Jeżeli testujesz specjalistę od ekstrakcji, zapisz także jego nazwę. Przy próbie pełnej analizy w Panelu Agenta użyj modelu, dla którego Ollama deklaruje obsługę narzędzi.

## Przepływ dokumentu

| Próba | Czynność | Wynik oczekiwany |
| --- | --- | --- |
| PDF i skan | Otwórz po kolei oba dokumenty przez **Nowa faktura → Importuj PDF → Odczytaj cały PDF**. | PDF z tekstem korzysta z warstwy tekstowej, skan z OCR. Otwarty PDF ma prawidłową liczbę stron. |
| Analiza i korekta | Uruchom analizę AI bez OCR na modelu vision, a następnie powtórz z OCR. Porównaj dostawcę, numer, kwotę, termin i okres z PDF-em. Pola z obrazu niepotwierdzone przez OCR potwierdź ręcznie. Przenieś wyłącznie zweryfikowane pola i popraw formularz. | Kwoty i daty zgadzają się z dokumentem po korekcie. Przed kliknięciem **Zapisz fakturę** zaimportowany dokument jest dostępny w **Dokumentach**, a nowej pozycji w **Moich fakturach** jeszcze nie ma. |
| Nawigacja | Przed zapisem przejdź przez **Pulpit → Historia → Ustawienia → Nowa faktura**, przełącz PL/EN i zmień szerokość okna. | Wracasz do tego samego dokumentu, strony PDF-u, etapu i treści formularza. |
| Zapis i duplikat | Zapisz zatwierdzoną fakturę. Otwórz ją ponownie w **Moich fakturach**, zmień np. testową uwagę i ponownie wybierz zapis. W pierwszej próbie odmów nadpisania. | W tabeli jest jeden rekord dla tej faktury. Odmowa zostawia zapisane dane w dotychczasowej postaci. Świadome nadpisanie w drugiej próbie aktualizuje ten sam rekord. |
| QR, jeśli dotyczy | Kliknij **Odczytaj QR** i porównaj kwotę oraz konto z PDF-em. Najpierw zamknij okno, potem powtórz próbę i potwierdź przeniesienie. | Zamknięcie nie zmienia formularza. Potwierdzenie przenosi dane do formularza, który nadal wymaga ręcznego zapisu faktury. |
| Wzorce W1–W4 | Po zapisie i odczycie pierwszej faktury utwórz i zatwierdź wzorzec. Odczytaj kolejną fakturę tego dostawcy. Jeśli aplikacja pyta o użycie wzorca, zaakceptuj. Po zapisie zaproponuj aktualizację i zatwierdź ją. | Wzorzec jest rozpoznany i widoczny w analizie. Kwota i daty pochodzą z nowej faktury. Menedżer wzorców pokazuje aktualną i wcześniejszą rewizję. |

## Rozliczenie

Przy porównaniu zapisz sobie lokalnie kwotę faktury, miesiąc końca usługi, faktyczną datę płatności i stan pozostałych faktur w tych miesiącach. Porównuj wyniki tej samej faktury albo zmianę sumy o jej kwotę.

| Próba | Czynność | Wynik oczekiwany |
| --- | --- | --- |
| Należności i terminy | Zapisz fakturę ze statusem **Do zapłaty**. Sprawdź Pulpit i skrót **Pokaż faktury** w odpowiednim kafelku. | Faktura zwiększa należności o swoją kwotę. Termin wcześniejszy niż dziś trafia do **Po terminie**, dziś i najbliższe 7 dni do **Płatne dziś i przez kolejne 7 dni**. Faktura bez terminu jest w należnościach ogółem. |
| Plan i kompletność | Dla zakończonego miesiąca utwórz pasujący profil, kliknij **Utwórz oczekiwania** i użyj **Powiąż fakturę**. W **Historii → Zamknięcie miesiąca** potwierdź komplet dokumentów. | Plan pokazuje otrzymaną fakturę. Jeżeli pozostaje aktywna nieopłacona faktura, miesiąc pokazuje potwierdzone dokumenty i otwarte rozliczenie finansowe. |
| Faktyczna płatność | W **Historii** wskaż fakturę i wybierz **Oznacz jako opłacony**. Podaj faktyczną datę i potwierdź. | Kwota znika z bieżących należności. W Historii widać datę i wpis w dzienniku zmian. Pulpit pokazuje opłacony rachunek według miesiąca usługi oraz faktyczną płatność według daty zapłaty. |
| Statystyki | Obejmij oba miesiące zakresem. Przełącz **Miesiąc usługi** na **Faktyczna płatność**. Sprawdź filtry kategorii i dostawcy. | Kwota faktury przypada na miesiąc usługi w pierwszym widoku i miesiąc zapłaty w drugim. Wyniki tabeli i wykresu są zgodne z zastosowanymi filtrami. |
| Agent | Przy działającej Ollamie poczekaj na kontrolę po uruchomieniu. W **Agencie AI** wybierz także **Pełna analiza teraz**. | Pulpit pokazuje stan kontroli i skonfigurowany model. Panel odróżnia wynik lokalny, dostępność modelu oraz ewentualny błąd analizy. Samo uruchomienie analizy nie zmienia płatności ani zapisanych faktur. |

## Kopia, powrót i zgłaszanie uwag

1. Wybierz **Plik → Utwórz kopię zapasową…**. Zapisz ZIP w katalogu odbioru, obok folderu `data`. Kopia zawiera prywatne PDF-y i bazę w postaci nieszyfrowanej.
2. Zmień testową uwagę w jednej zapisanej fakturze, po czym przywróć kopię przez **Plik → Przywróć kopię zapasową…**. Sprawdź, czy wcześniejsza uwaga, PDF, wzorzec i data płatności wróciły po otwarciu nowego okna.
3. Jeżeli chcesz sprawdzić pełne czyszczenie, wykonaj je w tej nowej bazie odbiorczej po odtworzeniu kopii. Sprawdź działanie obowiązkowego ZIP-u i przywróć próbkę. Użyj osobnych nazw dla kolejnych kopii.
4. Zamknij program po zwykłej pracy, a następnie po rozpoczęciu OCR. Program powinien wrócić do terminala po zakończeniu anulowania, bez `bus error` lub błędu segmentacji.

Do przekazania wystarczą numer commita, wersja Pythona, użyte modele, nazwa próby, wynik i kroki odtworzenia. Jeśli prześlesz zrzut lub fragment logu, zasłoń dane faktury i prywatne ścieżki. PDF-y, bazy i kopie ZIP zachowaj lokalnie.
