# Świstak — założenia i etapy

## Zasady
- Dane prywatne pozostają lokalnie; kod i testy na GitHubie.
- Najpierw ręczna kontrola i zatwierdzanie, bez automatycznego księgowania.
- PDF z warstwą tekstową obsłużymy bez OCR; skan tylko z OCR na wybranym fragmencie.
- Oryginałów PDF nie modyfikujemy; przechowujemy kopię z SHA-256.
- Moduły SQLite i archiwum wzorowane architektonicznie na Nornicy,
  interfejs wizualnie inspirowany AI Bobrem.
- Wszystkie etapy mają testy i osobne commity.

## Etap 0 — wykonany
Wielostronicowy podgląd PDF, zoom, zaznaczanie obszaru z normalizacją
współrzędnych. Ręczne potwierdzenie działania przez użytkownika.

## Etap 1 — baza i archiwum (gałąź robocza)
SQLite: `dokumenty`, `rachunki`, `pozycje_rachunku`, `kategorie`.
Kwoty jako całkowite grosze. Wersjonowane i sprawdzane SHA-256 migracje.
Archiwum PDF w katalogu użytkownika, deduplikacja SHA-256, ścieżki
względne, ponowna weryfikacja przy otwieraniu.
Import, formularz rachunku, ręczne dodawanie kategorii, lista dokumentów.
Przed scaleniem potrzebny test GUI na docelowym komputerze.

## Etap 2 — odczyt zaznaczonego pola
Tekstowa warstwa PDF (np. pdfplumber) lub Tesseract dla skanów
(po rasteryzacji, OpenCV), wyłącznie dla wybranego obszaru.
Podpowiedź w edytowalnym formularzu, ręczne zatwierdzanie,
operacje OCR poza głównym wątkiem interfejsu.

## Etap 3 — historia, statystyki i kopie zapasowe
Filtrowanie rachunków, sumy miesięczne; kopia spójnej migawki SQLite
i oryginałów PDF z manifestem SHA-256 oraz sprawdzane przywracanie.

## Etap 4 — szablony dostawców
Zapamiętywanie układu dokumentu, potwierdzanie odczytu,
dopiero po sprawdzeniu dokładności odczytu z różnych rachunków.

## Poza zakresem
Bankowość, cloud, telemetria, AI/LLM, automatyczny e-mail,
powiadomienia i rozbudowane hierarchie kategorii.
