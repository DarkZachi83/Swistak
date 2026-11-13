# Kontrakty AI Core v1 — norma techniczna Etapu 0

**Wersja:** 1.0 · **Język:** polski · **Status:** kontrakt bazowy dla przyszłych implementacji.  
Uzgodnione wymagania pochodzą z zatwierdzonej specyfikacji AI Core 1.0; poniższe szczegóły techniczne są konkretyzacją Etapu 0.

## 1. Granice i kierunek zależności

`PySide6 → AI Orchestrator → Model Router → LLMProvider` oraz `AI Orchestrator → Tool Gateway → usługi domenowe → SQLite / PDF`.

Model **nie** posiada połączenia SQLite, swobodnego SQL, dostępu do plików poza narzędziami ani własnej ścieżki zapisu. Treść dokumentów jest nieufnymi danymi. Zmiana finansowa to wyłącznie propozycja do zatwierdzenia, a wykonanie następuje przez kontrolowaną usługę, po sprawdzeniu wersji rekordu.

Jeden model główny `main` prowadzi planowanie. Opcjonalne role: `extractor`, `verifier`, `financial_analyst`, `cycle_analyst`. W razie niedostępności specjalisty router może użyć modelu głównego **tylko po sprawdzeniu zgodności z rolą**; nie wolno cicho przełączać się do zewnętrznego API.

## 2. Kontrakt adaptera `LLMProvider v1`

W Etapie 0 zamrażamy **semantykę** operacji, a nie implementację Python:

| Operacja | Zwracany sens | Zachowanie szczególne |
|---|---|---|
| `health_check` | Dostępność backendu i modelu | Nie pobiera ani nie uruchamia instalacji modelu |
| `list_models` | Identyfikatory modeli dostępnych lokalnie | Brak modelu to zwykły wynik, nie utrata danych |
| `get_capabilities` | `ModelProfile` / opis możliwości | Deklaracja podlega testom zgodności |
| `generate` | Wynik zadania w schemacie `AnalysisResult` | Walidacja odpowiedzi jest poza modelem |
| `stream` | Zdarzenia postępu i fragmenty odpowiedzi | Fragmenty nie mogą powodować operacji finansowych |
| `cancel` | Próba przerwania zadania | Best-effort; spóźnione wyniki są ignorowane |

Etap 1 doprecyzuje metody asynchroniczne i protokół strumieniowania. Nie wprowadzamy zależności aplikacji od nazw pól Ollamy.

## 3. Koperty JSON — wersja `1.0`

Schemat normatywny: [`contracts_v1.schema.json`](contracts_v1.schema.json) (`$defs`).

- **`TaskRequest`**: `contract_version`, `task_id`, `role`, `instruction`, `context`, `allowed_tools`, `response_schema`, `data_revision`, `locale`, `timezone`, `limits`.
- **`ToolCall`**: `task_id`, unikalne `call_id`, nazwa i wersja narzędzia, parametry oraz wersja danych.
- **`ToolResult`**: status `ok|error`, dane, dowody, ustrukturyzowany błąd i wersja danych.
- **`AnalysisResult`**: `findings`, `proposed_actions`, `uncertainties`, `diagnostics`, `model_id`, `data_revision` i stan.
- **`ModelProfile`**: backend, model, role i możliwości.

Każda koperta ma `contract_version: "1.0"`. Nieznana wersja lub nieznane pole na poziomie koperty powoduje odrzucenie. Identyfikatory `task_id`, `call_id`, `data_revision` są nieprzezroczystymi tokenami — nie wolno wyprowadzać z ich składni stanu biznesowego.

**Daty:** faktury i terminy używają `YYYY-MM-DD`; czas zdarzeń operacyjnych — UTC; zadanie przekazuje strefę IANA (domyślnie `Europe/Warsaw`). Bieżącą datę dostarcza aplikacja/narzędzie, nie model.

**Kwoty:** wyłącznie całkowite grosze w narzędziach finansowych; prezentacja walutowa jest obowiązkiem UI. Brak daty zapłaty nie może być uzupełniony domysłem.

**Dowody:** `verification: "verified"` jest ustawiane wyłącznie po sprawdzeniu `evidence` przez warstwę aplikacji. Model nie może sam uwiarygodnić cytowanego identyfikatora. Brak podstaw oznacza `unverified` lub `needs_review`.

## 4. Narzędzia v1

Źródło maszynowe: [`tools_v1.json`](tools_v1.json). Wszystkie wpisy v1 mają `effect: "read"` i ograniczony zakres. Są to kontrakty interfejsów przyszłych narzędzi, nie dostępne dziś endpointy.

| Narzędzie | Znaczenie |
|---|---|
| `invoice.search` | Filtrowanie i stronicowanie faktur |
| `invoice.details` | Pojedynczy rekord wraz ze stanem |
| `invoice.lines` | Pozycje bez podwajania sum |
| `payment.inspect` | Data, status i termin płatności |
| `date.evaluate` | Porównania dat bez interpretacji modelu |
| `finance.aggregate` | Grosze, agregacje `billing_end` / `paid_date` |
| `document.extract` | Lokalny odczyt PDF/OCR |
| `document.verify` | Kontrola pochodzenia danych dokumentu |
| `plan.expected` | Oczekiwane rachunki dla cyklu |
| `plan.match` | Możliwe powiązania faktury z profilem |
| `cycle.evaluate` | Osobno kompletność i opłacenie |
| `audit.read` | Ograniczony odczyt historii zmian |

Narzędzia zwracają fakty i identyfikatory źródeł. Brak dowolnego SQL, brak automatycznego tworzenia zobowiązań na podstawie samych oczekiwań, brak samodzielnego wywoływania operacji zapisu.

## 5. Propozycje zmian — bez skutków ubocznych

Każde `ProposedAction` ma `requires_confirmation: true` oraz `expected_data_revision`. Samo wygenerowanie propozycji nie wywołuje zapisu. Po akceptacji aplikacja ponownie odczytuje dane, weryfikuje aktualność, uprawnienia i sens operacji; następnie usługa domenowa wykonuje transakcję wraz z wpisem do dziennika.

Odmowa, błąd i anulowanie nie zmieniają finansów. Nawigacja zaproponowana przez LLM również nie jest automatyczną zmianą stanu faktury.

## 6. Hybrydowa praca i spójność

Analiza przy starcie — po gotowości modelu; po zmianie rekordu — tylko dotknięty zakres; pełna analiza — na żądanie. Priorytet ma polecenie użytkownika. Kolejka scala podobne zadania, ogranicza jednoczesne obciążenie GPU i umożliwia anulowanie.

`data_revision` pochodzi z kontrolowanej warstwy danych. Przed pokazaniem ustalenia jako aktualnego i przed zatwierdzeniem propozycji należy sprawdzić, czy istotne rekordy nie zmieniły się po rozpoczęciu analizy.

Bez modelu pozostają: rejestr, PDF, ręczne operacje, podstawowe sumy i wyliczenia terminów. Wyniki wcześniejszego LLM nie są prezentowane jako świeże.

## 7. Wersjonowanie i testowanie

- Zmiana łamiąca kontrakt wymaga nowego numeru głównego wersji; dotychczasowe v1 pozostaje czytelne dla zgodnych klientów.
- Rozszerzenia niełamiące mogą otrzymać osobne wersje dodatkowe, ale nie można arbitralnie dodawać pól do kopert v1 z `additionalProperties: false`.
- Testy Etapu 0 są bez Ollamy, bez prywatnych dokumentów i bez migracji SQLite.
- Testy Etapu 1–2 mają objąć rzeczywiste walidowanie JSON Schema, dwa różne modele lokalne, niedostępny backend, timeout, anulowanie, niepoprawny JSON, nieuprawnione narzędzie, prompt injection i spóźnione wyniki.

**Kryterium zakończenia Etapu 0:** spójne kontrakty, katalog narzędzi i dane syntetyczne; testy automatyczne przechodzą; brak zmian w runtime, GUI i bazie.
