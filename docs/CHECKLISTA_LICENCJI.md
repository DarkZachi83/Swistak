# Checklista licencji i dystrybucji — Świstak

**Wersja robocza, 10 listopada 2026.** Ta lista nie jest opinią prawną ani zgodą na sprzedaż.

## Zanim zaczynamy nowy projekt

- [ ] Potwierdzić właściciela praw do kodu i dopuszczalność jego dalszego licencjonowania.
- [ ] Wybrać licencję przed pierwszym commitem i opisać zamierzony użytek domowy oraz biznesowy.
- [ ] Zdefiniować sposób publikacji kodu: open source / source-available / prywatny.
- [ ] Sporządzić listę planowanych bibliotek, modeli AI, danych modelowych i zewnętrznych narzędzi.
- [ ] Sprawdzić licencje **wszystkich komponentów**, w tym zależności pośrednich i skompilowanych binariów.
- [ ] Zdecydować, czy program zależy od osobnej instalacji narzędzi, czy będzie je dołączał do instalatora.

## Dodając kolejną bibliotekę

- [ ] Wpisać nazwę, wersję, licencję, źródło i zastosowanie do `licencje/rejestr.json`.
- [ ] Sprawdzić, czy licencja nie wprowadza obowiązku udostępniania kodu, notices lub możliwości podmiany bibliotek.
- [ ] Uruchomić `python -m tools.audyt_licencji --check`.
- [ ] Zaktualizować `THIRD_PARTY_LICENSES.md`.
- [ ] Sprawdzić i udokumentować sposób dystrybucji nowego komponentu.

## Przed pierwszym instalatorem Świstaka

- [ ] **Qt/PySide6:** lista dokładnie użytych modułów, LGPLv3, sposób linkowania, notices i prawa do wymiany bibliotek.
- [ ] **Poppler:** osobna instalacja lub pełny przegląd GPL przed dołączeniem binariów.
- [ ] **Tesseract:** komplet licencji silnika OCR i modeli językowych `pol/eng`.
- [ ] **PDFium/pypdfium2:** notices bibliotek wewnątrz wheel.
- [ ] **Ollama:** oddzielny instalator lub zgodna redystrybucja na MIT.
- [ ] **Gemma 3:** odrębna kontrola warunków Google i sposobu dostarczenia wag.
- [ ] **Python:** wersja interpretera i licencje komponentów dołączanych w runtime.
- [ ] Wygenerować listę pakietów z dokładnymi wersjami oraz rzeczywistych binariów spakowanych do `dist/`.
- [ ] Dołączyć licencje i informacje copyright do instalatora tam, gdzie jest to wymagane.
- [ ] Przeprowadzić test instalacji na czystym Linuxie i Windowsie.
- [ ] Weryfikacja prawna warunków **Home / Business** oraz historycznych wydań GPL.
- [ ] Dopiero wtedy udostępnić plik instalacyjny i opublikować wydanie z sumą SHA-256.

## Ważne rozróżnienie

**Audyt zależności źródłowych ≠ audyt dystrybuowanego instalatora.**
Prawdziwe obowiązki prawne zależą od dokładnych wersji i dołączonych plików.

Zobacz [rejestr zależności](../THIRD_PARTY_LICENSES.md) oraz
[propozycję licencji Home / Business](LICENCJONOWANIE.md).
