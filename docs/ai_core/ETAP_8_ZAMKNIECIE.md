# Świstak — zamknięcie implementacji AI Core 1.0 (etap 8)

**Data:** 14 listopada 2026  
**Status:** zakończony pod względem implementacji i automatycznej regresji; lokalny test na Pythonie 3.14.10 oraz rzeczywistej Ollamie pozostaje testem odbiorczym użytkownika.  
**Repozytorium:** https://github.com/DarkZachi83/Swistak · gałąź `main`.

## Zakres etapów 0–8

| Etap | Zrealizowano |
| --- | --- |
| 0 | Kontrakty v1, schematy JSON i zasady odczytu/zapisu |
| 1 | Adapter lokalnej Ollamy, router, orkiestrator, anulowanie i timeouty |
| 2 | Tool Gateway: 12 kontrolowanych narzędzi `read`, walidacja i dowody |
| 3 | SQLite: daty opłacenia, wycofanie, audyt, plan rachunków, cykle |
| 4 | PDF/OCR → AI Core, walidacja, ręczna akceptacja, W1–W4 i QR |
| 5 | Agent hybrydowy: start, po zapisie, ręcznie, kolejka, offline i Panel Agenta |
| 6 | Plan rachunków, Historia, potwierdzanie dokumentów i zamykanie miesięcy |
| 7 | Cztery opcjonalne role modeli lokalnych, odrębne raporty i ograniczenia uprawnień |
| **8** | **Audyt kontraktów, paczek i prywatności; testy integracyjne; stabilizacja i dokumentacja** |

Etapy AI Core są **odrębne** od historycznych etapów budowy PDF/importu. Obecne sześć ekranów nawigacji to kroki obsługi faktury, a **nie** docelowe menu całego programu.

## Audyt i poprawki etapu 8

### A. Wydanie Linux — naprawiona niekompletność

Wykryto, że wcześniejsza **źródłowa paczka Linux Beta** zawierała kod GUI i SQLite, ale pomijała `ai_core/` oraz pliki JSON, od których zależą kontrakty uruchomieniowe. Dotyczyło to również schematów wymaganych przez binarną paczkę PyInstaller.

**Naprawiono:**
- `tools/build_linux_beta.py`: jawna allowlista całego `ai_core/*.py`, `contracts_v1.schema.json` i `tools_v1.json`;
- `tools/build_linux_binary.py`: dołączenie tych dwóch schematów jako danych runtime do PyInstallera;
- `testy/test_linux_beta.py` i `testy/test_linux_binary.py`: sprawdzenie pełnego manifestu;
- `testy/test_ai_core_stage8.py`: rozpakowanie **rzeczywistego** `tar.gz` do izolowanego katalogu i odrębny import AI Core przez `python -I`, bez zależności od katalogu repozytorium.

**Uwaga:** sukces testów deklaracji pakietu binarnego nie jest testem uruchomienia rzeczywistego pliku PyInstaller na każdej dystrybucji; binarne wydanie pozostaje w statusie QA/Beta i wymaga ręcznej próby oraz kontroli licencji przed publiczną dystrybucją.

### B. Kontrakty, bezpieczeństwo i prywatność

Dodatkowy `tools/audyt_ai_core.py --check` uruchamiany na **każdym pushu i pull requeście** w `.github/workflows/testy.yml` sprawdza:
- zgodność głównego JSON Schema v1;
- dostępność dokładnie 12 kontraktowych narzędzi z efektem `read`;
- kompletność kodu oraz schematów w źródłowej i binarnej paczce;
- brak plików prywatnych (PDF, baz, kluczy) i katalogów danych w allowliście paczki źródłowej;
- odrzucanie przez adapter Ollamy adresów spoza lokalnego HTTP loopback;
- brak potrzeby otwierania prawdziwej bazy i brak połączenia z Ollamą podczas audytu.

Pozostałe zabezpieczenia z etapów 0–7 nadal obowiązują: model nie dostaje swobodnego SQL, dowód `verified` wymaga odczytu faktycznego narzędzia, wszystkie efekty finansowe muszą zostać zatwierdzone przez użytkownika, a praca na nieaktualnej wersji danych jest odrzucana.

### C. Integracja end-to-end — tylko testy syntetyczne

`testy/test_ai_core_stage8.py` sprawdza:
1. sugestię ekstrakcji z fikcyjnego tekstu rachunku, w tym opcjonalnego modelu `extractor`;
2. **brak automatycznego zapisu** faktury po samej analizie LLM;
3. zapis tylko po jawnej operacji użytkownika w usłudze rejestru;
4. sprawdzenie sum i zaległości przez agenta **bez Ollamy**;
5. rozdzielenie „dokumenty kompletne” od „miesiąc finansowo zamknięty”;
6. faktyczną datę ręcznie zatwierdzonej płatności i jej wpływ na historię;
7. odrzucenie próby użycia narzędzia zapisu przez Tool Gateway;
8. oznaczenie niepopartej tekstem sugestii kwoty jako niepotwierdzonej;
9. kompletność i importowalność paczki Linux Beta z pustego katalogu.

Odrębne `testy/test_odczyt_pdf.py`, `testy/test_rasteryzacja.py` i `testy/test_proces_faktury.py` nadal testują rzeczywiste, wygenerowane **syntetycznie** pliki PDF, PDFium, OCR i GUI. Jeden duplikujący test natywnego Qt PDF w etapie 8 został celowo zastąpiony testem tekstowym, ponieważ destabilizował wspólny proces CI.

## Automatyczne testy i ograniczenia odbioru

- GitHub Actions: Python **3.11** i **3.13**, pełne `unittest discover`, audyt licencji i AI Core, kompilacja, porównanie OCR, zbudowanie źródłowej paczki Linux.
- Lokalnie (u autora): Python **3.14.10** z `.venv`, Ubuntu/Arch-like Linux, rzeczywista lokalna Ollama — wymagany manualny smoke test po aktualizacji.
- Nie ogłoszono wersji produkcyjnej ani oficjalnego wydania binarnego.
- Nie wgrano prywatnych faktur, baz ani historii do GitHuba.
- Kod pozostaje na `main`, nie są potrzebne nowe gałęzie ani worktree.
- Numer wersji pakietu nadal odpowiada obecnej becie; **nie podnosimy numeru** bez odrębnej decyzji o wydaniu.

## Polecenia na komputerze autora

```bash
cd /mnt/dane/Python/Projekty/Swistak/Swistak
git pull --ff-only origin main
./.venv/bin/python -m tools.audyt_ai_core --check
./.venv/bin/python -m unittest testy.test_ai_core_stage8 -v
./.venv/bin/python -m unittest discover -s testy -v
./uruchom.sh --test
```

Program testowy korzysta z osobnej bazy `~/.local/share/Swistak-Test-main`. Przed pracą na bazie rzeczywistej należy wykonać kopię zapasową.

## Co dalej — **nie etap 9 AI Core**, lecz interfejs użytkownika

AI Core 1.0 pozostaje niezależnym, stabilizowanym silnikiem. Użytkownik
wskazał, że Świstak ma już wczytywanie faktur, ale nie ma jeszcze
**głównego pulpitu, pełnego menu aplikacji i statystyk**.

Dalszy zatwierdzony kierunek: [Plan rozwoju GUI](../PLAN_ROZWOJU_GUI.md).

1. **GUI-1:** docelowa nawigacja aplikacji i Pulpit główny;
2. **GUI-2:** statystyki, wykresy oraz filtry porównawcze;
3. **GUI-3:** integracja obecnych modułów pod wspólnym menu;
4. **GUI-4:** dopracowanie wyglądu, responsywności, języków i testy UI.

**Pierwsze zadanie w następnym czacie: GUI-1.** Nie zastępuj danych
liczbami przykładowymi w programie i nie przebudowuj AI Core bez uzasadnienia.
