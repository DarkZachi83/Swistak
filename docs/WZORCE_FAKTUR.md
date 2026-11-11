# Świstak — inteligentne wzorce faktur (W1–W4)

**Status: funkcja rozwojowa, przeznaczona do testów lokalnych.**
Nie jest to trening/fine-tuning Gemmy. To *pamięć zatwierdzonych reguł*.

## Przepływ

1. Zaimportuj PDF i uruchom **Odczyt PDF / skanu** (dla skanu: lokalny OCR).
2. Świstak przed **Analizą AI** porównuje tekst z lokalnymi wzorcami:
   NIP sprzedawcy (60 punktów), nazwa/alias (20), etykiety układu (20).
   NIP nabywcy **nie** jest używany do automatycznego dopasowania.
3. Wynik ≥80 punktów ze zgodnym NIP-em i bez konkurencji:
   zastosowanie zatwierdzonego wzorca; 55–79 lub zgodny układ/nazwa
   bez czytelnego NIP-u: sugestia do zaakceptowania; brak zgodności:
   normalna analiza bez wzorca.
4. Gemma otrzymuje **wyłącznie zatwierdzone wskazówki** wraz z tekstem
   **bieżącej** faktury. Dalej obowiązują dowody OCR/PDF, daty, kwoty,
   waluta, sprawdzanie rachunku bankowego i ręczny wybór użytkownika.
5. W Analizie AI możesz skorygować pole, zaznaczyć wiersz i wybrać
   **Komentarz do pola…**. Możesz też wpisać wskazówkę ogólną.
   Uwagi nie są jeszcze zapisywane — pozostają w pamięci bieżącej sesji.
6. Przenieś dane do **Edycji danych**, popraw, obejrzyj **Fakturę** i
   świadomie wybierz **Zapisz fakturę**. Sam zapis faktury **nie zapisuje
   żadnego wzorca**.
7. Dopiero po zapisie pojawia się propozycja **Utwórz wzorzec faktury…**
   lub **Zaproponuj aktualizację wzorca…**. Otwiera edytowalny podgląd JSON;
   **Anuluj** nie zmienia żadnego wzorca.
8. **Zatwierdź i zapisz** tworzy lokalny JSON. Aktualizacja przechowuje
   poprzednią wersję w podkatalogu \`historia\`.
9. Przy kolejnej fakturze z pasującym NIP-em i układem zatwierdzone
   wskazówki są przekazywane do lokalnej Ollamy.

## Gdzie są pliki?

W lokalnym katalogu danych aplikacji, zależnym od systemu:

\`\`\`text
<SWISTAK_DATA_DIR lub domyślny katalog Świstaka>/
└── wzorce/
    ├── wz-<unikalny-identyfikator>.json
    └── historia/
        └── wz-<unikalny-identyfikator>.rev-000001.json
\`\`\`

Wzorce są **prywatnymi danymi lokalnymi**, nie są dołączane do
repozytorium ani paczek dystrybucyjnych. JSON zawiera tylko
identyfikację sprzedawcy (m.in. NIP), etykiety układu, reguły pól,
kategorię, wskazówki zatwierdzone przez użytkownika oraz numer rewizji.
Nie przechowujemy historycznych kwot, dat płatności, numerów kont
ani całego tekstu OCR.

**Wskazówki to tekst użytkownika:** nie wpisuj do nich danych nabywcy,
adresów, numerów kont ani kwot z dokumentów. Program blokuje długie
ciągi przypominające numery rachunków bankowych, a zapisywane
pola JSON są ograniczone do zdefiniowanego schematu.

## Bezpieczeństwo

- Nieaktualny/wyłączony wzorzec nie jest automatycznie używany.
- Sprzeczny poprawny NIP sprzedawcy **blokuje automatyczne dopasowanie**.
- Brak NIP sprzedawcy nigdy nie daje automatycznej akceptacji.
- Wynik podobieństwa dotyczy identyfikacji szablonu, **nie dokładności
  odczytu poszczególnych wartości**.
- Tekst faktury pozostaje niezaufany (instrukcje z PDF nie mogą
  utworzyć ani zaktualizować wzorca).
- Żadna akcja wzorca nie zapisuje faktury automatycznie do SQLite.
- Pliki JSON zapisujemy atomowo, z uprawnieniami \`0600\` na Linuxie,
  a katalog jest prywatny (\`0700\`).
- Rewizje JSON służą do przywracania reguł; nie zastępują pełnej kopii
  bazy danych i zaimportowanych PDF.
- Zarządzanie historią, wyłączaniem i przywracaniem jest już dostępne
  w usłudze \`MagazynWzorcow\`; pełny graficzny menedżer wzorców
  stanowi **kolejny etap W5**.

## Granice obecnej wersji

Układ dokumentu jest rozpoznawany na podstawie **stałych etykiet
tekstowych**, a nie obrazu piksel po pikselu. Dla PDF bez tekstu wymagany
jest najpierw OCR. Nie jest to gotowe rozpoznawanie wariantów
wizualnych skanów; to dalsza praca w etapie W6.

Wskazówki do poprawionych pól nie powstają automatycznie na podstawie
konkretnych wartości finansowych — użytkownik może podać je świadomie,
a generator przypisuje bezpieczne, ogólne etykiety i formaty.
To celowe ograniczenie bezpieczeństwa danych.

## Testy

\`\`\`bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest \
  testy.test_wzorce testy.test_wzorce_integracja -v
\`\`\`

Testy używają wyłącznie fikcyjnego operatora i syntetycznych PDF.
Żaden rzeczywisty dokument nie jest częścią testów.
