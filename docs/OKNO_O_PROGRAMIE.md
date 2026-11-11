# Okno „O programie” — grafika JPEG i działające przyciski

Menu **O programie** otwiera autorski dialog PySide6 zamiast `QMessageBox.about`.
W górnej części widoczna jest ilustracja Świstaka, a poniżej tytuł,
licencja, informacja o prywatności oraz interaktywne przyciski.

## Format grafiki

Okno ładuje wyłącznie pliki **JPEG**, w poniższej kolejności:

1. `assets/about/swistak-o-programie.jpeg` — opcjonalna, dedykowana
   ilustracja okna „O programie”.
2. `assets/branding/swistak-banner.jpeg` — obecny, wysokiej
   rozdzielczości baner Świstaka dodany już do repozytorium.

Nie korzystamy z WebP ani z jego wcześniejszej miniatury 3,9 KB.
Obraz jest skalowany w pamięci do dostępnego miejsca, a przy skalowaniu
uwzględniana jest gęstość pikseli ekranu (HiDPI); oryginalny JPEG
pozostaje niezmieniony na dysku.

Jeżeli brakuje obu plików, dialog wyświetla komunikat zastępczy
i nie blokuje uruchomienia aplikacji.

Wszystkie napisy są kontrolkami Qt (PL/EN), nie częścią obrazu.
Przycisk gwiazdki otwiera repozytorium GitHub dopiero po kliknięciu,
a przycisk Zamknij kończy dialog. Baza SQLite pozostaje nietknięta.

Testy Qt offscreen weryfikują ładowanie rzeczywistego pliku JPEG
o rozdzielczości co najmniej 1000×600, zachowanie funkcji przy braku
pliku, skalowanie HiDPI, języki PL/EN i przyciski.
