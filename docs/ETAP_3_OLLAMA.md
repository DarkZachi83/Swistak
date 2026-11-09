# Etap 3 — lokalny asystent odczytu przez Ollamę

**Status: specyfikacja, niezaimplementowane.**
Zależy od etapu 2, czyli poprawnego wydobywania tekstu z PDF i OCR skanów.

## Założenia użytkowe

Przycisk: **Analizuj rachunek (Ollama)**, z wyborem lokalnie
zainstalowanego modelu. Po analizie Świstak pokazuje tabelę
**propozycja / źródłowy fragment dokumentu / wartość po korekcie**.
Przyciski: **Zatwierdź i zapisz**, **Popraw**, **Zaznacz fragment ręcznie**.
Brak odpowiedzi Ollamy nigdy nie uniemożliwia manualnej obsługi dokumentu.

## Wejście i wyjście

Wejście: tekst całego rachunku (w razie potrzeby z informacją o numerach
stron), po odfiltrowaniu pustych bloków. Dla większych dokumentów należy
ograniczyć kontekst bez usuwania istotnych danych płatności.

Ollama REST API: `POST http://127.0.0.1:11434/api/chat`,
`stream: false`, `format: { ... JSON Schema ... }`.
Model jest wybierany z listy lokalnie dostępnych modeli, a odpowiedź
jest traktowana jako niezaufana sugestia.

**Schemat logiczny odpowiedzi** (JSON poniżej to dane syntetyczne,
nie rzeczywiste informacje bankowe):

```json
{
  "dostawca": {"wartosc": "Zakład Testowy", "dowod": "Sprzedawca: Zakład Testowy"},
  "numer_faktury": {"wartosc": "FV-TEST-001", "dowod": "Faktura FV-TEST-001"},
  "kwota_do_zaplaty": {"wartosc": "125,80", "dowod": "Do zapłaty 125,80 PLN"},
  "waluta": {"wartosc": "PLN", "dowod": "125,80 PLN"},
  "termin_platnosci": {"wartosc": "2026-12-10", "dowod": "Termin płatności: 10.12.2026"},
  "data_wystawienia": {"wartosc": null, "dowod": null},
  "okres_od": {"wartosc": null, "dowod": null},
  "okres_do": {"wartosc": null, "dowod": null},
  "numer_konta_bankowego": {"wartosc": null, "dowod": null},
  "kategoria_sugerowana": {"wartosc": "Gaz", "dowod": "Zużycie gazu"}
}
```

Dla każdego pola dopuszczamy `null`. `dowod` ma być
cytatem z wejściowego tekstu; aplikacja sprawdza, czy dowód faktycznie
występuje w ekstrakcie, ale to **nie oznacza**, że interpretacja jest
prawidłowa. W prawdziwym schemacie JSON należy wymagać obecności kluczy
i typów; nie wolno ufać samemu formatowi odpowiedzi modelu.

## Walidacja po stronie aplikacji

- `kwota_do_zaplaty`: parsowanie przy użyciu Decimal, zapis jako grosze,
  waluta jawna; odróżnienie salda, kwoty brutto, nadpłaty i kwoty do zapłaty.
- `termin_platnosci` / daty: ścisły ISO 8601 `RRRR-MM-DD`,
  rozpoznanie źródłowego formatu DD.MM.RRRR.
- `numer_konta_bankowego`: osobny typ tekstowy od numeru
  faktury, normalizacja spacji, kontrola sumy NRB/IBAN i kraju;
  nieprawidłowy numer oznaczony jako ostrzeżenie, nie poprawiany „na oko”.
- `kategoria_sugerowana`: mapowanie wyłącznie do kategorii istniejących
  w SQLite, bez samowolnego tworzenia nowych.
- Dla niepewności lub braku źródła: nie wypełniać bez ostrzeżenia.
- Dokument jest **niezaufanym tekstem**: instrukcje znalezione w treści
  rachunku nie mogą zmieniać zachowania aplikacji, omijać walidacji
  ani uruchamiać jakichkolwiek poleceń.

## Warunki ukończenia

1. Tekstowy PDF i skan po OCR dają sugestie w tym samym schemacie.
2. Numer faktury nie jest mylony z numerem konta — przypadki testowe.
3. Brak kwoty/terminu/konta pozostawia pole puste (`null`).
4. Błędny JSON, brak Ollamy lub timeout => bezpieczny powrót do formularza.
5. Wymagana jawna akceptacja użytkownika przed każdym zapisem.
6. Ani tekst PDF, ani wyniki modelu nie są wysyłane do usług chmurowych.
7. W testach i repozytorium występują tylko rachunki syntetyczne.
8. Nie ma możliwości automatycznego przelewu ani wykorzystania konta
   bankowego bez kontroli użytkownika.

## Zakres implementacji

Odseparować klienta Ollama od parsera/validatora danych i okna GUI.
Wywołanie wykonać w wątku roboczym z timeoutem i anulowaniem.
Nowe kolumny SQLite wprowadzać wyłącznie nowymi migracjami.
Wybór modelu i jego zachowanie sprawdzić na kilku rzeczywistych typach
rachunków, ale samych plików ani wyników OCR nie publikować.

API Ollama:
- https://docs.ollama.com/api/chat
- https://ollama.com/blog/structured-outputs
