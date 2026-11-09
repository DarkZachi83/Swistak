# Świstak — założenia i etapy

## Zasady

- Dane użytkownika zostają lokalnie. Kod i testy są rozdzielone od magazynu danych.
- Najpierw **ręczne zaznaczenie**, potem odczyt, korekta i zatwierdzenie.
- PDF z warstwą tekstową odczytujemy bez OCR; skan poddajemy OCR tylko tam,
  gdzie użytkownik wskazał obszar.
- Oryginalnego PDF nie modyfikujemy. Archiwizujemy go z sumą SHA-256.
- Modułowość na wzór Nornicy, estetyka AI Bobra, interfejs PySide6.
- Testy każdej nowej reguły oraz migracje SQLite od pierwszej wersji bazy.

## Etap 0 — prototyp (obecny)

Podgląd lokalnych PDF, wiele stron, zoom i ręczne zaznaczanie obszaru.
Prostokąt obliczany we współrzędnych względnych (0–1), niezależnie od zoomu.
Przed przejściem dalej należy sprawdzić działanie GUI na Linuxie i Windowsie
oraz na rzeczywistych, ale niepublikowanych rachunkach.

## Etap 1 — zapis i archiwizacja

Minimalny schemat: `dokumenty`, `rachunki`, `pozycje_rachunku`, `kategorie`.
Kwoty jako całkowita liczba groszy. Migracje z wersjonowaniem i kontrolą SHA-256.
Oryginalne PDF-y w prywatnym katalogu danych (ścieżki względne, suma SHA-256),
zabezpieczenie przed duplikatami. Stan dokumentu musi przetrwać restart programu.

## Etap 2 — odczyt i zatwierdzanie

Najpierw użycie warstwy tekstowej (np. pdfplumber). Jeśli strona/obszar jest
skanem: rasteryzacja (Poppler), przygotowanie wycinka (OpenCV), Tesseract.
Surowy odczyt pozostaje edytowalny. Użytkownik przypisuje pole i zatwierdza.
Operacje OCR w wątku roboczym, bez blokowania interfejsu.

## Etap 3 — pierwsza wersja użytkowa

Historia rachunków z filtrowaniem, sumy miesięczne po kategorii. Kopia zapasowa
zawiera spójną migawkę SQLite i oryginalne PDF-y, jest weryfikowana przed
potwierdzeniem i może zostać bezpiecznie przywrócona.

## Etap 4 — szablony

Dopasowywanie dokumentu do dostawcy i zapamiętywanie obszarów, ale bez
samoczynnego zatwierdzania płatności. Wdrażamy dopiero na sprawdzonych przykładach.

## Poza zakresem na starcie

Bankowość, konta użytkowników, chmura, telemetria, modele AI, automatyczny
import e-mail, przypomnienia, edytor PDF i rozbudowane hierarchie kategorii.
