# Świstak Linux Beta — eksperymentalny pakiet binarny

**Status: wyłącznie test techniczny i licencyjny, bez oficjalnego wydania.**

Celem jest uruchomienie Świstaka **bez lokalnej instalacji Pythona,
`pip` ani tworzenia `.venv`**. Pakiet jest budowany na Linuxie
przez PyInstaller w trybie **one-folder** (nigdy `--onefile`).

## Jak testować

Archiwum `swistak-linux-0.1.0b1-bin.tar.gz` jest dostępne jako
artefakt testowego przebiegu GitHub Actions tego PR (nie jako Release).

```bash
tar -xzf swistak-linux-0.1.0b1-bin.tar.gz
cd Swistak-Linux-0.1.0b1-bin
./start.sh --version
./start.sh --self-test
./start.sh --test
```

`--self-test` kontroluje obecność zasobów Qt PDF, JPEG, tłumaczeń
i migracji, **bez otwierania bazy danych**. `--test` uruchamia aplikację
ze specjalnym katalogiem `Swistak-Test-Binary-0.1.0b1`, odrębnym od
domyślnej bazy i poprzedniego pakietu źródłowego.

**Nie testuj pierwszego uruchomienia bez flagi `--test` na prawdziwej bazie.**

## Ważne wymagania

Pakiet nie wymaga Pythona, ale **wciąż wymaga odpowiednich bibliotek
systemowych Linux**, graficznego środowiska X11/Wayland oraz sterowników
Qt. Może nie działać na każdej dystrybucji (glibc, xcb, OpenGL).

**Tesseract z danymi `pol`/`eng` nie jest dołączany** — trzeba go
zainstalować systemowo do OCR skanów. **Ollama i model AI również
pozostają osobnymi instalacjami**.

Program nie wykonuje przelewów i nie wysyła rachunków do chmury.

## Dystrybucja a licencje

Wersja binarna zawiera m.in. biblioteki Qt/PySide6 i PDFium. Przed
publicznym wydaniem wymagamy **szczegółowego audytu użytych wersji
komponentów i pełnego kompletu ich licencji**.

- Qt/PySide6: zobowiązania LGPL, w szczególności możliwość wymiany
  współdzielonych bibliotek / ponownego połączenia oraz informacje
  licencyjne i źródła bibliotek.
- PDFium/pypdfium2: licencja PDFium i teksty licencji zależności
  binarnych muszą towarzyszyć dystrybucji.
- PolyForm Noncommercial: zasady użytkowania kodu Świstaka;
  starsze wydania na GPL zachowują swoją licencję.
- PyInstaller: jego wyjątek od GPL pozwala na pakowanie aplikacji
  na różnych licencjach, jednak nie zwalnia z praw pozostałych
  bibliotek.

Paczka jest przeznaczona do prób **autora**; nie została zatwierdzona
jako zgodna licencyjnie paczka do szerokiej dystrybucji.

Oficjalne źródła:
- https://www.qt.io/development/open-source-lgpl-obligations
- https://github.com/pypdfium2-team/pypdfium2#licensing
- https://pyinstaller.org/en/stable/license.html

## Budowanie lokalnie

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-build.txt
.venv/bin/python -m tools.build_linux_binary
```

Budowanie nie czyta katalogu danych użytkownika i nie dołącza
prywatnych rachunków. Dołącza pliki źródłowe z `assets`, `i18n`
i historyczne migracje SQL **bez ich zmiany**.
