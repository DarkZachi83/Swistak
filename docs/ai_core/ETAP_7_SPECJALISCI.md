# AI Core 1.0 — Etap 7: opcjonalne modele specjalistyczne

**Stan:** wdrożone na gałęzi `main`, do odbioru po CI i lokalnym teście.

## Cel i działanie

Agent główny jest nadal jedynym punktem odniesienia dla analizy
rachunków. Modele specjalistyczne są opcjonalnymi, lokalnymi pomocnikami.
Ich obecność nie zmienia sposobu odczytu SQLite, uprawnień agenta ani
zasad ręcznego potwierdzania zmian finansowych.

**Konfiguracja:** `Ustawienia → Konfiguruj`, sekcja
**Modele specjalistyczne (opcjonalne)**. Każda rola ma rozwijaną listę
wykrytych lokalnie modeli Ollamy oraz pozycję **Bez specjalisty**.
Wybory są przechowywane w prywatnym `settings.json` i zapamiętywane
po ponownym uruchomieniu. W przypadku braku dostępnej Ollamy zachowana
jest dotychczasowa konfiguracja; wybór modeli zostanie ponownie
uzupełniony po uruchomieniu lokalnego serwera.

| Rola | Gdzie działa | Granice |
|---|---|---|
| `extractor` | PDF/OCR → sugestie pól faktury | Korzysta ze wspólnego schematu i reguł W1–W4, bez zapisu |
| `verifier` | Panel Agenta, po analizie głównej | Niezależnie sprawdza fakty przez Tool Gateway |
| `financial_analyst` | Panel Agenta, po analizie głównej | Stan płatności, daty i sumy, bez modyfikacji |
| `cycle_analyst` | Pełny monitoring przy starcie / ręcznie | Oczekiwane dokumenty i zamknięcie miesięcy; pomijany przy pojedynczej fakturze |

**Bez zaznaczonych specjalistów** ścieżka pozostaje taka sama jak
w etapach 4–6: jeden model główny, lokalne kontrole deterministyczne
i Panel Agenta. Jeżeli użytkownik świadomie wybierze ten sam model
również dla roli specjalistycznej, wykona on odrębną kontrolę
z instrukcją tej roli — nie zostanie po cichu pominięty.

## Przebieg pracy i bezpieczeństwo

1. Agent hybrydowy najpierw oblicza sumy lokalnie, a następnie
   uruchamia **model główny**.
2. Tylko gdy analiza główna ma wynik `completed` / `partial`,
   uruchamiane są kolejno skonfigurowane role kontrolne.
3. Każdy specjalista ma osobne `task_id`, ten sam `data_revision`,
   ścisłe `allowed_tools` i sesję `Tool Gateway` z odczytem SQLite.
4. Zweryfikowany wynik kontrolny jest wyświetlany **oddzielnie**
   od wniosków modelu głównego w Panelu Agenta.
5. Propozycje akcji specjalistów są **odrzucane przed GUI**;
   nie mogą samodzielnie księgować płatności ani cofać faktur.
6. Gdy specjalista jest niedostępny, odmawia odpowiedzi lub nie spełnia
   schematu, wynik modelu głównego pozostaje dostępny.
7. Anulowanie i zmiana `data_revision` podczas analizy specjalistycznej
   powodują odrzucenie bieżącej pracy, nie zastosowanie starej sugestii.

Brak zweryfikowanego dowodu z wykonanych narzędzi obniża status
ustalenia do `unverified`. Sam model nie może dodać fałszywego
identyfikatora dowodu i uzyskać statusu `verified`.

W zadaniu dotyczących pojedynczej faktury specjalista finansowy
i weryfikujący mają zakres ograniczony przez identyfikator faktury;
specjalista cykli nie jest uruchamiany w tym trybie.

**Nie używamy zewnętrznych modeli chmurowych.**
Konfiguracja specjalistów nie pobiera ani nie instaluje modeli,
nie otwiera dostępu do plików prywatnych i nie zmienia migracji SQLite.

## Ograniczenia

- Przypisanie roli jest deklaracją użytkownika; automatyczny benchmark
  zdolności konkretnego modelu nie jest jeszcze wykonywany.
- Oddzielne role wykonują analizy **kolejno**, aby ograniczyć obciążenie
  CPU/GPU. Przy kilku modelach pełny raport może powstawać dłużej.
- Wyniki doradcze nie są automatycznie scalane z wynikiem głównym
  ani zatwierdzane jako decyzje księgowe.
- Nie ma automatycznego wyboru modeli na podstawie parametrów sprzętu
  z AI Bobra. To odrębny kierunek integracji, wymagający późniejszego projektu.
- Płatności, harmonogramy i historia w GUI pozostają własnością
  istniejących usług domenowych.

## Testy i kryteria odbioru

```bash
./.venv/bin/python -m unittest testy.test_ai_core_stage7 -v
./.venv/bin/python -m unittest discover -s testy -v
```

Testy korzystają wyłącznie z plików i baz syntetycznych oraz lokalnego
symulatora dostawcy LLM, bez pobierania modeli i prawdziwych faktur.

- [x] Cztery opcjonalne role w ustawieniach; domyślnie wyłączone.
- [x] Ekspert ekstrakcji korzysta ze wspólnego schematu pól i reguł OCR.
- [x] Agent główny pracuje jako pierwszy, kontrole uruchamiane kolejno.
- [x] Weryfikacja `AnalysisResult` i `evidence` przez Tool Gateway.
- [x] Role kontrolne nie mogą wykonywać operacji finansowych.
- [x] Fallback przy braku lub błędzie modelu specjalistycznego.
- [x] Ograniczenie zakresu do pojedynczej faktury po zapisie.
- [x] Anulowanie i ochrona przed nieaktualnymi wynikami.
- [x] Tłumaczenia PL/EN i oddzielne wyniki w Panelu Agenta.
- [x] GitHub Actions `43514283254` — **301 testów OK** na Pythonie 3.11 i 3.13.
- [ ] Lokalny test Python 3.14.10 i rzeczywisty model Ollama.
- [ ] Akceptacja użytkownika.

Po odbiorze możliwy **etap 8**: integracja końcowa, audyt
bezpieczeństwa, dokumentacja wydania oraz pakiet testów regresyjnych.
