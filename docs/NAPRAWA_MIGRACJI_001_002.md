# Naprawa zgodności migracji 001/002 po zmianie licencji

Problem: wczesne wydania Świstaka tworzyły wpisy w tabeli
\`migracje\` z SHA-256 plików \`001_start.sql\` i \`002_numer_konta.sql\`
z nagłówkiem \`GPL-3.0-only\`. Późniejsza zmiana licencji na
\`PolyForm-Noncommercial-1.0.0\` zmodyfikowała także nagłówki tych
**już zastosowanych** migracji. Zmiana pojedynczego komentarza
spowodowała odmowę uruchomienia aplikacji:

\`\`\`text
Zmieniono wcześniej zastosowaną migrację: 001_start.sql
\`\`\`

## Bezpieczna zgodność wsteczna

W \`baza/migracje.py\` zezwalamy na **dokładnie jedną znaną różnicę**
dla dwóch konkretnych plików: nagłówek SPDX bez jakiejkolwiek
modyfikacji pozostałych bajtów SQL. Weryfikujemy SHA-256 całego
historycznego pliku po odtworzeniu jego poprzedniego nagłówka.

- Nie zmieniamy zawartości istniejących baz ani archiwum PDF.
- Nie podmieniamy zapisanych sum kontrolnych w tabeli \`migracje\`.
- Nie akceptujemy innych zmian w kodzie SQL, komentarzach lub
  nowych migracjach — ochrona integralności nadal działa.
- Zastosowanie nowej migracji pozostaje transakcyjne i zabezpieczone
  kopią SQLite zgodnie z obecnym mechanizmem projektu.

**Zasada na przyszłość:** nigdy nie zmieniamy już zastosowanych
plików migracji, również w celu poprawienia komentarzy czy nagłówków
licencji. Każda zmiana schematu dostaje nowy plik
\`003_*.sql\`, \`004_*.sql\` itd. Informacje licencyjne istniejących
plików muszą zachowywać historię i nie mogą powodować zmiany ich
sum kontrolnych.

## Gdy błąd utrzymuje się

Nie kasuj \`swistak.sqlite3\`, nie usuwaj tabeli \`migracje\`
ani nie aktualizuj jej SHA ręcznie. Zrób kopię całego katalogu
danych Świstaka przy wyłączonym programie i zgłoś komunikat błędu.
Ta zgodność nie jest uniwersalnym obejściem kontroli migracji.
