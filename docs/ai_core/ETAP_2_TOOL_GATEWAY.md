# Świstak AI Core — Etap 2: Tool Gateway i weryfikacja wyników

**Status:** Wdrożone na `main`, wymagany odbiór użytkownika.  
**Ustalony kontrakt:** `docs/ai_core/contracts_v1.schema.json` i `tools_v1.json` (bez zmian łamiących).

## Co działa

- `ai_core/gateway.py`: jawna allowlista i `jsonschema`, odczyt SQLite w trybie `mode=ro` + `query_only=ON`, identyfikatory dowodów, kontrola wersji pliku bazy.
- `invoice.search`, `invoice.details`, `invoice.lines`: bezpieczny odczyt faktur i kategorii; stronicowanie, limity.
- `payment.inspect`: zaległość od **dnia po terminie**, bez dat zgadywanych przez LLM; `reference_date` musi zgadzać się z datą przekazaną przez aplikację w `TaskRequest.context`.
- `date.evaluate`: sprawdzalne porównanie dat.
- `finance.aggregate`: sumy w całkowitych groszach, koszty wg końca okresu lub zastępczo daty wystawienia; kategorie sumowane po pozycjach.
- `document.verify`: lokalna weryfikacja archiwalnego PDF według SHA-256.
- `document.extract`: korzysta z istniejącego PDF/OCR, z limitem 3 stron, 10 MiB i 20 tys. znaków tekstu. Tekst dokumentu pozostaje nieufny.
- `ai_core/ollama.py`: natywna pętla `tool_calls → Tool Gateway → tool result → LLM → AnalysisResult`.
- `ai_core/orchestrator.py`: zlecanie pracy adapterowi i ponowna walidacja odpowiedzi; blokada niedozwolonego narzędzia.

## Funkcje odroczone — żadnych fikcyjnych wyników

Obecna baza SQLite ma tylko migracje 001 i 002. **Nie ma jeszcze** kolumny rzeczywistej daty zapłaty ani tabel Planu rachunków, miesięcznych potwierdzeń i audytu.

- `finance.aggregate` z `paid_date` odpowiada błędem `provider_unavailable`.
- `plan.expected`, `plan.match`, `cycle.evaluate`, `audit.read` również sygnalizują `provider_unavailable`, nie zwracają sztucznych zer.
- Faktyczny moduł płatności i migracje powstaną w Etapie 3.
- Nie ma jeszcze interfejsu panelu agenta ani automatycznych analiz przy starcie: plan Etapów 4–6.

## Granica zaufania

LLM **nigdy** nie ma dostępu do swobodnego SQL, plików spoza magazynu ani operacji finansowego zapisu. Każde żądanie narzędzia przechodzi przez kontrakt `ToolCall`, listę `allowed_tools`, ścisły schemat argumentów i limit rekordów.

Dowody `verified` mogą dotyczyć wyłącznie deterministycznych kodów `INVOICE_OVERDUE`, `INVOICE_UNPAID`, `INVOICE_PAID`, `PAYMENT_DUE_SOON`, po rzeczywistym wywołaniu `payment.inspect` dla tego samego ID i tej samej wersji danych. Swobodny opis wygenerowany przez LLM nie jest dowodem sam w sobie.

Narzędzia bazodanowe korzystają z tokenu `data_revision` opartego na SHA-256 istniejącego pliku SQLite i nie tworzą nowej bazy. Po zmianie danych wyniki starego zadania są odrzucane. Ta strategia zakłada obecny SQLite z `journal_mode=DELETE`; przed wsparciem WAL lub synchronizacji między urządzeniami należy ją zmienić.

Gdy użytkownik odmówi proponowanej zmiany finansowej, nic nie jest zapisywane. **Etap 2 w ogóle nie udostępnia takich operacji.**

## Testy

```bash
python -m unittest testy.test_ai_core_stage2 -v
python -m unittest discover -s testy -v
```

Testy używają wyłącznie syntetycznej bazy SQLite, fikcyjnych dokumentów i lokalnego symulatora Ollamy na `127.0.0.1`, bez pobranego modelu.

## Odbiór Etapu 2

- [x] Prawdziwe wywołania kontrolowanych narzędzi odczytowych.
- [x] Integracja z Ollamą przez `tool_calls` i kontrakty v1.
- [x] Ochrona przed dowolnym SQL, złą datą, nieautoryzowanymi narzędziami i błędnymi parametrami.
- [x] Dowody weryfikowane przez aplikację, nie przez LLM.
- [x] Niewdrożone funkcje jasno oznaczane jako niedostępne.
- [ ] Zielone GitHub Actions na Pythonie 3.11 i 3.13 dla końcowego commita.
- [ ] Test lokalny z prawdziwą Ollamą na fikcyjnych rachunkach (może być przeprowadzony podczas kolejnej akceptacji end-to-end).
- [ ] Odbiór przez użytkownika.

**Granica:** bez zmian w istniejących migracjach, GUI i ścieżce importu. Etap 3 implementuje docelowy model finansowy.
