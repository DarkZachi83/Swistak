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
| [pdf2image](https://pypi.org/project/pdf2image/) | `>=1.17,<2` | **MIT**, ALE używa zewnętrznych programów **Poppler** | Rasteryzacja skanu dla OCR | **WYSOKIE RYZYKO:** licencja samego wrappera nie rozwiązuje kwestii Popplera |
| [pytesseract](https://github.com/madmaze/pytesseract) | `>=0.3.13,<1` | **Apache-2.0** | Wywoływanie lokalnego silnika Tesseract | **INFORMACYJNIE:** uwzględnić notices Apache, niezależnie audytować silnik OCR |

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
| [Pillow](https://python-pillow.github.io/) | MIT-CMU | Wymaga własnego tekstu copyright/licencji. |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | Apache-2.0 / BSD-3-Clause + PDFium: BSD i zależności | Końcowe koła mogą zawierać binarny PDFium i licencje jego komponentów; sprawdzić `BUILD_LICENSES/`. **Kandydat do zastąpienia Popplera dla OCR**. |
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
| [Poppler](https://poppler.freedesktop.org/) — m.in. `pdftoppm` | **System użytkownika**, wywoływany przez pdf2image | GPL-2.0-only OR GPL-3.0-only (dobór wersji i plików do weryfikacji) | **WYSOKIE RYZYKO** dla zamkniętej lub noncommercial dystrybucji. Nie dołączać do instalatora bez osobnego przeglądu skutków GPL; rozważyć przejście na pypdfium2. Wywołanie osobnego procesu nie przesądza samo o kompatybilności. |
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

### B. Poppler i pakowanie OCR — priorytet

Aktualna ścieżka skanu to:
`pdf2image → (program Popplera pdftoppm) → obraz → pytesseract`.

**To główny punkt ryzyka** dla planowanego modelu
PolyForm Noncommercial + płatna licencja biznesowa. Na etapie
testów użytkownik instaluje Popplera oddzielnie.
Przed przygotowaniem instalatora:
1. Porównać OCR z rasteryzacją przez `pypdfium2` (już jest zależnością
   pośrednią pdfplumber) lub przez odpowiednio licencjonowany Qt PDF.
2. Przetestować różne formaty skanów i wydajność w Windows/Linux.
3. Jeśli pozostanie Poppler — uzyskać profesjonalną analizę skutków
   GPL dla konkretnego modelu pakowania i integracji.

**Źródła:**  
- https://formulae.brew.sh/formula/poppler  
- https://pypdfium2-team.github.io/pypdfium2/readme.html

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
