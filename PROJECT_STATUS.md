# Świstak — PROJECT_STATUS

## Ustawienia — lokalne wyszukiwanie modeli na wzór AI Bobra (13.11.2026)

**Wdrożono:** edytowalną listę modeli w Ustawieniach, przycisk „Szukaj modeli lokalnych…”, wyszukiwanie standardowych lokalizacji lub wybranego folderu, zapamiętanie folderu w `settings.json`, asynchroniczny skan ograniczony liczbą plików i głębokością. Wyszukiwarka rozpoznaje Ollamę przez localhost `/api/tags`, magazyny manifestów Ollamy, GGUF oraz katalogi tekstowych modeli Transformers (HF) z `config.json` i wagami. Tylko model widoczny w działającej lokalnej Ollamie można wybrać bezpośrednio; pliki dyskowe nie są automatycznie importowane ani uruchamiane. Nie zmieniano bazy, OCR ani Agenta.

**Testy:** `testy/test_ustawienia_modele.py`, `testy/test_modele_lokalne.py`, `testy/test_dialog_modele_lokalne.py`. Odbiór lokalny na Pythonie 3.14.10 i kontrola UX pozostają do wykonania. [Instrukcja](docs/MODELE_LOKALNE.md).

## AI Core 1.0 — Etap 7 (13.11.2026)

**Wdrożono:** cztery opcjonalne role modeli lokalnych Ollamy w Ustawieniach (`extractor`, `verifier`, `financial_analyst`, `cycle_analyst`) z trwałymi przypisaniami w `settings.json`. Ekstrakcja PDF korzysta już z wybranego eksperta; Agent hybrydowy najpierw uruchamia model główny, a następnie kolejne kontrole specjalistyczne. Ustalenia specjalistów trafiają do Panelu Agenta osobno; ich propozycje akcji nie są w ogóle przekazywane do UI.

**Reguły:** brak specjalisty = bez zmian w dotychczasowym działaniu; specjalista niedostępny = zachowanie wyniku głównego. Każda kontrola tylko przez Tool Gateway, osobny task i wersję danych; brak dostępu do zapisu SQLite. Analiza pojedynczej faktury wyklucza całościowego specjalistę cykli. Testy syntetyczne: `testy/test_ai_core_stage7.py`. CI końcowego commita i lokalny odbiór Python 3.14.10 do potwierdzenia. [Dokumentacja](docs/ai_core/ETAP_7_SPECJALISCI.md).

## AI Core 1.0 — Etap 6 (13.11.2026)

**Wdrożone:** GUI `gui/dialog_plan_historia.py` (trzy karty Plan / Historia / Zamknięcie), `uslugi/historia.py` (sumy, kalendarz płatności, audit, statusy oczekiwań), uzupełnione operacje `PlanRachunkow.ustaw_aktywnosc`, `anuluj_wyjatek` oraz granice powiązań. Historia rozróżnia miesiąc usługi od rzeczywistego miesiąca płatności, pokazuje wycofane dokumenty bez zaliczania ich do bieżących sum.

**Zamykanie:** kontrola wszystkich nierozstrzygniętych oczekiwań, w tym jeszcze niewymagalnych, świadome potwierdzenie pustego miesiąca i osobne potwierdzenie kompletności. Pełne rozliczenie finansowe wymaga jednocześnie opłacenia wszystkich aktywnych faktur. Brak samodzielnego zapisu LLM, nowej migracji ani zmian w OCR.

**Testy:** GitHub Actions `43502518347` — **282 testy OK na Pythonie 3.11 i 3.13** (commit `0f34855`). Lokalna weryfikacja Python 3.14.10 i odbiór użytkownika pozostają do wykonania. [Dokumentacja i kryteria](docs/ai_core/ETAP_6_PLAN_HISTORIA.md).

## AI Core 1.0 — Etap 5 (13.11.2026)

**Wdrożono:** agent hybrydowy (`ai_core/hybrid.py`), kolejkę z priorytetami, zadania Qt, osobny Panel Agenta, dziennik metadanych oraz tryby `startup`, `change` i `manual`. Zapis faktury wyzwala kontrolę tylko jej ID; ręczna analiza może anulować automatyczną.

**Bez Ollamy** działają sumy, zaległości, terminy i oczekiwane dokumenty z SQLite. **Z Ollamą** agent może tylko czytać przez Tool Gateway i pokazać propozycje bez możliwości zapisania ich z panelu. Brak zmian schematu SQLite i istniejącego formularza OCR.

**Testy i odbiór:** GitHub Actions `43447801954`: **266 testów OK na Pythonie 3.11 i 3.13** (commit `463eedc`). Pozostaje lokalny test Python 3.14.10 i odbiór użytkownika. Dokumentacja: [docs/ai_core/ETAP_5_AGENT_HYBRYDOWY.md](docs/ai_core/ETAP_5_AGENT_HYBRYDOWY.md).

## AI Core 1.0 — Etap 4 (13.11.2026)

**Zaimplementowano:** bieżący formularz AI po analizie OCR korzysta teraz z `uslugi/analiza_ai_core.py`, `ModelRouter` i metody `OllamaProvider.generate_structured`. Zatwierdzone wzorce W1–W4, QR i cały mechanizm ręcznej akceptacji pozostały nienaruszone. Zadanie Qt może anulować aktywny transport; nie ma automatycznych zapisów do SQLite.

**Kompatybilność:** `uslugi/analiza_llm.py` zawiera nadal starą, testowaną ścieżkę narzędziową, ale wykorzystuje ten sam prompt co nowy provider. Opcjonalna rola `extractor` jest dostępna przez API, nie ma jeszcze osobnego wyboru w GUI.

**Testy:** `testy/test_ai_core_stage4.py`, symulowana lokalna Ollama i regresja. Dokumentacja: [docs/ai_core/ETAP_4_INTEGRACJA.md](docs/ai_core/ETAP_4_INTEGRACJA.md). GitHub Actions `43443677093`: 256 testów OK na Pythonie 3.11 i 3.13 (commit `ff50bef`). Pozostaje lokalny odbiór na Pythonie 3.14.10 i świadoma akceptacja użytkownika.

## AI Core 1.0 — Etap 3 (13.11.2026)

**Wdrożono model finansowy i Plan rachunków:** migracje `003_platnosci_wycofanie.sql`, `004_plan_rachunkow.sql`, `005_cykle_audyt.sql`, usługi `uslugi/finanse.py` i `uslugi/plan_rachunkow.py`, integrację rejestru i pełny audyt materiałowych operacji. Tool Gateway ma odczyt nowych tabel. Przed zmianą schematu wykonywany jest snapshot istniejącej SQLite.

**Reguły:** wyłącznie logiczne wycofanie, daty płatności podaje człowiek, brak utraty opłacenia podczas ponownego importu, niezmienne migracje 001/002, profile bez tworzenia fikcyjnych należności, potwierdzenie kompletności oddzielone od płatności. Wszystkie nowe funkcje przetestowano na danych syntetycznych.

**Stan:** kod i testy etapu 3 na `main`; GitHub Actions końcowego commita i lokalny test Python 3.14 do potwierdzenia; wymagana akceptacja użytkownika. Dokumentacja: [docs/ai_core/ETAP_3_FINANSE.md](docs/ai_core/ETAP_3_FINANSE.md).

## AI Core 1.0 — Etap 2 (13.11.2026)

**Wdrożono:** `ai_core/gateway.py`, odczyt istniejącej bazy przez narzędzia kontraktu v1, kontrolę dowodów, pętlę natywnych `tool_calls` w Ollamie i testy syntetyczne `testy/test_ai_core_stage2.py`. Dokumentacja: [docs/ai_core/ETAP_2_TOOL_GATEWAY.md](docs/ai_core/ETAP_2_TOOL_GATEWAY.md).

**Bezpieczeństwo:** brak dowolnego SQL, brak operacji zapisu, kontrola dnia odniesienia i rewizji bazy, brak fikcyjnych wyników dla niedostępnych tabel. Nie zmieniono migracji, GUI ani starszego importu.

**Weryfikacja:** pierwsze GitHub Actions po implementacji `43415835779` — sukces na Pythonie 3.11 i 3.13. Końcowe GitHub Actions `43416285049` — **sukces na Pythonie 3.11 i 3.13** (commit `58439b5`). Test rzeczywistej Ollamy na komputerze użytkownika pozostaje do wykonania. Odbiór etapu przez użytkownika — oczekiwany.

## AI Core 1.0 — Etap 1 (13.11.2026)

**Wdrożono szkielet:** `ai_core/` — kontrakty, adapter lokalnej Ollamy, router modeli i orkiestrator (kolejka/anulowanie/stream). Testy syntetyczne: `testy/test_ai_core_stage1.py`. Opis: [docs/ai_core/ETAP_1_OLLAMA.md](docs/ai_core/ETAP_1_OLLAMA.md). 

**Granice:** wciąż brak Tool Gateway, integracji z GUI, nowych migracji i zapisu finansów. Stary import pozostaje niezmieniony. GitHub Actions `43413016614` po commicie `8544413`: pełny zestaw testów i audyt zależności **sukces na Pythonie 3.11 i 3.13**. Następny etap wymaga odbioru użytkownika. Test rzeczywistego lokalnego modelu na komputerze użytkownika pozostaje odrębnym testem akceptacyjnym.

## NOWY PROGRAM PRAC — AI Core 1.0 / Etap 0 (13.11.2026)

**Zatwierdzone przez użytkownika:** specyfikacja AI Core 1.0; jeden główny LLM + opcjonalne modele specjalistyczne; hybrydowa analiza (start / zmiana / ręcznie); lokalna praca i tryb ograniczony bez LLM; użytkownik potwierdza zmiany finansowe.

**Przygotowane w Etapie 0:** [docs/ai_core/README.md](docs/ai_core/README.md), kontrakt JSON Schema v1, katalog narzędzi tylko do odczytu, syntetyczne przykłady i testy `testy/test_ai_core_contracts.py`. To **projekt kontraktów**; runtime agenta, adapter Ollamy, migracje, GUI i operacje finansowe **nie zostały zmienione**.

**Sprawdzone:** GitHub Actions `43408966854` zakończone sukcesem na Python 3.11 i 3.13 po commicie `731fdf3`. **Pozostaje:** odbiór Etapu 0 przez użytkownika. Kolejny etap po odbiorze: orkiestrator i adapter Ollamy. Pełne kryteria: [docs/ai_core/ETAP_0_ODBIOR.md](docs/ai_core/ETAP_0_ODBIOR.md).

**Uwaga:** poniższe fragmenty dotyczą wcześniejszych etapów importu. Nazwa „Etap 0” w historycznym `docs/PLAN.md` odnosi się do podglądu PDF, nie do nowego AI Core.


**Ostatnia weryfikacja:** 2026-11-12  
**Repozytorium:** `DarkZachi83/Swistak` · **gałąź:** `main`  
**Punkt odniesienia:** commit `7b5894b994ed987337fac352a118b659d1c68bd1` (czyszczenie bazy i testy, przed aktualizacją statusu).  
**Wersja w `wersja.py`:** `0.1.0b1` / `0.1.0 Beta 1`.

> To dokument przekazania prac między sesjami programistycznymi i asystentami AI. **Kod na bieżącym HEAD `main` jest nadrzędny**; przed wznowieniem trzeba porównać ten dokument z repozytorium i ostatnimi commitami. Sam wpis „wykonane” nie zastępuje testu na komputerze użytkownika.

## Zrealizowane i obecne w kodzie `main`

- Lokalny rejestr SQLite, wersjonowane migracje, oryginalne PDF-y przechowywane w prywatnym archiwum, SHA-256 i rozpoznawanie identycznego importu.
- Przełączanie okien po **Przywróć kopię** i **Wyczyść bazę danych**: poprzednie okno jest ukrywane przed pokazaniem nowego, a następnie zamykane przed modalnym komunikatem. Zapobiega to migotaniu i chwilowemu wyświetlaniu dwóch okien; test GUI sprawdza kolejność i widoczność.
- **Wyczyść bazę danych…** w menu Plik: najpierw ostrzeżenie „UWAGA! Komenda spowoduje wymazanie wszystkich danych! Utwórz najpierw kopię zapasową.”, potem obowiązkowa pełna kopia ZIP i próba jej weryfikacji, wpisanie frazy, końcowe potwierdzenie, nowa pusta baza z sześcioma kategoriami podstawowymi. Usuwane są faktury, PDF-y, wzorce i własne kategorie. Ustawienia i kopia ZIP pozostają. Awarię podmiany można cofnąć, a jeśli nie uda się usunąć starego katalogu, GUI zgłasza jego ścieżkę. Testy wyłącznie syntetyczne.
- Pełne kopie zapasowe w menu Plik: ZIP z migawką SQLite, PDF-ami, wzorcami (w tym historią) i lokalnymi ustawieniami. Przed przywróceniem weryfikacja manifestu SHA-256, integralności SQLite i powiązań PDF; świadoma zgoda i zachowanie całego poprzedniego katalogu. ZIP **nie jest szyfrowany**. Testy tylko na fikcyjnych dokumentach.
- Podgląd PDF, lokalny odczyt tekstu i OCR (Tesseract), analiza przez lokalną Ollamę; edycja propozycji AI i formularza przed świadomym zapisem.
- Interfejs PySide6 w językach polskim i angielskim; etapy: Odczyt PDF → Analiza AI → Edycja danych → Faktura → Dokumenty.
- Tabela **Faktury** (nowy widok): filtrowanie i sortowanie zapisanych rekordów, statusy, suma widocznych, otwieranie do edycji; pierwotne **Dokumenty** pozostają archiwum PDF. Dane wyłącznie z SQLite, bez nowej migracji.
- Widok ANALIZA AI → DANE: pasek pracy Agenta w miejscu pod tabelą, nad przyciskami. Animacja przy oczekiwaniu na Ollamę (`stream=False`, brak wiarygodnego procentu), dokładne etapy: przygotowanie / zapytanie / walidacja, 100% dopiero po zakończeniu. Przerwanie/błąd przywraca stan spoczynkowy; testy syntetyczne bez faktur użytkownika.
- AGENT: przycisk „Szukaj modeli lokalnych…” — gotowe modele przez lokalne Ollama /api/tags, osobna informacyjna lista modeli GGUF i magazynów Ollamy znalezionych w znanych lokalizacjach Bobra; wybrać można tylko modele dostępne w API. Wybór zapisuje ustawienie `ollama_model`; bez pobierania, ładowania modeli i bez przetwarzania faktur podczas skanowania.
- Interfejs ANALIZA AI: wewnętrzne zakładki **DANE** (maksymalna tabela 5 kolumn, komentarze edytowane dwuklikiem, INFO i akcje na dole) i **AGENT** (Ollama, wybór wzorca, ogólne wskazówki). Sama przebudowa układu nie zmienia algorytmu LLM; aktualne notatki są używane podczas propozycji wzorca, nie jako nowy prompt bieżącego zapytania.
- Odczyt kodów QR z PDF: lokalny PDFium + ZXing-C++, okno z danymi płatności i potwierdzanym przenoszeniem kwoty oraz numeru konta. Żadnych przelewów ani automatycznego zapisu. **Licencja ZXing-C++: Apache-2.0, dopuszcza wykorzystanie komercyjne**; zawartość docelowego binarnego wheel wymaga audytu przed wydaniem Business.
- Inteligentne wzorce faktur W1–W4: dopasowywanie na podstawie sprzedawcy/układu, zatwierdzanie, edycja w formularzu zamiast ręcznego JSON, wyłączanie i przywracanie rewizji. Osobne reguły sprawdzają pełny miesiąc rozliczeniowy, jeśli źródło jednoznacznie wskazuje `MM/RRRR`.
- **Ochrona przed ponownym zapisem faktury (2026-11-11):** `RejestrRachunkow.znajdz_duplikat` i `zapisz_rachunek(..., nadpisz_id=...)` rozpoznają ten sam dokument lub dostawcę i numer faktury. Zapis istniejącej pozycji bez jawnego potwierdzenia jest blokowany w warstwie bazy. GUI pyta „Czy nadpisać?” z domyślnym **Nie**; potwierdzona aktualizacja zachowuje identyfikator faktury, bez dopisywania drugiej.
- Testy syntetyczne zapisów i duplikatów: `testy/test_rejestr.py`, `testy/test_duplikaty_baza.py`, `testy/test_duplikaty_faktur.py`; workflow `.github/workflows/duplikaty-sqlite.yml` dla testów bez Qt.
- Linux Beta: dokumentacja paczki źródłowej i eksperymentalnego pakietu binarnego. Nie traktować tego jako gotowej, oficjalnej wersji dla użytkowników końcowych.

- Katalog kategorii: wybór istniejących z liczbą faktur, ostrzeganie przed nazwami bliskimi lub równoważnymi, osobne potwierdzenie celowego duplikatu oraz transakcyjne scalanie błędnych kategorii (zachowuje kwoty, PDF-y i przypisania; źródło jest dezaktywowane). Kategorii domyślnych nie można wycofać, a wzorce z nazwą źródłową blokują scalanie do czasu poprawy wzorca. Funkcje nie wymagają migracji SQLite.

## Stan weryfikacji

**GitHub Actions — pełny zestaw testów ukończony pomyślnie** na Pythonie 3.11 i 3.13 (run `43182694952`, stan kodu `9a0fe7697be5de7a53b927ee4a04bfd2604331a4`). Testy QR korzystają wyłącznie z fikcyjnego kodu i syntetycznego PDF-u. Naprawiono też obsługę polskiego „ł” w nazwach okresów rozliczeniowych oraz izolację języka w teście sortowania kwot. **Nie wykonano testu GUI na komputerze użytkownika ani testu nowego dekodera na jego prywatnej fakturze**; są to kolejne testy akceptacyjne.

**Wyszukiwanie modeli lokalnych:** GitHub Actions `43197033453` zakończone sukcesem na Pythonie 3.11 i 3.13. Testy korzystają z fikcyjnych manifestów Ollamy, plików GGUF oraz symulowanego API `/api/tags`, bez prywatnych danych. Rzeczywisty skan katalogów na komputerze użytkownika pozostaje do sprawdzenia.


**Pasek pracy Agenta:** GitHub Actions `43199521730` — pełny zestaw testów ukończony pomyślnie na Pythonie 3.11 i 3.13 (commit `e69c1bf42464ab8f2eb33a45e09b6c6f57325b28`). Etapy pochodzą z lokalnego procesu analizy, a animacja pracy Ollamy nie udaje rzeczywistych procentów. Testy na danych fikcyjnych, bez prywatnych faktur.

**Kategorie i statystyki:** nowy dialog wyboru / dodawania / scalania kategorii, blokada przypadkowych duplikatów i osobne potwierdzenie tworzenia podobnych nazw; pełny GitHub Actions `43202906583` zakończył się sukcesem na Pythonie 3.11 i 3.13. Szybkie testy SQLite: `43202274153` — sukces. Przed operacją na rzeczywistych fakturach wykonać kopię całego lokalnego katalogu danych; nie przenoszono ani nie publikowano danych użytkownika.

**Kopie zapasowe — weryfikacja:** GitHub Actions `43212824122` — sukces na Pythonie 3.11 i 3.13. Przetestowano syntetyczne PDF-y, zapisy SQLite i wzorców, przywracanie z GUI, odmowę, SHA-256, brak nadpisania archiwum, zabezpieczenia przed ścieżkami niebezpiecznymi, zachowanie poprzedniego katalogu i cofanie po symulowanej awarii. Zwykłe testy bazodanowe: `43212441790` — sukces. Kopia ZIP nie jest szyfrowana; test na komputerze użytkownika pozostaje do wykonania.

**Wyczyszczenie bazy — weryfikacja:** GitHub Actions `43217601902` zakończony sukcesem na Pythonie 3.11 i 3.13. Testy obejmują odmowę usunięcia, błędną frazę, obowiązkową kopię ZIP ze sprawdzeniem spójności, wyczyszczenie faktur/PDF/wzorców/własnych kategorii, zachowanie języka i modelu, możliwość odtworzenia z ZIP oraz symulację awarii podczas podmiany. Szybkie testy SQLite `43217602028`. Test interaktywny na komputerze użytkownika pozostaje do wykonania — najpierw tylko w trybie `--test`.

## Dystrybucja i licencje

- Aktualny kod `main`: **PolyForm Noncommercial 1.0.0**. Business wymaga osobnej licencji dla klientów; wcześniejsze wersje GPL pozostają na swoich warunkach.
- Biblioteka QR `zxing-cpp` (`>=3.1.1,<4`): podstawowa licencja Apache-2.0 **pozwala na użycie komercyjne**. Przed sprzedażą instalatora zweryfikować konkretny wheel, notices i inne dołączane komponenty Qt/PDFium oraz zapisać listę wersji/hashów.
- Szczegóły: `THIRD_PARTY_LICENSES.md` i `docs/LICENCJONOWANIE.md`.

## Następne zadania — kolejność

1. **Test akceptacyjny QR:** sprawdzić syntetyczne kody, odczyt PDF na komputerze użytkownika, przypadki nieznanych formatów, brak QR, przeniesienie danych tylko po potwierdzeniu; testy CI nie używają prywatnego PDF.
2. **Test akceptacyjny tabeli faktur:** sprawdzić na komputerze docelowym różne statusy, daty, sortowanie kwot, wyszukiwanie, zapis i nadpisanie; zweryfikować zachowanie podglądu PDF po otwarciu z tabeli. Wykonać pełny zestaw testów syntetycznych w CI i lokalnie.
3. **Weryfikacja end-to-end:** fikcyjny PDF z warstwą tekstową i fikcyjny skan → OCR → Ollama → korekta → zapis → ponowny import → odmowa/potwierdzenie nadpisania. Prawdziwy dokument wyłącznie lokalnie, poza GitHubem.
4. **Akceptacja czyszczenia i historia/statystyki:** w trybie testowym potwierdzić, że przycisk bez backupu niczego nie usuwa, że wyczyszczona baza jest pusta i że sprawdzony ZIP pozwala odtworzyć dane. Następnie zaprojektować sumy miesięczne, historię i statystyki.
5. **Porządek dokumentacji:** uaktualnić `docs/PLAN.md`, który nadal nazywa część zaimplementowanego etapu 3 „gałęzią roboczą”. Uzupełniać status po każdym większym etapie, także przy zmianie interfejsu i testów.

## Testy do uruchamiania

```bash
# Baza i duplikaty — Python bez bibliotek GUI
python3 -m unittest testy.test_rejestr testy.test_duplikaty_baza testy.test_rejestr_faktur -v

# W środowisku projektu z zainstalowanym PySide6:
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest   testy.test_duplikaty_faktur testy.test_tabela_faktur testy.test_wzorce   testy.test_wzorce_integracja testy.test_okres_wzorca_formularz   testy.test_menedzer_wzorcow -v

# Nowe testy lokalnego odczytu QR (tylko dane fikcyjne):
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest testy.test_kody_qr -v

# Kopie zapasowe (testy wyłącznie syntetyczne):
python3 -m unittest testy.test_kopie_zapasowe -v

# Pełny zestaw testów, jeśli zależności są dostępne:
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s testy -v
```

Do testów interaktywnych na Linuxie używać `./uruchom.sh --test`, który wybiera odrębny katalog danych. Nie uruchamiać testów zapisu na bazie użytkownika.

## Niezmienne zasady

- Prace prowadzić na `main`, zgodnie z ustalonym trybem współpracy, z małymi logicznymi commitami i testami; przed zapisem zawsze ponownie sprawdzić aktualny kod.
- **Nie publikować na GitHubie prawdziwych faktur, skanów, plików SQLite, danych nabywcy ani danych finansowych.** W repozytorium wyłącznie fikcyjne dane i syntetyczne dokumenty.
- Archiwalnego PDF nie wolno modyfikować; przetwarzanie rachunków i Ollama pozostają lokalne.
- AI wyłącznie proponuje dane. To użytkownik potwierdza ich zapis, aktualizację i zapis wzorców; odrzucenie nadpisania nie może zmieniać bazy.
- Zachować kompatybilność istniejących baz i migracji; nie modyfikować historycznych migracji bez szczególnego uzasadnienia.
- Po każdym etapie odświeżyć ten plik: **zrobione / sprawdzone / otwarte / następny krok / commit HEAD**.

## Instrukcja wznowienia dla kolejnej sesji

1. Odczytaj `PROJECT_STATUS.md`, `README.md`, `docs/PLAN.md`, aktualny `main` i ostatnie commity.
2. Zweryfikuj, czy niniejszy status nadal zgadza się z kodem (w szczególności listą/tabelą faktur i ochroną duplikatów).
3. Kontynuuj od pierwszego niezakończonego zadania, tylko na syntetycznych danych.
4. Wykonaj adekwatne testy, zapisz commit i uaktualnij ten dokument. Gdy nie możesz uruchomić testów, wpisz to jawnie.
