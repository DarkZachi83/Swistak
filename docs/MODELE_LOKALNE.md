# Świstak — wyszukiwanie lokalnych modeli (jak w AI Bobrze)

**Stan:** wdrożone na `main`. Dotyczy ustawień i wyszukiwarki modeli;
nie wymaga zmian schematu SQLite.

## Jak korzystać?

1. Wybierz **Ustawienia → Konfiguruj**.
2. Obok edytowalnej listy **Domyślny model Ollama** kliknij
   **Szukaj modeli lokalnych…**.
3. Zaznacz **Przeszukuj standardowe lokalizacje**, jeśli chcesz objąć
   Ollamę, LM Studio, Hugging Face, llama.cpp i GPT4All.
4. Opcjonalnie kliknij **Wskaż katalog…**. Możesz przeszukiwać jednocześnie
   foldery standardowe i własny albo odznaczyć lokalizacje standardowe,
   aby ograniczyć skanowanie do wybranego katalogu.
5. Kliknij **Szukaj ponownie**, jeśli zmieniasz zakres.
6. W zakładce **Dostępne w Ollamie** wybierz model i kliknij
   **Użyj zaznaczonego modelu**.
7. W oknie Ustawień wybierz **Zapisz**. Zapamiętana zostanie nazwa
   modelu i ostatni własny katalog.

Zasada wyboru: **tylko modele zgłoszone przez działającą lokalną Ollamę**
są gotowe do analizy dokumentów. Lista na dysku to informacja o
potencjalnych modelach, nie gwarancja obsługi przez aktualny backend.

Jeśli Ollama jest wyłączona, można nadal obejrzeć pliki na dysku.
Model zapamiętany wcześniej w polu Ustawień pozostaje dostępny po
ponownym uruchomieniu Ollamy. Pole można też edytować ręcznie.

## Skąd Świstak bierze wyniki?

- **Ollama (gotowe):** lokalne `http://127.0.0.1:11434/api/tags` bez proxy;
  odfiltrowane modele embeddingowe.
- **Ollama (dysk):** domyślny magazyn `~/.ollama/models`, katalogi usług
  systemowych lub `OLLAMA_MODELS`; odczyt manifestów i istnienia blobów.
- **LM Studio:** `~/.lmstudio/models` i starsza pamięć podręczna.
- **Hugging Face:** `HF_HOME`, `HF_HUB_CACHE` lub standardowy XDG cache.
- **llama.cpp / GPT4All:** ich typowe lokalizacje i zmienne środowiskowe.
- **Własny katalog:** folder wybrany w dialogu, w tym GGUF
  lub cały katalog magazynu Ollamy.

Na dysku odczytywane są jedynie nazwy i krótkie nagłówki GGUF,
`config.json` dla tekstowych modeli Transformers oraz manifesty Ollamy.
Plików `safetensors` i wag PyTorch nie otwieramy. Program nie instaluje,
nie przenosi, nie usuwa i nie uruchamia znalezionych modeli.

## Bezpieczeństwo i ograniczenia

Skan działa poza wątkiem GUI, z ograniczoną głębokością i liczbą plików.
Nie chodzi po zewnętrznych stronach i nie wysyła plików do chmury.
Nie wszystkie formaty wag można rozpoznać na podstawie katalogu.
Świstak może wyświetlić model jako „na dysku”, choć wymaga on
jeszcze importu do Ollamy.

Katalog użytkownika zapisany jest wyłącznie w prywatnym `settings.json`,
oddzielnie od bazy rachunków. Zmiana nazwy modelu nie uruchamia
automatycznie analizy faktury.

## Testy

```bash
./.venv/bin/python -m unittest testy.test_ustawienia_modele -v
./.venv/bin/python -m unittest discover -s testy -v
```

Wszystkie testowe foldery i pliki modeli są syntetyczne.
