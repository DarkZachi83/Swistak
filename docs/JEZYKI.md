# Menu i tłumaczenia Świstaka

**Etap:** gałąź \`feature/menu-i-jezyki-live\`.

Wzorcem projektu jest **AI Bóbr** (analiza \`aibobr/i18n/\`,
\`aibobr/gui/main_window.py\`, testy \`tests/test_i18n.py\`).
W Świstaku warstwę i18n napisano samodzielnie, bez kopiowania GPL-owego
kodu Bobra do projektu na PolyForm Noncommercial.

## Górne menu

- **Plik / File:** import PDF, odśwież listę dokumentów, zakończ.
- **Ustawienia / Settings:** dialog konfiguracji domyślnego modelu Ollama
  i podgląd katalogu prywatnych danych.
- **Języki / Languages:** język systemu, polski, angielski. Aktywna opcja
  jest oznaczona (radio). Język systemu to zawsze opcja pusta \`""\`,
  więc zmiana ustawień OS zadziała przy kolejnym uruchomieniu.
- **O programie / About:** informacje o zastosowaniu, autorze,
  lokalności danych i repozytorium.

## Dlaczego przełączanie działa bez restartu?

AI Bóbr trzyma teksty w słownikach \`pl.json\`/\`en.json\`, zapamiętuje
wybór języka i odtwarza ekran w nowym języku. Świstak stosuje
słowniki z tym samym podejściem, ale **nie buduje widgetów ponownie**:
\`OknoGlowne._retranslate_ui()\` zmienia ich \`setText()\`, nazwy kart,
menu, placeholdery, nagłówki tabel i zapamiętane komunikaty.

To ważne, bo zniszczenie formularza mogłoby utracić wpisane kwoty,
zaznaczenie PDF, tekst OCR, wynik Ollamy lub aktywną zakładkę.
Identyfikatory danych w SQLite, znaczniki pól JSON oraz nazwy kategorii
w bazie pozostają stabilne i nie są uzależnione od języka prezentacji.

## Ustawienia

Konfiguracja jest oddzielona od bazy rachunków:
- Linux: \`~/.config/swistak/settings.json\` (lub \`XDG_CONFIG_HOME\`)
- Windows: \`%APPDATA%/Swistak/settings.json\`
- macOS: \`~/Library/Application Support/Swistak/settings.json\`

Dostępne ustawienia: \`language\` (puste=systemowy; \`pl\`, \`en\`) oraz
\`ollama_model\`. Plik aktualizowany jest atomowo. Dane rachunków nie są
modyfikowane przy zmianie języka.

## Dodawanie nowego języka

1. Utwórz \`i18n/de.json\`, zachowując wszystkie klucze i nazwy pól
   formatowania z istniejących \`pl.json\`/\`en.json\`.
2. Dodaj kod do \`LANGUAGES\` w \`i18n/__init__.py\`.
3. Rozszerz walidację ustawień w \`ustawienia.py\`.
4. Uzupełnij test \`testy/test_i18n.py\`, uruchom testy GUI offscreen.
5. Nigdy nie tłumacz kluczy JSON, statusów i nazw kategorii zapisanych
   w SQLite. Tłumacz wyłącznie ich prezentację.
