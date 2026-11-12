# Świstak — kody QR (lokalnie)

Nowy przycisk **Odczytaj QR** w etapie **Odczyt PDF / skanu** otwiera osobne okno.

- Strony PDF rasteryzowane są przez istniejące PDFium ze wspólną blokadą wątków.
- Kody są odczytywane lokalnie przez ZXing-C++ (Apache-2.0); nie korzystamy z Tesseract ani z Ollamy.
- W wybranych polskich kodach płatniczych rozpoznajemy pola: NIP, PL, NRB, kwota w groszach, odbiorca, tytuł przelewu. NRB jest walidowany sumą kontrolną.
- Inne kody pozostają wyłącznie tekstem. **Żadne URL nie są automatycznie otwierane**, a żadne instrukcje z QR nie są wykonywane.
- Przycisk „Przenieś kwotę i konto do formularza” jest aktywny tylko wtedy, gdy wykryto dokładnie jeden rozpoznany kod płatniczy. Użytkownik musi potwierdzić operację; dwa pola formularza mogą zostać nadpisane. **Brak zapisu do SQLite i brak inicjowania przelewów**.
- Wyniki nie są zapisywane w historii ani wysyłane przez Internet. Odczyt ma limit 30 stron i maksymalnie 30 kodów.
- Inne formaty QR płatności mogą wymagać rozszerzenia parsera.
- QR nie zastępuje danych o terminie płatności, kategorii ani okresie rozliczeniowym. Nadal należy sprawdzić wartości z dokumentem.

Testy używają fikcyjnego kodu i sztucznego dokumentu PDF. **Prawdziwe dokumenty użytkownika nigdy nie trafiają do repozytorium, testów CI ani logów.**

Testy (po instalacji requirements.txt):

~~~bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest testy.test_kody_qr -v
~~~
