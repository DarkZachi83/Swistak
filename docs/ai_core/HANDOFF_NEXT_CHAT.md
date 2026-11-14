# Handoff do następnego czatu — Świstak po AI Core 1.0

**Data:** 14.11.2026. **Repo:** https://github.com/DarkZachi83/Swistak, gałąź `main`.  
**Po szczegóły etapu 8:** [ETAP_8_ZAMKNIECIE.md](ai_core/ETAP_8_ZAMKNIECIE.md).  
**Zatwierdzony następny plan:** [PLAN_ROZWOJU_GUI.md](../PLAN_ROZWOJU_GUI.md).

## Zasady pracy

Użytkownik pracuje lokalnie w
`/mnt/dane/Python/Projekty/Swistak/Swistak`, Python 3.14.10
w `.venv`, Linux. Aktualizuje przez `git pull --ff-only origin main`,
uruchamia `./uruchom.sh --test` dla oddzielnej bazy testowej
`~/.local/share/Swistak-Test-main`.
Wszystkie implementacje na `main` z testami; nie używaj starego worktree.
Nie publikuj faktur ani danych prywatnych na GitHubie.
Model LLM pozostaje lokalny, działa przez Ollamę; człowiek zatwierdza
każdą istotną operację finansową. PySide6, SQLite, PL/EN.

## Stan implementacji

**Historyczne fundamenty:** podgląd PDF, odczyt warstwy tekstowej/Tesseract OCR,
QR, formularze i kategorie, import/archiwum SHA-256, wykrywanie duplikatów,
W1–W4 inteligentne wzorce, kopie zapasowe i czyszczenie bazy, logika
rachunków/płatności, menu języków i lokalne modele (standardowe katalogi,
własny folder, Ollama/GGUF/Transformers).

**AI Core 1.0 — etapy 0–8 wdrożone:**
0. Schematy JSON i kontrakty.
1. Orkiestrator, router modeli, lokalna Ollama.
2. Tool Gateway, 12 read-only operacji, kontrola dowodów.
3. Finanse SQLite, 003–005 migracje, Plan i cykle, audyt.
4. PDF/OCR → AI Core i ręczna akceptacja.
5. Agent hybrydowy i panel, kontrole start/zmiana/ręcznie, offline.
6. Plan/Historia/zamknięcie miesięcy w osobnym oknie.
7. Opcjonalne role extractor/verifier/financial_analyst/cycle_analyst.
8. Audyt, integracja, naprawa pakowania AI Core, testy release,
   dokumentacja i przebieg CI.

**Stan UI:** nadal dominują 6 kroków pojedynczej faktury
(`Odczyt / Analiza AI / Edycja / Faktura / Dokumenty / Faktury`).
Są już osobne okna `Plan / Historia`, `Panel Agenta` i `Ustawienia`,
ale **nie ma docelowego głównego pulpitu ani wykresów statystyk**.
Nie twierdź, że pulpit został wdrożony.

**Konieczne do potwierdzenia przez użytkownika:** test lokalny pełnego
AI Core na Pythonie 3.14.10 i test rzeczywistej Ollamy; sukces CI
nie zastępuje testu na lokalnym sprzęcie. Binarna paczka PyInstaller
pozostaje eksperymentalnym QA/Beta, nie oficjalnym wydaniem.

## Następny zatwierdzony plan (wykonuj po kolei)

1. **GUI-1: główne menu i Pulpit** — nowy ekran startowy, boczne menu,
   karta sum, terminy, zaległości, oczekiwania, przejścia do istniejących
   ekranów bez utraty danych formularza; nie usuwać kreatora OCR.
2. **GUI-2: Statystyki** — miesięczne/roczne wykresy, kategorie, dostawcy,
   filtry okresu i statusu; sumy w groszach, odrębny miesiąc usługi
   i rzeczywistej zapłaty.
3. **GUI-3: Integracja** — Moje faktury, Plan, Historia, Agent i Ustawienia
   w spójnym menu, wykorzystując już działające usługi i dialogi.
4. **GUI-4: dopracowanie** — motyw, HiDPI, tłumaczenia PL/EN, testy UX,
   brak uciętych opisów, zgodność z istniejącą bazą, PDF i AI.

## Pierwsza akcja następnego asystenta

1. Otwórz aktualny `main` repo i sprawdź strukturę `gui/okno_glowne.py`,
   `gui/motyw.py`, `uslugi/finanse.py`, `uslugi/historia.py`,
   `ai_core/hybrid.py`, `gui/dialog_plan_historia.py` i istniejące
   testy PySide6.
2. Zaproponuj spójny, konkretny układ **GUI-1** z weryfikowalnymi
   kryteriami (pulpit + nowe menu) i **zaimplementuj go bezpośrednio
   na `main`**, zachowując dotychczasowy kreator faktury.
3. Dodaj/rozszerz testy syntetyczne GUI i uruchom regresję CI.
4. Poproś o lokalny odbiór `./uruchom.sh --test` i zrzuty ekranu.
5. **Nie** przechodź do GUI-2 przed zaakceptowaniem GUI-1.

Nie rozpoczynaj nowego etapu AI Core; zakończenie implementacji
wersji 1.0 jest opisane w ETAP_8_ZAMKNIECIE.md.
