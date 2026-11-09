# Warstwa danych — etap 1

- \`polaczenie.py\`: SQLite, \`foreign_keys=ON\`, transakcje \`BEGIN IMMEDIATE\`.
- \`migracje.py\`: migracje SQL ze sprawdzeniem SHA-256.
- \`schemat/001_start.sql\`: dokumenty, kategorie, rachunki i pozycje.

**Nie modyfikować wykonanej migracji 001.** Nowe zmiany wprowadzać przez
kolejne pliki \`002_*.sql\`, \`003_*.sql\` itd. Zmiana treści istniejącego pliku
powoduje błąd sprawdzania spójności.

Kwoty przechowywane są w groszach (liczby całkowite). Dokumenty zapisują
ścieżki względne do katalogu danych użytkownika; Git nie powinien zawierać
żadnych prawdziwych rachunków ani bazy.
