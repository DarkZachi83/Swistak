# Okno „O programie” — grafika i działające przyciski

Menu O programie otwiera autorski dialog PySide6, nie QMessageBox.about.
Podobnie jak w AI Bobrze, górną część stanowi ilustracja, a poniżej
pojawiają się tytuł, licencja, informacje o prywatności i przyciski.

Pliki obrazu są sprawdzane w kolejności:
1. assets/about/swistak-o-programie.webp — wycinek wcześniejszej wizualizacji.
2. assets/branding/swistak-banner.webp — istniejący baner brandingowy.

Jeśli obu brakuje, dialog działa z tekstem zastępczym.
Teksty i przyciski pozostają prawdziwymi kontrolkami Qt (PL/EN).
Przycisk gwiazdki otwiera oficjalne repozytorium w przeglądarce.

Ilustrację dostarczamy osobno w archiwum ZIP do skopiowania
do assets/about/ w katalogu projektu. Później może być dołączona
do repozytorium jako zasób binarny.

Testy Qt offscreen: dialog, języki, obecność/brak obrazu i URL GitHub.
