# Świstak — propozycja modelu licencjonowania Home / Business

**Status: dokument roboczy do przeglądu prawnego.**
Niniejszy dokument objaśnia model. Wiążące warunki użytkowania
niekomercyjnego zawiera tekst `LICENSE`; warunki komercyjne wymagają
odrębnej pisemnej umowy i nie zostały jeszcze opublikowane.

## Cel projektu

- **Świstak Home:** bezpłatny do użytku osobistego i innych celów
  niekomercyjnych dozwolonych w licencji, bez sztucznych limitów
  dokumentów, reklam i obowiązkowego konta.
- **Świstak Business:** prawo do wykorzystania komercyjnego
  udzielane na podstawie odrębnej pisemnej licencji. Na tym etapie
  nie publikujemy cen, nie sprzedajemy licencji i nie tworzymy
  fikcyjnego systemu aktywacji.
- **Publiczny kod:** dostępny do przeglądu, nauki, modyfikacji
  i dalszego rozpowszechniania w zakresie dozwolonym licencją.
  Termin właściwy: **source-available**, nie klasyczne
  **open source / OSI-approved**.

## Licencja proponowana dla kolejnych wersji

**PolyForm Noncommercial License 1.0.0**
SPDX: `PolyForm-Noncommercial-1.0.0`
Tekst bez zmian: https://polyformproject.org/licenses/noncommercial/1.0.0

Dopuszcza użytkowanie, modyfikowanie i redystrybucję **wyłącznie
dla dozwolonych celów niekomercyjnych**. Licencja dopuszcza również
niektóre cele edukacyjne, charytatywne i publiczne; dlatego termin
„Home” jest jedynie nazwą edycji, a nie pełnym opisem uprawnień.

**Nie wolno przedstawiać tej licencji jako GPL/MIT ani jako
licencji zatwierdzonej przez Open Source Initiative (OSI).**

## Licencja komercyjna

W przyszłości opracować odrębne warunki handlowe:
zakres użytku firmowego, liczba stanowisk lub organizacji,
okres licencji, aktualizacje, gwarancje i wyłączenia odpowiedzialności,
procedura wsparcia, fakturowanie oraz sposób zawierania umowy.
Bez podpisanej odrębnej licencji nowe wersje oferowane na PolyForm
Noncommercial **nie dopuszczają komercyjnego użycia**.

Nie korzystamy z ukrytych blokad ani telemetrii wymuszających
aktywację. Sam publiczny dostęp do kodu nie nadaje uprawnień
komercyjnych.

## Poprzednie wersje GPL

Do commita `5df8a0311868e702cd30979ad7aadbe1cc061116` włącznie
Świstak był publikowany jako `GPL-3.0-only`. Użytkownicy, którzy
otrzymali te wersje, zachowują prawa przyznane przez GPL.
Zmiana licencji kolejnych wydań nie cofa wcześniejszej licencji.
Nie należy usuwać historii repozytorium ani sugerować, że GPL
przestała obowiązywać dla otrzymanych wcześniej kopii.

Źródło historyczne:
https://github.com/DarkZachi83/Swistak/tree/5df8a0311868e702cd30979ad7aadbe1cc061116

Jeśli wykorzystujemy kod współautorów lub kod zapożyczony z innych
projektów GPL, potrzebujemy ich zgody na zmianę licencji lub
zastąpienia tych fragmentów. Obecny rejestr commitów wskazuje
jednego autora konta GitHub, ale **nie dowodzi sam w sobie
wyłączności praw do wszystkich fragmentów kodu**.

## Zależności i warunki wydania

Wstępny audyt: [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md),
maszynowy rejestr: [licencje/rejestr.json](../licencje/rejestr.json).
**Blokery przed dystrybucją komercyjną: Poppler (GPL), warunki Qt LGPL
oraz odrębna licencja wag Gemma 3.** Oznacza to konieczność oceny
konkretnego sposobu pakowania, a nie automatyczny zakaz użycia.

Świstak korzysta m.in. z PySide6/QtPdf, pakietów Python,
Tesseract, Poppler oraz lokalnej Ollamy (opcjonalnie).
Licencja Świstaka **nie zastępuje licencji tych komponentów**.

Przed wydaniem instalatora konieczny jest audyt LGPL/GPL
wszystkich używanych modułów Qt, sposobu pakowania,
możliwości podmiany bibliotek, informacji o ich licencjach
oraz pozostałych zależności.

Poradnik Qt: https://www.qt.io/development/open-source-lgpl-obligations

## Zmiana licencji w repozytorium

Dokonać jej spójnym commitem: `LICENSE`, nagłówki SPDX kodu,
README i niniejszy dokument. Nie przejmować automatycznie
licencji wcześniejszych wersji. Zanim PR zostanie scalony
z gałęzią `main`, właściciel praw powinien zatwierdzić
brzmienie nowej licencji i uzyskać profesjonalny przegląd
licencji zależności oraz umowy komercyjnej.
