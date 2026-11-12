# Świstak — rejestr zależności i licencji

**Stan przeglądu: 2026-11-10 · WERSJA ROBOCZA · nie stanowi opinii prawnej.**

Rejestr opisuje komponenty występujące w kodzie, `requirements.txt`,
pobrane w przykładowym środowisku Python oraz wymagane programy systemowe.
**Nie jest certyfikatem zgodności instalatora ani kompletnym SBOM.**
Wersje w `requirements.txt` są zakresami, a nie zamrożonymi wersjami.
Przed pierwszym wydaniem należy sporządzić rzeczywistą listę wszystkich
plików binarnych, bibliotek, podzespołów i modeli w *konkretnym artefakcie*.

**Obecnie `main` Świstaka jest na GPL-3.0-only.** Projekt zmiany
na PolyForm Noncommercial 1.0.0 znajduje się w gałęzi
`proposal/licencja-home-business` i nie zmienia zasad wcześniejszych wydań.

## Znaczenie statusów

- **DO SPRAWDZENIA** — konieczna kontrola zobowiązań przed publikacją pakietu.
- **WYSOKIE RYZYKO** — element GPL lub złożona zależność, która może wpłynąć
  na projekt dystrybucji. Nie interpretować jako automatyczny zakaz użycia.
- **ODRĘBNE WARUNKI** — własna umowa/licencja, inna niż typowe MIT/Apache.
- **INFORMACYJNIE** — znana deklarowana licencja; mimo to należy
  dołączyć wymagane informacje prawne, jeśli komponent jest dystrybuowany.

## 1. Bezpośrednie zależności Python (requirements.txt)

| Komponent | Wersja w projekcie | Licencja deklarowana / dostępne opcje | Użycie | Wnioski dla dystrybucji |
|---|---|---|---|---|
| [PySide6](https://pypi.org/project/PySide6/) | `>=6.8,<7` | Qt for Python: **LGPL-3.0 / GPL-3.0 / licencja komercyjna**; dokładne warunki zależą od modułu | GUI i Qt PDF | **DO SPRAWDZENIA:** obowiązki LGPLv3 (informacje prawne, prawa dotyczące bibliotek, wymiana bibliotek, brak blokowania dozwolonego reverse engineeringu) i lista spakowanych modułów |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | `>=0.11,<1` | **MIT** | Ekstrakcja tekstu z PDF | **INFORMACYJNIE:** dołączyć wymaganą informację o prawach/licencję przy dystrybucji |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | `>=5.9,<6` | **Apache-2.0 / BSD-3-Clause**, PDFium ma osobne zależności/NOTICE | Domyślna rasteryzacja skanów OCR | **DO SPRAWDZENIA:** prawa i notices binariów PDFium w konkretnym wheel |
| [pytesseract](https://github.com/madmaze/pytesseract) | `>=0.3.13,<1` | **Apache-2.0** | Wywoływanie lokalnego silnika Tesseract | **INFORMACYJNIE:** uwzględnić notices Apache, niezależnie audytować silnik OCR |
| [Pillow](https://python-pillow.github.io/) | `>=12.2,<14` | **MIT-CMU** | Obraz PIL przy OCR PDFium i generowanie skanów do testów | **INFORMACYJNIE:** dołączyć tekst licencji i copyright |
| [zxing-cpp](https://github.com/zxing-cpp/zxing-cpp) | `>=3.1.1,<4` | **Apache-2.0** | Lokalny dekoder QR | **DO SPRAWDZENIA:** licencja i notices dokładnego binarnego wheel przed wydaniem |

## 2. Zależności pośrednie / pakiety, które mogą trafić do instalatora

Nie każda zależność wystąpi w każdej wersji środowiska. Wpływ wersji
PySide6 i sposobu pakowania jest szczególnie duży. Po instalacji
`python -m tools.audyt_licencji` sprawdza wersje i metadane
widocznych pakietów, ale **nie wydaje opinii o zgodności licencji**.

| Komponent | Znana licencja / charakter | Uwagi |
|---|---|---|
| PySide6-Essentials, PySide6-Addons, PySide6-Pdf, shiboken6 | Qt for Python — LGPL/GPL/komercyjna zależnie od modułu | Sprawdzić **dokładne pliki wheel**. Świstak używa `QtWidgets`, `QtGui`, `QtCore` i `QtPdf`. |
| PySide6-WebEngine (jeśli zainstalowany) | Qt WebEngine LGPL/GPL/komercyjna + **wiele licencji Chromium** | Świstak **nie importuje** WebEngine, więc **nie dołączać bez potrzeby** do instalatora. |
| [pdfminer.six](https://github.com/pdfminer/pdfminer.six) | MIT | Parser tekstowy wykorzystywany przez pdfplumber. |

| [pdf2image](https://pypi.org/project/pdf2image/) | MIT, używa Popplera | **TYLKO opcjonalne testy** `requirements-compare.txt`; nie jest zależnością produkcyjną. |
| [charset-normalizer](https://pypi.org/project/charset-normalizer/) | MIT | Pośrednio przez pdfminer.six. |
| [cryptography](https://pypi.org/project/cryptography/) | Apache-2.0 **OR** BSD-3-Clause | Pośrednio przez pdfminer.six; może zawierać dalsze binarne zależności. |
| [cffi](https://pypi.org/project/cffi/) | MIT-0 (dla obecnych wersji; sprawdzić konkretny wheel) | Zależność cryptography. |
| [pycparser](https://pypi.org/project/pycparser/) | BSD-3-Clause | Zależność cffi. |
| [packaging](https://pypi.org/project/packaging/) | Apache-2.0 **OR** BSD-2-Clause | Zależność pytesseract. |

Powyższe pośrednie zależności są **rejestrem poglądowym**, nie
wyczerpującą listą pakietów. Pojawienie się nowej zależności w
wydaniu oznacza konieczność aktualizacji tego dokumentu oraz
zebrania licencji z faktycznie zbudowanych pakietów.

## 3. Programy i modele zewnętrzne

| Składnik | Dystrybucja na dziś | Licencja / warunki | Ocena i czynność |
|---|---|---|---|
| [Poppler](https://poppler.freedesktop.org/) — `pdftoppm` | **Tylko osobny test porównawczy** `requirements-compare.txt` | GPL-2.0-only OR GPL-3.0-only (zależnie od plików) | **NIE jest wymagany** przy normalnym OCR na PDFium; nie dołączać do instalatora bez oddzielnego przeglądu GPL. |
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | System użytkownika | Apache-2.0 | Można rozważyć bundling, ale trzeba uwzględnić licencję i komponenty binarne oraz notices. |
| [tessdata](https://github.com/tesseract-ocr/tessdata) `pol`, `eng` | System użytkownika | Apache-2.0 dla repozytorium tessdata | Przy dystrybucji modeli językowych dołączyć odpowiednie notices i upewnić się, z jakiego pakietu pochodzą. |
| [Ollama](https://github.com/ollama/ollama/blob/main/LICENSE) | Instalowana **osobno** przez użytkownika | MIT (sam silnik) | Aplikacja korzysta z lokalnego API `127.0.0.1:11434`, nie sprzedaje Ollamy jako części własnego produktu. Przyszły bundling wymaga notices i przeglądu licencji składników. |
| [Gemma 3:4b](https://ai.google.dev/gemma/terms/) | Pobierana **osobno** przez użytkownika przez Ollamę | **Gemma Terms of Use** + Gemma Prohibited Use Policy; to **nie** MIT/Apache | **ODRĘBNE WARUNKI.** Dopuszczalne przypadki użytku i redystrybucji zależą od warunków Google; bundling wag wymaga zgodnego powiadamiania odbiorców i dalszych obowiązków. |
| Python / standard library | Interpreter użytkownika (w przyszłości może wejść do paczki) | PSF License i licencje komponentów | Dystrybucja spakowanego interpretera oznacza dołączenie stosownych informacji prawnych. |

## 4. Najważniejsze decyzje i blokery wydania

### A. Qt/PySide6 i Qt PDF — przegląd warunków LGPL

Qt pozwala tworzyć aplikacje o odrębnej licencji, jeśli spełnia się
wymagania LGPLv3 dotyczące użytych modułów (lub dysponuje ważną
licencją komercyjną). **Nie wystarczy dopisać nazwę biblioteki do README.**
Trzeba obejrzeć konkretną dystrybucję i przygotować informacje o
prawach odbiorcy do bibliotek. Niektóre moduły Qt są tylko na GPL;
`QtPdf` należy sprawdzić według jego własnej dokumentacji.

**Źródła:**  
- https://www.qt.io/development/open-source-lgpl-obligations  
- https://doc.qt.io/qt-6/licensing.html  
- https://doc.qt.io/QT-6/qtpdf-index.html  
- https://doc.qt.io/qtforpython-6.10/commercial/index.html

### B. PDFium jest domyślny, Poppler tylko do porównania — eksperyment

Nowa domyślna ścieżka skanu to
`pypdfium2 → PDFium → obraz PIL → pytesseract`.
Aplikacja **nie wymaga teraz Popplera** ani pakietu `pdf2image` podczas
normalnej pracy. Wyświetlanie PDF nadal wykorzystuje QtPdf, a odczyt
warstwy tekstowej — pdfplumber.

Poprzednią ścieżkę
`pdf2image → Poppler (pdftoppm) → PIL → pytesseract`
zachowano jedynie jako **opcjonalne porównanie** po instalacji
`requirements-compare.txt` i systemowego Popplera.
W `tools/porownaj_ocr.py` oba silniki otrzymują dokładnie takie same
syntetyczne skany i ustawienia Tesseract.

**Zmniejszyło to zależność produkcyjną od komponentów GPL**,
ale nie usuwa obowiązków LGPL Qt/PySide6 ani licencji
składników binarnych PDFium i modeli Gemma. Przed instalatorem
trzeba zweryfikować licencje PDFium (również jego NOTICE),
a nie polegać jedynie na etykiecie pypdfium2.

[Dziennik eksperymentu](docs/PDFIUM_OCR_BENCHMARK.md).

### B.1 Licencje binariów PDFium i identyfikowalność wydań

Zgodnie z dokumentacją producenta, sam wrapper pypdfium2 ma warianty
**Apache-2.0 / BSD-3-Clause**, ale PDFium ma licencję typu BSD oraz
**wiele licencji dołączonych zależności**. Nie należy utożsamiać
licencji wrappera z uprawnieniami do dystrybuowania całego wheel.

- Do wydania dołączyć teksty licencji PDFium i zależności dostarczone
  w `BUILD_LICENSES/` (lub w odpowiednich katalogach wheel).
- Dla każdej platformy sprawdzić **konkretny build i konfigurację**,
  nie tylko numer wersji pakietu. Niektóre kompilacje mogą używać
  runtime `libgcc` z odrębnymi obowiązkami licencyjnymi.
- Dokumentacja i przykłady **pypdfium2** są na **CC-BY-4.0**;
  dołączanie ich do paczki ma inne obowiązki niż samo używanie
  biblioteki.
- Narzędzie `python -m tools.sprawdz_pdfium` wypisuje nazwy plików
  licencyjnych i binarnych z zainstalowanego wheel. To **nie jest**
  potwierdzenie ich kompletności.
- Wydanie należy przygotować z zablokowanymi wersjami i hashami
  artefaktów; kontrolować zależności i nie wprowadzać automatycznie
  nowej wersji biblioteki w dniu wydania.
- PDFium nie jest bezpieczny w równoległych wątkach. Nasze funkcje
  PDFium muszą współdzielić blokadę, a wszystkie obiekty PDFium
  zwalniać jawnie jeszcze przed jej zwolnieniem.
- Nie generować automatycznych zgłoszeń i PR-ów do upstream
  **pypdfium2**: autorzy wyraźnie zakazują AI-generated issues/PRs.
  Jeśli kiedyś pojawi się rzeczywisty błąd, powinien zostać
  samodzielnie odtworzony i sprawdzony przez człowieka, zgodnie
  z zasadami projektu.

Dokumentacja upstream:
[pypdfium2 Licensing](https://pypdfium2-team.github.io/pypdfium2/readme.html#licensing)
i [threading](https://pypdfium2.readthedocs.io/en/stable/python_api.html#incompatibility-with-threading).

### C. Gemma 3 — nie mylić silnika z modelem

Ollama ma licencję MIT, ale **wagi Gemma 3 nie są MIT**.
Należy rozróżniać **zdalne/local API**, użycie modelu,
redystrybucję wag i obowiązki wobec odbiorców.
Świstak powinien **nie pobierać ani nie dołączać modeli
bez wyraźnej decyzji użytkownika**, a ich licencje
prezentować niezależnie.

**Źródła:**  
- https://github.com/ollama/ollama/blob/main/LICENSE  
- https://ai.google.dev/gemma/terms/  
- https://ai.google.dev/gemma/prohibited_use_policy

### D. Historia GPL a nowe warunki

Wersje Świstaka opublikowane dotychczas jako GPL-3.0-only zachowują
swoje warunki. Zmiana licencji przyszłych wersji wymaga praw do kodu.
Dokument obejmuje **jedynie propozycję** i nie jest próbą
retroaktywnej zmiany praw.

## 5. Co musi być gotowe przed publikacją instalatora?

- [ ] Zatwierdzona licencja nowej wersji i prawa autorskie do kodu.
- [ ] Sprawdzone licencje **każdego** spakowanego wheel i programu.
- [ ] Rozstrzygnięte skutki użycia Popplera lub zamieniona rasteryzacja.
- [ ] Zweryfikowane warunki **Qt LGPLv3** i użytych konkretnych modułów.
- [ ] Spisane binarne zależności PDFium/Qt wraz z własnymi licencjami.
- [ ] Przygotowane NOTICE/third-party license texts wymagane przez
      faktycznie dołączone komponenty (nie tylko odnośniki).
- [ ] Gemma i Ollama instalowane osobno lub licencjonowane odpowiednio
      do wybranego sposobu dystrybucji.
- [ ] Lockfile i SBOM dla konkretnej wersji `Windows` oraz `Linux`.
- [ ] Procedura aktualizacji listy zależności przy każdej aktualizacji.
- [ ] Przegląd prawny całego pakietu przed pierwszą sprzedażą.

## 6. Jak aktualizować rejestr?

1. Zmiana `requirements.txt` / zależności importowanych w kodzie:
   uzupełnij tabelę i `licencje/rejestr.json`.
2. Uruchom `python -m tools.audyt_licencji --check` po instalacji
   środowiska. Narzędzie wykrywa **brak opisu bezpośredniej zależności**.
3. Sprawdź metadane dokładnych wersji pakietów, a nie tylko ich nazw.
4. W czasie budowy release zapisz lockfile/SBOM oraz dołącz
   wymagane pełne licencje i notices do dystrybucji.
5. Zawsze odrębnie sprawdzaj nowe modele LLM i pliki wag.

**Ta tabela nie nadaje ani nie odbiera praw do oprogramowania stron
trzecich. Wiążące są licencje ich właścicieli.**
