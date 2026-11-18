# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Proces importu, OCR, analizy i zapisu faktury."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSplitter, QStackedWidget, QStyle, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

from ai_core.errors import ExtractionContextExceeded
from gui.analiza_worker import ZadanieAnalizy
from gui.dialog_kategorie import DialogKategorie
from gui.dialog_qr import DialogQR
from gui.dialog_wzorca import zaakceptuj_wzorzec
from gui.formularz_faktury import FormularzFaktury, StanFormularza
from gui.odczyt_worker import ZadanieOdczytu
from gui.okno_wzorcow import OknoWzorcow
from gui.podglad_pdf import PodgladPDF
from gui.uklad import Siatka
from gui.zapis_faktury import zapisz_z_potwierdzeniem
from i18n import t
from uslugi.analiza_llm import AnalizaModelu, ETYKIETY, POLA, ocena_json
from uslugi.dopasowanie_wzorca import Dopasowanie, dopasuj, zaproponuj_wzorzec
from uslugi.finanse import DataPlatnosciZPrzyszlosci, sprawdz_date_platnosci
from uslugi.geometria import Zaznaczenie
from uslugi.odczyt_pdf import WynikOdczytu
from uslugi.propozycja_wzorca import zaproponuj_aktualizacje
from uslugi.rachunki import (
    BrakDatyOplacenia, BrakDatyWystawienia, DaneRachunku, RejestrRachunkow, grosze_na_kwote,
)
from uslugi.wzorce import MagazynWzorcow


class KreatorFaktury(QScrollArea):
    """Otwarty PDF, odczyt, analiza i świadomy zapis faktury."""

    ETAP_ODCZYT = 0
    ETAP_ANALIZA = 1
    ETAP_EDYCJA = 2
    ETAP_FAKTURA = 3
    ETAP_DOKUMENTY = 4
    ETAPY = ("tab.read", "tab.ai", "tab.edit", "tab.bill", "tab.documents")

    pokaz_kreator = Signal()
    pokaz_agenta = Signal()
    wybor_modelu = Signal()
    analiza_zadana = Signal()
    odswiez_dokumenty = Signal()
    kategorie_zmienione = Signal()
    faktura_zapisana = Signal(int)
    status_zmieniony = Signal(str, dict)

    def __init__(self, rejestr: RejestrRachunkow, prefs: dict):
        super().__init__()
        self.rejestr = rejestr
        self._messages: dict[QLabel, tuple[str, dict]] = {}
        self.magazyn_wzorcow = MagazynWzorcow(rejestr.katalog)
        self._dopasowanie_wzorca: Dopasowanie | None = None
        self._aktywny_wzorzec: dict | None = None
        self._wzorzec_pominiety = False
        self._tekst_dopasowania = ""
        self._wzorzec_dokument_id: int | None = None
        self._komentarze_wzorca: dict[str, str] = {}
        self.aktualny_dokument_id: int | None = None
        self._zapisany_formularz: StanFormularza | None = None
        self._wybrany_obszar: Zaznaczenie | None = None
        self._zadanie_odczytu: ZadanieOdczytu | None = None
        self._zadanie_ai: ZadanieAnalizy | None = None
        self._analiza: AnalizaModelu | None = None
        self._analiza_dokument_id: int | None = None
        self._aktualizuje_tabele_ai = False
        self._pola_potwierdzone_recznie: set[str] = set()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        tresc_kreatora = QWidget()
        self.setWidget(tresc_kreatora)
        pion = QVBoxLayout(tresc_kreatora)
        pion.setContentsMargins(0, 0, 0, 0)
        pion.setSpacing(12)

        pasek = QFrame()
        pasek.setObjectName("pasek")
        pasek_uklad = QVBoxLayout(pasek)
        pasek_uklad.setContentsMargins(8, 7, 8, 7)
        grupy_pdf = Siatka(3, szerokosc=240)
        pasek_uklad.addWidget(grupy_pdf)

        self.otworz_przycisk = QPushButton()
        self.otworz_przycisk.clicked.connect(self.wybierz_plik)
        grupy_pdf.dodaj(self.otworz_przycisk)

        strony_panel = QWidget()
        przyciski = QHBoxLayout(strony_panel)
        przyciski.setContentsMargins(0, 0, 0, 0)

        self.poprzednia = QPushButton()
        self.poprzednia.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.poprzednia.clicked.connect(lambda: self._zmien_strone(-1))
        przyciski.addWidget(self.poprzednia)

        self.strony = QLabel()
        self.strony.setMinimumWidth(100)
        self.strony.setAlignment(Qt.AlignmentFlag.AlignCenter)
        przyciski.addWidget(self.strony)

        self.nastepna = QPushButton()
        self.nastepna.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self.nastepna.clicked.connect(lambda: self._zmien_strone(1))
        przyciski.addWidget(self.nastepna)
        grupy_pdf.dodaj(strony_panel)
        powiekszenie = Siatka(4)
        for etykieta, akcja in (
            ("−", lambda: self.podglad.powieksz(0.8)),
            ("+", lambda: self.podglad.powieksz(1.25)),
            ("Szerokość", lambda: self.podglad.dopasuj_szerokosc()),
            ("Dopasuj", self.podglad_dopasuj),
        ):
            przycisk = QPushButton(etykieta)
            przycisk.clicked.connect(akcja)
            if etykieta == "Szerokość":
                self.btn_szerokosc = przycisk
            if etykieta == "Dopasuj":
                self.btn_dopasuj = przycisk
            powiekszenie.dodaj(przycisk)
        grupy_pdf.dodaj(powiekszenie)
        pion.addWidget(pasek)

        obszar_pracy = QVBoxLayout()
        obszar_pracy.setSpacing(10)
        self.obszar_pracy = obszar_pracy

        # Stała, pionowa nawigacja z etykietami poziomo (jak w menedżerach PDF).
        pasek_etapow = QFrame()
        pasek_etapow.setObjectName("etapyPanel")
        self.pasek_etapow = pasek_etapow
        uklad_etapow = QVBoxLayout(pasek_etapow)
        uklad_etapow.setContentsMargins(7, 12, 7, 12)
        self.tytul_etapow = QLabel()
        self.tytul_etapow.setObjectName("podpowiedz")
        uklad_etapow.addWidget(self.tytul_etapow)
        self.nawigacja = QListWidget()
        self.nawigacja.setObjectName("etapyMenu")
        self.nawigacja.setSpacing(3)
        self.nawigacja.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nawigacja.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for _ in self.ETAPY:
            self.nawigacja.addItem("")
        uklad_etapow.addWidget(self.nawigacja, 1)
        obszar_pracy.addWidget(pasek_etapow)

        dzielnik = QSplitter(Qt.Orientation.Horizontal)
        self.dzielnik = dzielnik
        self.podglad = PodgladPDF()
        self.podglad.setMinimumSize(190, 190)
        self.podglad.zaznaczono.connect(self._zaznaczenie)
        self.podglad.zmiana_strony.connect(self._aktualizuj_nawigacje)
        dzielnik.addWidget(self.podglad)

        self.karty = QStackedWidget()
        self.karty.addWidget(self._zbuduj_odczyt())
        self.karty.addWidget(self._zbuduj_analize())
        self.formularz = FormularzFaktury(self.rejestr, self)
        self.karty.addWidget(self.formularz.edycja)
        self.karty.addWidget(self.formularz.podsumowanie)
        self.formularz.btn_przejdz_faktura.clicked.connect(
            lambda: self.karty.setCurrentIndex(self.ETAP_FAKTURA)
        )
        self.formularz.btn_powrot_edycja.clicked.connect(
            lambda: self.karty.setCurrentIndex(self.ETAP_EDYCJA)
        )
        self.formularz.btn_dodaj_kategorie.clicked.connect(self._dodaj_kategorie)
        self.formularz.zapisz_przycisk.clicked.connect(self._zapisz_rachunek)
        self.formularz.btn_proponuj_wzorzec.clicked.connect(self._zaproponuj_zapis_wzorca)
        self.karty.addWidget(self._zbuduj_liste())
        self.nawigacja.currentRowChanged.connect(self.karty.setCurrentIndex)
        self.karty.currentChanged.connect(self.nawigacja.setCurrentRow)
        self.karty.currentChanged.connect(self._zmieniony_etap)
        self.nawigacja.setCurrentRow(self.ETAP_ODCZYT)
        dzielnik.addWidget(self.karty)
        dzielnik.setChildrenCollapsible(False)
        dzielnik.setStretchFactor(0, 1)
        dzielnik.setStretchFactor(1, 1)
        dzielnik.setSizes([610, 750])
        obszar_pracy.addWidget(dzielnik, 1)
        pion.addLayout(obszar_pracy, 1)

        self.opis_zaznaczenia = QLabel()
        self.opis_zaznaczenia.setObjectName("podpowiedz")
        self.opis_zaznaczenia.setWordWrap(True)
        pion.addWidget(self.opis_zaznaczenia)
        self._aktualizuj_nawigacje(0, 0)
        self._wyczysc_formularz()
        self._message(self.info_odczytu, "read.start")
        self._message(self.info_ai, "ai.start")
        self._message(self.opis_zaznaczenia, "doc.selection_hint")
        self._aktualizuj_odczyt()
        self.wczytaj_ustawienia(prefs)

    _VALIDATION_KEYS = {
        "Brak danych — uzupełnij ręcznie": "validation.missing",
        "Brak potwierdzenia w tekście": "validation.evidence",
        "Format poprawny — zweryfikuj z PDF": "validation.valid",
        "Potwierdzone ręcznie z PDF — sprawdź przed zapisem": "validation.manual",
        "Wartość niezgodna z fragmentem źródłowym": "validation.value_mismatch",
        "Okres niezgodny z miesiącem rozliczeniowym w PDF": "validation.billing_month",
        "Okres wyliczony z miesiąca rozliczeniowego w PDF — sprawdź": "validation.billing_derived",
        "Niepoprawny numer konta (NRB/IBAN lub suma kontrolna). Sprawdź go z oryginalnym rachunkiem.": "validation.account",
        "Kategoria spoza listy Świstaka": "validation.category",
        "Wymagana data RRRR-MM-DD": "validation.date",
        "Obsługiwana waluta rachunku: PLN": "validation.currency",
        "Waluta niepotwierdzona jako PLN": "validation.currency_missing",
        "Początek okresu późniejszy niż koniec": "validation.period",
        "Numer faktury identyczny z kontem": "validation.invoice_account",
        "Numer konta identyczny z fakturą": "validation.account_invoice",
        "Za długa nazwa dostawcy": "validation.supplier_length",
        "Za długi numer faktury": "validation.invoice_length",
    }
    _AI_FIELDS = {
        "dostawca": "ai.label.supplier",
        "numer_faktury": "ai.label.invoice",
        "kwota_do_zaplaty": "ai.label.amount",
        "waluta": "ai.label.currency",
        "data_wystawienia": "ai.label.issued",
        "termin_platnosci": "ai.label.due",
        "okres_od": "ai.label.from",
        "okres_do": "ai.label.to",
        "numer_konta_bankowego": "ai.label.account",
        "kategoria_sugerowana": "ai.label.category",
    }

    def _validation_message(self, value: str) -> str:
        key = self._VALIDATION_KEYS.get(value)
        return t(key) if key else value

    def dopasuj_uklad(self, width: int) -> None:
        kierunek = Qt.Orientation.Vertical if width < 830 else Qt.Orientation.Horizontal
        if self.dzielnik.orientation() != kierunek:
            self.dzielnik.setOrientation(kierunek)
            self.dzielnik.setSizes([390, 520])
        pionowy = kierunek == Qt.Orientation.Vertical
        self.obszar_pracy.setDirection(
            QVBoxLayout.Direction.TopToBottom if pionowy
            else QVBoxLayout.Direction.LeftToRight
        )
        self.tytul_etapow.setVisible(not pionowy)
        self.nawigacja.setFlow(QListWidget.Flow.LeftToRight if pionowy else QListWidget.Flow.TopToBottom)
        self.nawigacja.setWrapping(pionowy)
        self._dopasuj_etapy()

    def _dopasuj_etapy(self) -> None:
        metryka = self.nawigacja.fontMetrics()
        szerokosc = max(metryka.horizontalAdvance(t(klucz)) for klucz in self.ETAPY)
        if self.dzielnik.orientation() == Qt.Orientation.Vertical:
            self.pasek_etapow.setMinimumWidth(0)
            self.pasek_etapow.setMaximumWidth(16777215)
            self.nawigacja.setFixedHeight((metryka.height() + 25) * 2)
        else:
            self.pasek_etapow.setFixedWidth(max(170, szerokosc + 57))
            self.nawigacja.setMinimumHeight(0)
            self.nawigacja.setMaximumHeight(16777215)

    def przetlumacz(self) -> None:
        self.otworz_przycisk.setText(t("button.import"))
        self.poprzednia.setText(t("button.previous"))
        self.nastepna.setText(t("button.next"))
        self.btn_dopasuj.setText(t("button.fit"))
        self.btn_szerokosc.setText(t("button.fit_width"))
        self.formularz.przetlumacz()
        self.tytul_etapow.setText(t("workflow.title"))
        for index, key in enumerate(self.ETAPY):
            self.nawigacja.item(index).setText(t(key))
            self.nawigacja.item(index).setToolTip(t(key))
        self._aktualizuj_tekst_propozycji()
        self._aktualizuj_podsumowanie(zachowaj_komunikat=True)

        self.hint_listy.setText(t("list.hint"))
        self.btn_odswiez.setText(t("button.refresh"))
        self.btn_panel_agenta.setText(t("agent.open"))
        self.hint_odczytu.setText(t("read.hint"))
        self.btn_odczytaj.setText(t("button.read_all"))
        self.btn_odczytaj_obszar.setText(t("button.read_selection"))
        self.btn_odczytaj_qr.setText(t("qr.read"))
        self.btn_anuluj.setText(t("button.cancel"))
        self.btn_kopiuj.setText(t("button.copy"))
        self.pole_odczytu.setPlaceholderText(t("read.placeholder"))
        self.btn_analizuj_z_odczytu.setText(t("button.analyze_text"))
        self.zakladki_ai.setTabText(0, t("ai.tab_data"))
        self.zakladki_ai.setTabText(1, t("ai.tab_agent"))
        self.btn_info_ai.setToolTip(t("ai.info_title"))
        self.postep_ai.setAccessibleName(t("ai.progress.accessible"))
        self.btn_wybierz_wzorzec.setText(t("patterns.choose"))
        self.etykieta_notatek_wzorca.setText(t("patterns.notes"))
        self.notatki_wzorca.setPlaceholderText(t("patterns.notes_placeholder"))
        self.info_notatek_agenta.setText(t("ai.notes_scope"))
        self.formularz.btn_proponuj_wzorzec.setText(t("patterns.propose"))
        self._aktualizuj_info_wzorca()
        self.etykieta_modelu.setText(t("ai.model"))
        self.ed_model.setToolTip(t("ai.model_tip"))
        self.btn_szukaj_modeli.setText(t("models.search"))
        self.btn_szukaj_modeli.setToolTip(t("models.search_hint"))
        self.btn_analizuj.setText(t("button.analyze"))
        self.btn_anuluj_ai.setText(t("button.cancel"))
        self.btn_przenies.setText(t("button.apply"))
        self.btn_przenies.setToolTip(t("ai.apply_tip"))
        self.btn_potwierdz_recznie.setText(t("ai.confirm_row"))
        self.btn_potwierdz_recznie.setToolTip(t("ai.confirm_row_tip"))
        self.btn_dodaj_kategorie_ai.setText(t("categories.open"))
        self.tabela_ai.setHorizontalHeaderLabels([
            t("ai.table.field"), t("ai.table.suggestion_edit"),
            t("ai.table.evidence"), t("ai.table.verdict"), t("ai.table.comment"),
        ])
        self._odswiez_komentarze_ai()
        for row, field in enumerate(POLA):
            self.tabela_ai.setItem(row, 0, QTableWidgetItem(t(self._AI_FIELDS[field])))
            if self._analiza is not None and field in self._analiza.oceny:
                verdict = self._analiza.oceny[field]
                value = ("✓ " if verdict.poprawne else "⚠ ") + self._validation_message(verdict.komunikat)
                if self.tabela_ai.item(row, 3) is not None:
                    self.tabela_ai.item(row, 3).setText(value)
        # Refresh dynamically displayed messages from keys, without clearing
        # OCR text, form data, selections or analysis rows.
        for widget, (key, values) in list(self._messages.items()):
            widget.setText(t(key, **values))
        self._aktualizuj_nawigacje(self.podglad.strona, self.podglad.liczba_stron)

    def _message(self, widget: QLabel, key: str, **values) -> None:
        self._messages[widget] = (key, values)
        widget.setText(t(key, **values))

    def otworz_menedzer_wzorcow(self) -> None:
        OknoWzorcow(self.window(), self.magazyn_wzorcow).exec()
        # Menedżer może zmienić/wyłączyć aktywny wzorzec:
        # ponów dopasowanie przed kolejną analizą.
        if self.aktualny_dokument_id is not None:
            self._wykryj_wzorzec(self.pole_odczytu.toPlainText())

    def _status(self, key: str, **values) -> None:
        self.status_zmieniony.emit(key, values)

    def wczytaj_ustawienia(self, prefs: dict) -> None:
        self.ed_model.setText(prefs.get("ollama_model", "gemma3:4b"))
        self._model_ekstrakcji = prefs.get("model_extractor") or None

    def pracuje(self) -> bool:
        return self._zadanie_odczytu is not None or self._zadanie_ai is not None

    def zamknij(self) -> None:
        if self._zadanie_odczytu is not None:
            self._zadanie_odczytu.przerwij.set()
        if self._zadanie_ai is not None:
            self._zadanie_ai.anuluj()
        self.podglad.zamknij_dokument()

    def odswiez_platnosc(self, invoice_id) -> None:
        if self.aktualny_dokument_id is not None and isinstance(invoice_id, int):
            faktura = self.rejestr.rachunek(self.aktualny_dokument_id)
            if faktura is not None and faktura["id"] == invoice_id:
                zapisany = self._zapisany_formularz
                status = faktura["status"]
                oplacono = faktura["data_oplacenia"] or ""
                if zapisany is not None and (
                    status != zapisany.status or oplacono != zapisany.oplacono
                ):
                    self.formularz.wczytaj_platnosc(faktura)
                    self._zapisany_formularz = zapisany._replace(status=status, oplacono=oplacono)
                self.formularz.zapisz_przycisk.setEnabled(faktura["wycofano_utc"] is None)
        self._aktualizuj_podsumowanie()

    def _zmieniony_etap(self, indeks: int) -> None:
        if indeks == self.ETAP_FAKTURA:
            self._aktualizuj_podsumowanie()

    def _aktualizuj_podsumowanie(self, *, zachowaj_komunikat: bool = False) -> None:
        """Wartości po korekcie, bez odczytu/zapisu bazy przy zmianie widoku."""
        self.formularz.odswiez_podsumowanie()
        if not zachowaj_komunikat or self.formularz.info_faktury not in self._messages:
            self._message(
                self.formularz.info_faktury,
                "invoice.review" if self.aktualny_dokument_id is not None
                else "invoice.no_document",
            )

    def _zbuduj_odczyt(self) -> QWidget:
        """Podgląd surowego tekstu, zanim trafi do Ollamy."""
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(10, 12, 10, 12)
        uklad.setSpacing(10)
        instrukcja = QLabel()
        self.hint_odczytu = instrukcja
        instrukcja.setWordWrap(True)
        instrukcja.setObjectName("podpowiedz")
        uklad.addWidget(instrukcja)
        przyciski = Siatka(3)
        self.btn_odczytaj = QPushButton()
        self.btn_odczytaj.clicked.connect(lambda: self._start_odczytu(False))
        przyciski.dodaj(self.btn_odczytaj)
        self.btn_odczytaj_obszar = QPushButton()
        self.btn_odczytaj_obszar.clicked.connect(lambda: self._start_odczytu(True))
        przyciski.dodaj(self.btn_odczytaj_obszar)
        self.btn_odczytaj_qr = QPushButton()
        self.btn_odczytaj_qr.setObjectName("odczytajQR")
        self.btn_odczytaj_qr.clicked.connect(self._otworz_qr)
        przyciski.dodaj(self.btn_odczytaj_qr)
        uklad.addWidget(przyciski)
        self.btn_anuluj = QPushButton()
        self.btn_anuluj.clicked.connect(self._anuluj_odczyt)
        uklad.addWidget(self.btn_anuluj)
        self.info_odczytu = QLabel()
        self.info_odczytu.setWordWrap(True)
        uklad.addWidget(self.info_odczytu)
        self.pole_odczytu = QTextEdit()
        self.pole_odczytu.setReadOnly(True)
        uklad.addWidget(self.pole_odczytu, 1)
        kopiuj = QPushButton()
        self.btn_kopiuj = kopiuj
        kopiuj.clicked.connect(
            lambda: QApplication.clipboard().setText(self.pole_odczytu.toPlainText())
        )
        uklad.addWidget(kopiuj)
        self.btn_analizuj_z_odczytu = QPushButton()
        self.btn_analizuj_z_odczytu.clicked.connect(self._start_analizy)
        uklad.addWidget(self.btn_analizuj_z_odczytu)
        return panel

    def _zbuduj_analize(self) -> QWidget:
        """Dwie wewnętrzne zakładki: wyniki analizy i konfiguracja agenta.

        Podział zmienia wyłącznie układ GUI, nie kolejność walidacji
        ani zasady świadomego przenoszenia danych do formularza.
        """
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(10, 8, 10, 8)
        uklad.setSpacing(4)
        self.zakladki_ai = QTabWidget()
        self.zakladki_ai.setObjectName("zakladkiAnalizyAI")
        uklad.addWidget(self.zakladki_ai, 1)

        # DANE: tabela na całej dostępnej wysokości, przyciski na dole.
        self.karta_ai_dane = QWidget()
        dane_uklad = QVBoxLayout(self.karta_ai_dane)
        dane_uklad.setContentsMargins(6, 8, 6, 6)
        dane_uklad.setSpacing(6)

        self.tabela_ai = QTableWidget(len(POLA), 5)
        self.tabela_ai.setObjectName("tabelaAnalizyAI")
        self.tabela_ai.setHorizontalHeaderLabels([
            "Pole", "Sugestia / korekta", "Dowód z tekstu", "Ocena", "Komentarz",
        ])
        self.tabela_ai.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.tabela_ai.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela_ai.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabela_ai.setWordWrap(True)
        self.tabela_ai.setAlternatingRowColors(True)
        self.tabela_ai.verticalHeader().setVisible(False)
        self.tabela_ai.setColumnWidth(0, 120)
        self.tabela_ai.setColumnWidth(1, 160)
        self.tabela_ai.setColumnWidth(3, 175)
        self.tabela_ai.setColumnWidth(4, 145)
        self.tabela_ai.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        for n, pole in enumerate(POLA):
            self.tabela_ai.setItem(n, 0, self._element_tabeli_ai(ETYKIETY[pole]))
            self.tabela_ai.setItem(n, 4, self._element_tabeli_ai("—"))
        self.tabela_ai.itemChanged.connect(self._edytowano_sugestie_ai)
        self.tabela_ai.itemDoubleClicked.connect(self._podwojny_klik_ai)
        dane_uklad.addWidget(self.tabela_ai, 1)

        status_uklad = QHBoxLayout()
        self.info_ai = QLabel()
        self.info_ai.setObjectName("podpowiedz")
        self.info_ai.setWordWrap(True)
        status_uklad.addWidget(self.info_ai, 1)
        self.btn_info_ai = QPushButton("ⓘ")
        self.btn_info_ai.setObjectName("informacjeAnalizaAI")
        self.btn_info_ai.setFixedWidth(38)
        self.btn_info_ai.clicked.connect(self._pokaz_info_ai)
        status_uklad.addWidget(self.btn_info_ai)
        dane_uklad.addLayout(status_uklad)

        # Pasek pod tabelą, nad przyciskami. Ollama (stream=False) nie
        # podaje procentów; nie symulujemy ich zegarem ani animowanym licznikiem.
        self.postep_ai = QProgressBar()
        self.postep_ai.setObjectName("postepPracyAgenta")
        self.postep_ai.setRange(0, 100)
        self.postep_ai.setValue(0)
        self.postep_ai.setTextVisible(False)
        self.postep_ai.setFixedHeight(14)
        self.postep_ai.setStyleSheet(
            "QProgressBar { border: 1px solid #45484b; border-radius: 5px;"
            " background: #2b3035; }"
            "QProgressBar::chunk { background: #3fa66b; border-radius: 4px; }"
        )
        self.postep_ai.hide()
        dane_uklad.addWidget(self.postep_ai)

        analiza_akcje = Siatka(2)
        self.btn_analizuj = QPushButton()
        self.btn_analizuj.clicked.connect(self._start_analizy)
        analiza_akcje.dodaj(self.btn_analizuj)
        self.btn_anuluj_ai = QPushButton()
        self.btn_anuluj_ai.clicked.connect(self._anuluj_analize)
        analiza_akcje.dodaj(self.btn_anuluj_ai)
        dane_uklad.addWidget(analiza_akcje)

        korekty = Siatka(2)
        self.btn_potwierdz_recznie = QPushButton()
        self.btn_potwierdz_recznie.clicked.connect(self._potwierdz_pole_ai)
        korekty.dodaj(self.btn_potwierdz_recznie)
        self.btn_dodaj_kategorie_ai = QPushButton()
        self.btn_dodaj_kategorie_ai.clicked.connect(self._dodaj_kategorie)
        korekty.dodaj(self.btn_dodaj_kategorie_ai)
        dane_uklad.addWidget(korekty)

        self.btn_przenies = QPushButton()
        self.btn_przenies.setObjectName("przeniesSugestieAI")
        self.btn_przenies.clicked.connect(self._przenies_sugestie)
        dane_uklad.addWidget(self.btn_przenies)

        # AGENT: wszystkie ustawienia modelu, wzorce i wskazówki razem.
        self.karta_ai_agent = QWidget()
        agent_uklad = QVBoxLayout(self.karta_ai_agent)
        agent_uklad.setContentsMargins(10, 14, 10, 12)
        agent_uklad.setSpacing(12)

        self.etykieta_modelu = QLabel()
        agent_uklad.addWidget(self.etykieta_modelu)
        self.ed_model = QLineEdit()
        self.ed_model.setObjectName("modelOllamaAgent")
        model_wiersz = QHBoxLayout()
        model_wiersz.addWidget(self.ed_model, 1)
        self.btn_szukaj_modeli = QPushButton()
        self.btn_szukaj_modeli.setObjectName("szukajModeliLokalnych")
        self.btn_szukaj_modeli.clicked.connect(self.wybor_modelu)
        model_wiersz.addWidget(self.btn_szukaj_modeli)
        agent_uklad.addLayout(model_wiersz)

        wzorce_uklad = QHBoxLayout()
        self.info_wzorca = QLabel()
        self.info_wzorca.setObjectName("podpowiedz")
        self.info_wzorca.setWordWrap(True)
        wzorce_uklad.addWidget(self.info_wzorca, 1)
        self.btn_wybierz_wzorzec = QPushButton()
        self.btn_wybierz_wzorzec.clicked.connect(self._wybierz_wzorzec_recznie)
        wzorce_uklad.addWidget(self.btn_wybierz_wzorzec)
        agent_uklad.addLayout(wzorce_uklad)

        self.etykieta_notatek_wzorca = QLabel()
        self.etykieta_notatek_wzorca.setWordWrap(True)
        agent_uklad.addWidget(self.etykieta_notatek_wzorca)
        self.notatki_wzorca = QPlainTextEdit()
        self.notatki_wzorca.setObjectName("wskazowkiWzorca")
        self.notatki_wzorca.setMinimumHeight(140)
        agent_uklad.addWidget(self.notatki_wzorca, 1)
        self.info_notatek_agenta = QLabel()
        self.info_notatek_agenta.setObjectName("podpowiedz")
        self.info_notatek_agenta.setWordWrap(True)
        agent_uklad.addWidget(self.info_notatek_agenta)

        self.btn_panel_agenta = QPushButton()
        self.btn_panel_agenta.setObjectName("panelAgentaWAnalizie")
        self.btn_panel_agenta.clicked.connect(self.pokaz_agenta)
        agent_uklad.addWidget(self.btn_panel_agenta)

        self.zakladki_ai.addTab(self.karta_ai_dane, "")
        self.zakladki_ai.addTab(self.karta_ai_agent, "")
        return panel

    def _pokaz_info_ai(self) -> None:
        """Pełna instrukcja dostępna pod INFO, bez zabierania miejsca tabeli."""
        QMessageBox.information(
            self.window(), t("ai.info_title"),
            "\n\n".join((t("ai.hint"), t("ai.edit_hint"), t("ai.next_step"))),
        )

    def _podwojny_klik_ai(self, element: QTableWidgetItem) -> None:
        """Kolumna komentarza jest edytowana w wygodnym oknie tekstowym."""
        if element.column() == 4:
            self.tabela_ai.setCurrentCell(element.row(), 4)
            self._dodaj_komentarz_wzorca()

    def _odswiez_komentarze_ai(self) -> None:
        """Komentarze są przypisane do pola, nie do numeru wiersza ani OCR."""
        self._aktualizuje_tabele_ai = True
        try:
            for row, field in enumerate(POLA):
                note = self._komentarze_wzorca.get(field, "")
                element = self._element_tabeli_ai(note or "—")
                element.setToolTip(note or t("patterns.no_field_note"))
                self.tabela_ai.setItem(row, 4, element)
        finally:
            self._aktualizuje_tabele_ai = False

    @staticmethod
    def _element_tabeli_ai(tekst: str, edytowalny: bool = False) -> QTableWidgetItem:
        element = QTableWidgetItem(tekst)
        if not edytowalny:
            element.setFlags(element.flags() & ~Qt.ItemFlag.ItemIsEditable)
        element.setToolTip(tekst)
        return element

    def _start_postep_ai(self) -> None:
        """Nieznany czas odpowiedzi Ollamy: animacja bez fikcyjnego procentu."""
        self.postep_ai.setRange(0, 0)
        self.postep_ai.show()

    def _etap_postepu_ai(self, dokument_id: int, etap: str) -> None:
        """Etapy pochodzą z pracującego wątku; GUI aktualizuje wyłącznie Qt."""
        if (self._zadanie_ai is None or
                dokument_id != self.aktualny_dokument_id or
                self._zadanie_ai.przerwij.is_set()):
            return
        if etap in ("prepare", "ollama", "validate"):
            self._message(self.info_ai, "ai.progress." + etap,
                          model=self._zadanie_ai.model)

    def _koniec_postepu_ai(self, sukces: bool) -> None:
        self.postep_ai.setRange(0, 100)
        self.postep_ai.setValue(100 if sukces else 0)
        self.postep_ai.setVisible(sukces)

    def _wyczysc_analize(self) -> None:
        self._koniec_postepu_ai(False)
        self._analiza = None
        self._analiza_dokument_id = None
        self._pola_potwierdzone_recznie.clear()
        self._aktualizuje_tabele_ai = True
        try:
            for r in range(len(POLA)):
                for c in range(1, 4):
                    self.tabela_ai.setItem(r, c, self._element_tabeli_ai(""))
        finally:
            self._aktualizuje_tabele_ai = False
        self._message(self.info_ai, "ai.none")

    def _przelicz_sugestie_ai(self) -> None:
        """Zastosuj te same walidacje co po odpowiedzi Ollamy, ale bez żądania AI."""
        if self._analiza is None or self._analiza_dokument_id != self.aktualny_dokument_id:
            return
        dane = {}
        for r, pole in enumerate(POLA):
            element = self.tabela_ai.item(r, 1)
            wartosc = element.text().strip() if element is not None else ""
            dane[pole] = {
                "wartosc": wartosc if wartosc and wartosc != "—" else None,
                "dowod": self._analiza.oceny[pole].dowod,
            }
        oceny = ocena_json(
            dane, self.pole_odczytu.toPlainText(),
            [wiersz["nazwa"] for wiersz in self.rejestr.kategorie()],
            potwierdzone_recznie=self._pola_potwierdzone_recznie,
        )
        self._analiza = AnalizaModelu(self._analiza.model, oceny)
        self._aktualizuje_tabele_ai = True
        try:
            for r, pole in enumerate(POLA):
                ocena = oceny[pole]
                element = self.tabela_ai.item(r, 1)
                if element is not None and ocena.poprawne and ocena.wartosc is not None:
                    element.setText(ocena.wartosc)
                    element.setToolTip(ocena.wartosc)
                opis = ("✓ " if ocena.poprawne else "⚠ ") + self._validation_message(ocena.komunikat)
                self.tabela_ai.setItem(r, 3, self._element_tabeli_ai(opis))
            self.tabela_ai.resizeRowsToContents()
        finally:
            self._aktualizuje_tabele_ai = False
        self._aktualizuj_ai()

    def _edytowano_sugestie_ai(self, element: QTableWidgetItem) -> None:
        if self._aktualizuje_tabele_ai or element.column() != 1 or self._analiza is None:
            return
        pole = POLA[element.row()]
        # Zmiana wartości unieważnia wcześniejsze ręczne potwierdzenie.
        self._pola_potwierdzone_recznie.discard(pole)
        self._przelicz_sugestie_ai()

    def _potwierdz_pole_ai(self) -> None:
        """Ręcznie potwierdź wskazaną wartość po porównaniu z PDF.

        Dowód OCR może być uszkodzony, ale poprawność daty, kwoty,
        numeru konta, waluty i kategorii nadal jest weryfikowana.
        """
        if self._analiza is None or self._analiza_dokument_id != self.aktualny_dokument_id:
            return
        r = self.tabela_ai.currentRow()
        if not 0 <= r < len(POLA):
            return
        pole = POLA[r]
        odp = QMessageBox.question(
            self.window(), t("ai.manual_title"),
            t("ai.manual_confirm", field=t(self._AI_FIELDS[pole])),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if odp != QMessageBox.StandardButton.Yes:
            return
        self._pola_potwierdzone_recznie.add(pole)
        self._przelicz_sugestie_ai()
        if not self._analiza.oceny[pole].poprawne:
            self._pola_potwierdzone_recznie.discard(pole)
            self._przelicz_sugestie_ai()
            QMessageBox.warning(
                self.window(), t("ai.manual_title"),
                self._validation_message(self._analiza.oceny[pole].komunikat)
            )

    def _aktualizuj_ai(self) -> None:
        zajete = self._zadanie_ai is not None or self._zadanie_odczytu is not None
        dokument = self.aktualny_dokument_id is not None
        tekst = bool(self.pole_odczytu.toPlainText().strip())
        mozna = dokument and tekst and not zajete
        self.btn_analizuj.setEnabled(mozna)
        self.btn_analizuj_z_odczytu.setEnabled(mozna)
        self.btn_anuluj_ai.setEnabled(self._zadanie_ai is not None)
        analiza_dokumentu = (
            self._analiza is not None
            and self._analiza_dokument_id == self.aktualny_dokument_id
        )
        self.btn_przenies.setEnabled(
            not zajete and analiza_dokumentu
            and any(x.poprawne for x in self._analiza.oceny.values())
        )
        self.btn_potwierdz_recznie.setEnabled(not zajete and analiza_dokumentu)
        self.btn_dodaj_kategorie_ai.setEnabled(not zajete and analiza_dokumentu)

    def _start_analizy(self) -> None:
        if self._zadanie_ai is not None or self._zadanie_odczytu is not None:
            return
        if self.aktualny_dokument_id is None:
            QMessageBox.information(self.window(), t("tab.ai"), t("msg.no_pdf"))
            return
        tekst = self.pole_odczytu.toPlainText()
        if not tekst.strip():
            QMessageBox.information(
                self.window(), t("tab.ai"), t("msg.read_before_ai")
            )
            return
        model = self.ed_model.text().strip()
        if not model:
            QMessageBox.warning(self.window(), t("tab.ai"), t("msg.model_required"))
            return
        # Analiza żądana przez użytkownika ma pierwszeństwo nad monitorem
        # uruchomionym automatycznie w tle.
        self.analiza_zadana.emit()
        if (self._wzorzec_dokument_id != self.aktualny_dokument_id
                or self._tekst_dopasowania != tekst):
            self._wykryj_wzorzec(tekst)
        if (self._dopasowanie_wzorca is not None
                and self._dopasowanie_wzorca.poziom == "suggest"
                and self._aktywny_wzorzec is None and not self._wzorzec_pominiety):
            decyzja = QMessageBox.question(
                self.window(), t("patterns.match_title"),
                t("patterns.match_confirm",
                  name=self._dopasowanie_wzorca.wzorzec["name"],
                  score=self._dopasowanie_wzorca.punkty),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if decyzja == QMessageBox.StandardButton.Yes:
                self._aktywny_wzorzec = self._dopasowanie_wzorca.wzorzec
            else:
                self._wzorzec_pominiety = True
            self._aktualizuj_info_wzorca()
        kategorie = [wiersz["nazwa"] for wiersz in self.rejestr.kategorie()]
        zadanie = ZadanieAnalizy(
            self.aktualny_dokument_id, tekst, kategorie, model,
            wzorzec=self._aktywny_wzorzec,
            model_ekstrakcji=self._model_ekstrakcji,
        )
        self._wyczysc_analize()
        self._zadanie_ai = zadanie
        self.karty.setCurrentIndex(self.ETAP_ANALIZA)
        self.zakladki_ai.setCurrentIndex(0)
        self._message(self.info_ai, "ai.progress.prepare", model=model)
        self._start_postep_ai()
        zadanie.sygnaly.etap.connect(self._etap_postepu_ai)
        zadanie.sygnaly.gotowe.connect(self._analiza_gotowa)
        zadanie.sygnaly.blad.connect(self._analiza_blad)
        zadanie.sygnaly.anulowano.connect(self._analiza_anulowana)
        self._aktualizuj_odczyt()
        QThreadPool.globalInstance().start(zadanie)

    def _analiza_gotowa(self, dokument_id: int, wynik: AnalizaModelu) -> None:
        self._zadanie_ai = None
        if dokument_id != self.aktualny_dokument_id:
            self._koniec_postepu_ai(False)
            self._aktualizuj_odczyt()
            return
        self._koniec_postepu_ai(True)
        self._analiza = wynik
        self._analiza_dokument_id = dokument_id
        self._pola_potwierdzone_recznie.clear()
        ile = 0
        self._aktualizuje_tabele_ai = True
        try:
            for r, pole in enumerate(POLA):
                ocena = wynik.oceny[pole]
                if ocena.poprawne:
                    ile += 1
                tresci = (
                    ocena.wartosc if ocena.wartosc is not None else "—",
                    ocena.dowod or "—",
                    ("✓ " if ocena.poprawne else "⚠ ") + self._validation_message(ocena.komunikat),
                )
                for c, napis in enumerate(tresci, 1):
                    self.tabela_ai.setItem(
                        r, c, self._element_tabeli_ai(napis, edytowalny=(c == 1))
                    )
            self.tabela_ai.resizeRowsToContents()
        finally:
            self._aktualizuje_tabele_ai = False
        self._message(self.info_ai, "ai.done", model=wynik.model, count=ile, total=len(POLA))
        self.zakladki_ai.setCurrentIndex(0)
        self._aktualizuj_odczyt()

    def _analiza_blad(self, dokument_id: int, komunikat: str) -> None:
        self._koniec_postepu_ai(False)
        self._zadanie_ai = None
        za_dlugi = komunikat == ExtractionContextExceeded.code
        klucz = "ai.context_exceeded" if za_dlugi else "ai.failed"
        self._message(self.info_ai, klucz)
        self._aktualizuj_odczyt()
        if dokument_id == self.aktualny_dokument_id:
            QMessageBox.warning(self.window(), t("msg.ai_error"), t(klucz) if za_dlugi else komunikat)
            if za_dlugi:
                self.karty.setCurrentIndex(self.ETAP_ODCZYT)
                self._message(self.info_odczytu, klucz)

    def _analiza_anulowana(self, dokument_id: int) -> None:
        self._koniec_postepu_ai(False)
        self._zadanie_ai = None
        self._message(self.info_ai, "ai.cancelled")
        self._aktualizuj_odczyt()

    def _anuluj_analize(self) -> None:
        if self._zadanie_ai is not None:
            self._zadanie_ai.anuluj()
            self._message(self.info_ai, "ai.cancelling")

    def _przenies_sugestie(self) -> None:
        if (self._analiza is None or
                self._analiza_dokument_id != self.aktualny_dokument_id):
            return
        oceny = self._analiza.oceny
        pola_do_formularza = {
            "dostawca": self.formularz.ed_dostawca,
            "numer_faktury": self.formularz.ed_numer,
            "kwota_do_zaplaty": self.formularz.ed_kwota,
            "data_wystawienia": self.formularz.ed_wystawiono,
            "termin_platnosci": self.formularz.ed_termin,
            "okres_od": self.formularz.ed_od,
            "okres_do": self.formularz.ed_do,
            "numer_konta_bankowego": self.formularz.ed_konto,
        }
        do_zastosowania = [
            p for p in pola_do_formularza if oceny[p].poprawne
        ]
        if oceny["kategoria_sugerowana"].poprawne:
            do_zastosowania.append("kategoria_sugerowana")
        if not do_zastosowania:
            return
        odp = QMessageBox.question(
            self.window(), t("ai.confirm_title"),
            t("ai.confirm_body", count=len(do_zastosowania)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if odp != QMessageBox.StandardButton.Yes:
            return
        for pole, kontrolka in pola_do_formularza.items():
            if oceny[pole].poprawne:
                kontrolka.setText(oceny[pole].wartosc)
        if oceny["kategoria_sugerowana"].poprawne:
            nazwa = oceny["kategoria_sugerowana"].wartosc
            identyfikator = next(
                (int(row["id"]) for row in self.rejestr.kategorie()
                 if row["nazwa"] == nazwa), None
            )
            id_kategorii = self.formularz.wybor_kategoria.findData(identyfikator)
            if id_kategorii >= 0:
                self.formularz.wybor_kategoria.setCurrentIndex(id_kategorii)
        self._analiza = None  # nie pozwól ponownie użyć nieaktualnej propozycji
        self._pola_potwierdzone_recznie.clear()
        self._aktualizuj_odczyt()
        self.karty.setCurrentIndex(self.ETAP_EDYCJA)
        self._status("ai.saved_hint")

    def _aktualizuj_odczyt(self) -> None:
        pracuje = self._zadanie_odczytu is not None or self._zadanie_ai is not None
        jest_dokument = self.aktualny_dokument_id is not None
        self.btn_odczytaj.setEnabled(jest_dokument and not pracuje)
        self.btn_odczytaj_obszar.setEnabled(
            jest_dokument and self._wybrany_obszar is not None and not pracuje
        )
        self.btn_odczytaj_qr.setEnabled(jest_dokument and not pracuje)
        self.btn_anuluj.setEnabled(self._zadanie_odczytu is not None)
        self.otworz_przycisk.setEnabled(not pracuje)
        self.lista_dokumentow.setEnabled(not pracuje)
        self._aktualizuj_ai()

    def _start_odczytu(self, tylko_obszar: bool) -> None:
        if (self.aktualny_dokument_id is None or self._zadanie_odczytu is not None
                or self._zadanie_ai is not None):
            return
        obszar = self._wybrany_obszar if tylko_obszar else None
        if tylko_obszar and obszar is None:
            return
        try:
            sciezka = self.rejestr.sciezka_pdf(self.aktualny_dokument_id)
        except (OSError, ValueError) as blad:
            QMessageBox.warning(self.window(), t("msg.pdf"), str(blad))
            return
        zadanie = ZadanieOdczytu(sciezka, obszar)
        self._wyczysc_analize()
        self._zadanie_odczytu = zadanie
        self._aktualizuj_odczyt()
        self.pole_odczytu.clear()
        self._message(self.info_odczytu, "read.running")
        self.karty.setCurrentIndex(self.ETAP_ODCZYT)
        zadanie.sygnaly.gotowe.connect(self._odczyt_gotowy)
        zadanie.sygnaly.blad.connect(self._odczyt_blad)
        zadanie.sygnaly.anulowano.connect(self._odczyt_anulowano)
        QThreadPool.globalInstance().start(zadanie)

    def _odczyt_gotowy(self, wynik: WynikOdczytu) -> None:
        self._zadanie_odczytu = None
        self._aktualizuj_odczyt()
        self.pole_odczytu.setPlainText(wynik.tekst_dla_llm)
        self._wykryj_wzorzec(wynik.tekst_dla_llm)
        self._aktualizuj_odczyt()
        if wynik.czy_pusty:
            self._message(self.info_odczytu, "read.missing")
        else:
            statystyka = ", ".join(
                t("read.page_method", page=p.strona + 1, method=t("read.method_" + p.metoda))
                for p in wynik.strony
            )
            self._message(self.info_odczytu, "read.done", count=len(wynik.strony), details=statystyka)
        self._status("msg.read_status")

    def _odczyt_blad(self, komunikat: str) -> None:
        self._zadanie_odczytu = None
        self._aktualizuj_odczyt()
        self._message(self.info_odczytu, "read.error")
        QMessageBox.warning(self.window(), t("msg.pdf"), komunikat)

    def _odczyt_anulowano(self) -> None:
        self._zadanie_odczytu = None
        self._aktualizuj_odczyt()
        self._message(self.info_odczytu, "read.cancelled")

    def _otworz_qr(self) -> None:
        """Odczytaj QR lokalnie, bez zapisu i bez wywołania bankowości."""
        if (self.aktualny_dokument_id is None or self._zadanie_odczytu is not None
                or self._zadanie_ai is not None):
            return
        try:
            pdf = self.rejestr.sciezka_pdf(self.aktualny_dokument_id)
            dialog = DialogQR(self.window(), pdf)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            platnosc = dialog.wybrana_platnosc
            if platnosc is None:
                return
            # Zgoda w oknie QR dotyczy tylko dwóch pól. Żadnych
            # automatycznych zapisów do SQLite ani operacji bankowych.
            self.formularz.ed_kwota.setText(grosze_na_kwote(platnosc.kwota_grosze))
            self.formularz.ed_konto.setText(platnosc.numer_konta)
            self.karty.setCurrentIndex(self.ETAP_EDYCJA)
            self._status("qr.applied")
        except (OSError, ValueError, sqlite3.Error) as blad:
            QMessageBox.warning(self.window(), t("qr.title"), str(blad))

    def _anuluj_odczyt(self) -> None:
        if self._zadanie_odczytu is not None:
            self._zadanie_odczytu.przerwij.set()
            self._message(self.info_odczytu, "msg.read_cancelling")

    def _aktualizuj_info_wzorca(self) -> None:
        if not hasattr(self, "info_wzorca"):
            return
        if self._aktywny_wzorzec is not None:
            self.info_wzorca.setText(t(
                "patterns.active", name=self._aktywny_wzorzec["name"]
            ))
        elif self._dopasowanie_wzorca is not None:
            match = self._dopasowanie_wzorca
            key = "patterns.skipped" if self._wzorzec_pominiety else "patterns.suggest"
            self.info_wzorca.setText(t(
                key, name=match.wzorzec["name"], score=match.punkty
            ))
        else:
            self.info_wzorca.setText(t("patterns.none"))

    def _wykryj_wzorzec(self, tekst: str) -> None:
        """Rozpoznanie tylko po wstępnym OCR; żadnego zapisu i żadnego LLM."""
        self._wzorzec_dokument_id = self.aktualny_dokument_id
        self._tekst_dopasowania = tekst
        self._dopasowanie_wzorca = None
        self._aktywny_wzorzec = None
        self._wzorzec_pominiety = False
        if tekst.strip() and self.aktualny_dokument_id is not None:
            try:
                self._dopasowanie_wzorca = dopasuj(
                    tekst, self.magazyn_wzorcow.lista(tylko_aktywne=True)
                )
                if (self._dopasowanie_wzorca is not None
                        and self._dopasowanie_wzorca.poziom == "automatic"):
                    self._aktywny_wzorzec = self._dopasowanie_wzorca.wzorzec
            except (OSError, ValueError):
                self.info_wzorca.setText(t("patterns.load_error"))
                self._status("patterns.load_error")
                return
        self._aktualizuj_info_wzorca()

    def _wybierz_wzorzec_recznie(self) -> None:
        """Użytkownik może pominąć dopasowanie lub wskazać inne zatwierdzone reguły."""
        try:
            templates = self.magazyn_wzorcow.lista(tylko_aktywne=True)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.window(), t("patterns.title"), str(error))
            return
        choices = [t("patterns.no_template")] + [
            f"{item['name']} ({item['template_id'][-8:]}, r{item['revision']})"
            for item in templates
        ]
        choice, accepted = QInputDialog.getItem(
            self.window(), t("patterns.choose"), t("patterns.select"), choices, 0, False
        )
        if not accepted:
            return
        index = choices.index(choice)
        self._aktywny_wzorzec = templates[index - 1] if index else None
        self._wzorzec_pominiety = (index == 0)
        self._aktualizuj_info_wzorca()

    def _dodaj_komentarz_wzorca(self) -> None:
        # Komentarze można przygotować jeszcze przed analizą; zapis wzorca
        # następuje dopiero po świadomej decyzji użytkownika.
        if self.aktualny_dokument_id is None:
            return
        row = self.tabela_ai.currentRow()
        if not 0 <= row < len(POLA):
            QMessageBox.information(self.window(), t("patterns.title"), t("patterns.select_field"))
            return
        pole = POLA[row]
        text, accepted = QInputDialog.getMultiLineText(
            self.window(), t("patterns.field_note"), t("patterns.field_note_help"),
            self._komentarze_wzorca.get(pole, ""),
        )
        if accepted:
            if len(text.strip()) > 450:
                QMessageBox.warning(self.window(), t("patterns.title"), t("patterns.note_too_long"))
                return
            if text.strip():
                self._komentarze_wzorca[pole] = text.strip()
            else:
                self._komentarze_wzorca.pop(pole, None)
            self._odswiez_komentarze_ai()

    def _aktualizuj_tekst_propozycji(self) -> None:
        if not hasattr(self, "formularz"):
            return
        existing = self._aktywny_wzorzec is not None
        self.formularz.btn_proponuj_wzorzec.setText(t(
            "patterns.propose_update" if existing else "patterns.propose"
        ))
        self.formularz.info_propozycji_wzorca.setText(t(
            "patterns.offer_update" if existing else "patterns.offer_new"
        ))

    def _zaproponuj_zapis_wzorca(self) -> None:
        """Wyłącznie po zapisie faktury, z osobnym przeglądem JSON i zgodą."""
        if self.aktualny_dokument_id is None or self.rejestr.rachunek(
            self.aktualny_dokument_id
        ) is None:
            return
        tekst = self.pole_odczytu.toPlainText()
        if not tekst.strip():
            QMessageBox.information(
                self.window(), t("patterns.title"), t("patterns.read_first")
            )
            return
        kategoria = (
            self.formularz.wybor_kategoria.currentText()
            if self.formularz.wybor_kategoria.currentData() is not None else None
        )
        try:
            candidate = zaproponuj_wzorzec(
                tekst, self.formularz.ed_dostawca.text(), kategoria,
                self._komentarze_wzorca, self.notatki_wzorca.toPlainText(),
            )
            original = self._aktywny_wzorzec
            if original is not None:
                proposal = zaproponuj_aktualizacje(original, candidate)
            else:
                proposal = candidate
            # Dialog nie zapisuje niczego; anulowanie pozostawia pliki bez zmian.
            approved = zaakceptuj_wzorzec(
                self.window(), proposal, aktualizacja=original is not None
            )
            if approved is None:
                return
            if original is not None:
                saved = self.magazyn_wzorcow.aktualizuj(
                    original["template_id"], approved,
                    expected_revision=original["revision"],
                )
            else:
                saved = self.magazyn_wzorcow.utworz(approved)
            self._aktywny_wzorzec = saved
            self._wzorzec_pominiety = False
            self._aktualizuj_info_wzorca()
            self._aktualizuj_tekst_propozycji()
            self._status("patterns.saved", name=saved["name"])
        except (ValueError, OSError, TypeError) as error:
            QMessageBox.warning(self.window(), t("patterns.title"), str(error))

    def _zbuduj_liste(self) -> QWidget:
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(8, 10, 8, 10)
        opis = QLabel()
        self.hint_listy = opis
        opis.setWordWrap(True)
        uklad.addWidget(opis)
        self.lista_dokumentow = QListWidget()
        self.lista_dokumentow.itemClicked.connect(self._wybierz_z_listy)
        uklad.addWidget(self.lista_dokumentow)
        przycisk = QPushButton()
        self.btn_odswiez = przycisk
        przycisk.clicked.connect(self.odswiez_dokumenty)
        uklad.addWidget(przycisk)
        return panel

    def _dodaj_kategorie(self) -> None:
        """Wspólny dialog dla DANE i Edycji: najpierw wybór istniejącej."""
        dialog = DialogKategorie(self.rejestr, self.magazyn_wzorcow, self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.wybrana_id
        if selected is None:
            return
        row = next(
            (r for r in self.rejestr.kategorie() if int(r["id"]) == selected),
            None,
        )
        if row is None:
            QMessageBox.warning(self.window(), t("categories.title"),
                                t("categories.no_longer_available"))
            return
        self.formularz.odswiez_kategorie(selected)
        self.kategorie_zmienione.emit()
        # W ANALIZA AI świadomy wybór istniejącej lub nowej kategorii
        # jest korektą sugestii, ale nadal podlega walidacji formatu.
        if (self.karty.currentIndex() == self.ETAP_ANALIZA
                and self._analiza is not None
                and self._analiza_dokument_id == self.aktualny_dokument_id):
            pole = "kategoria_sugerowana"
            nr = POLA.index(pole)
            element = self.tabela_ai.item(nr, 1)
            if element is not None:
                self._aktualizuje_tabele_ai = True
                try:
                    element.setText(row["nazwa"])
                finally:
                    self._aktualizuje_tabele_ai = False
                self._pola_potwierdzone_recznie.add(pole)
                self._przelicz_sugestie_ai()

    def odswiez_liste(self) -> None:
        selected = self.lista_dokumentow.currentItem()
        selected_id = (selected.data(Qt.ItemDataRole.UserRole)
                       if selected is not None else self.aktualny_dokument_id)
        self.lista_dokumentow.clear()
        keep_row = -1
        for wiersz in self.rejestr.dokumenty():
            opis = f"{wiersz['nazwa_zrodlowa']}"
            if wiersz["kwota_grosze"] is not None:
                opis = (f"✓ {wiersz['dostawca']} — "
                        f"{grosze_na_kwote(wiersz['kwota_grosze'])} zł\n"
                        f"   {wiersz['nazwa_zrodlowa']}")
            else:
                opis = t("list.missing") + "\n   " + opis
            element = QListWidgetItem(opis)
            element.setData(Qt.ItemDataRole.UserRole, int(wiersz["id"]))
            self.lista_dokumentow.addItem(element)
            if int(wiersz["id"]) == selected_id:
                keep_row = self.lista_dokumentow.count() - 1
        if keep_row >= 0:
            self.lista_dokumentow.setCurrentRow(keep_row)

    def _wyczysc_formularz(self) -> None:
        self._message(self.formularz.nazwa_dokumentu, "doc.import_first")
        self.formularz.wyczysc()

    def _wyswietl_dokument(self, dokument_id: int) -> None:
        self._wybrany_obszar = None
        self._wyczysc_analize()
        self._komentarze_wzorca.clear()
        self._odswiez_komentarze_ai()
        self.notatki_wzorca.clear()
        self._dopasowanie_wzorca = None
        self._aktywny_wzorzec = None
        self._wzorzec_pominiety = False
        self._wzorzec_dokument_id = None
        self._tekst_dopasowania = ""
        self._aktualizuj_info_wzorca()
        self.formularz.btn_proponuj_wzorzec.hide()
        self.formularz.info_propozycji_wzorca.hide()
        self.pole_odczytu.clear()
        self._message(self.info_odczytu, "doc.opened")
        sciezka = self.rejestr.sciezka_pdf(dokument_id)
        # Przy błędzie (np. uszkodzony plik archiwalny) nie pozwalaj zapisywać
        # pól pod niewłaściwym dokumentem.
        self.aktualny_dokument_id = None
        self.formularz.zapisz_przycisk.setEnabled(False)
        self.podglad.otworz(sciezka)
        dokument = self.rejestr.dokument(dokument_id)
        self.aktualny_dokument_id = dokument_id
        zapis = self.rejestr.rachunek(dokument_id)
        self._wyczysc_formularz()
        self._message(self.formularz.nazwa_dokumentu, "doc.original", name=dokument["nazwa_zrodlowa"])
        if zapis is not None:
            self.formularz.wczytaj(zapis)
        self.formularz.zapisz_przycisk.setEnabled(zapis is None or zapis["wycofano_utc"] is None)
        self._zapisany_formularz = self.formularz.stan()
        self._aktualizuj_odczyt()
        self.karty.setCurrentIndex(
            self.ETAP_FAKTURA if zapis is not None else self.ETAP_ODCZYT
        )
        self._status("msg.opened", name=dokument["nazwa_zrodlowa"])

    def otworz_fakture(self, dokument_id: int) -> None:
        if dokument_id == self.aktualny_dokument_id:
            self.pokaz_kreator.emit()
            self.karty.setCurrentIndex(self.ETAP_FAKTURA)
            return
        if not self._zgoda_na_zmiane_dokumentu():
            return
        try:
            self._wyswietl_dokument(dokument_id)
            self.pokaz_kreator.emit()
        except (ValueError, OSError, sqlite3.Error) as blad:
            QMessageBox.warning(self.window(), t("msg.document_open_error"), str(blad))

    def _wybierz_z_listy(self, element: QListWidgetItem) -> None:
        dokument_id = int(element.data(Qt.ItemDataRole.UserRole))
        if dokument_id != self.aktualny_dokument_id:
            self.otworz_fakture(dokument_id)

    def _zgoda_na_zmiane_dokumentu(self) -> bool:
        if self._zadanie_odczytu is not None or self._zadanie_ai is not None:
            QMessageBox.information(self.window(), t("nav.new_invoice"), t("invoice.document_busy"))
            return False
        if self.aktualny_dokument_id is None or self.formularz.stan() == self._zapisany_formularz:
            return True
        return QMessageBox.question(
            self.window(), t("nav.new_invoice"), t("invoice.leave_draft"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def podglad_dopasuj(self) -> None:
        self.podglad.dopasuj()

    def wybierz_plik(self) -> None:
        sciezka, _ = QFileDialog.getOpenFileName(
            self.window(), t("msg.import_dialog"), "", t("msg.pdf_filter")
        )
        if sciezka:
            self.otworz_pdf(sciezka)

    def otworz_pdf(self, sciezka: str | Path) -> None:
        if not self._zgoda_na_zmiane_dokumentu():
            return
        try:
            # Zweryfikuj PDF w Qt przed dodaniem go do archiwum i bazy.
            self.aktualny_dokument_id = None
            self.formularz.zapisz_przycisk.setEnabled(False)
            self.podglad.otworz(sciezka)
            dokument_id, czy_nowy = self.rejestr.importuj_pdf(sciezka)
            self._wyswietl_dokument(dokument_id)
            self.pokaz_kreator.emit()
            self.odswiez_dokumenty.emit()
            if not czy_nowy:
                self._status("msg.duplicate")
        except (OSError, ValueError, sqlite3.Error) as blad:
            QMessageBox.warning(self.window(), t("msg.document_import_error"), str(blad))

    def _zapisz_rachunek(self) -> None:
        if self.aktualny_dokument_id is None:
            return
        try:
            formularz = self.formularz.stan()
            zapisany = self._zapisany_formularz
            data_oplacenia = formularz.oplacono.strip() if formularz.status == "oplacony" else ""
            if formularz.status == "oplacony" and not data_oplacenia:
                raise BrakDatyOplacenia("Wpisz datę opłacenia faktury")
            wystawiono = formularz.wystawiono.strip() or None
            platnosc_bez_zmian = (
                zapisany is not None
                and zapisany.status == formularz.status
                and zapisany.oplacono == data_oplacenia
            )
            daty_zmienione = (
                zapisany is None
                or not platnosc_bez_zmian
                or zapisany.wystawiono.strip() != (wystawiono or "")
            )
            if (data_oplacenia and sprawdz_date_platnosci(data_oplacenia, wystawiono)
                    and daty_zmienione):
                odpowiedz = QMessageBox.question(
                    self.window(), t("payment.confirm_title"),
                    t("payment.before_issue", paid=data_oplacenia, issued=wystawiono),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if odpowiedz != QMessageBox.StandardButton.Yes:
                    self.karty.setCurrentIndex(self.ETAP_EDYCJA)
                    self.formularz.ed_oplacono.setFocus()
                    return
            # Nie nadpisuj daty, której użytkownik nie zmienił w otwartym formularzu.
            if platnosc_bez_zmian:
                data_oplacenia = ""
            dane = DaneRachunku(
                dokument_id=self.aktualny_dokument_id,
                dostawca=formularz.dostawca,
                numer=formularz.numer,
                numer_konta=formularz.numer_konta,
                kwota=formularz.kwota,
                kategoria_id=formularz.kategoria_id,
                data_wystawienia=formularz.wystawiono,
                termin_platnosci=formularz.termin,
                okres_od=formularz.okres_od,
                okres_do=formularz.okres_do,
                status=formularz.status,
                uwagi=formularz.uwagi,
                data_oplacenia=data_oplacenia,
            )
            zapisany_id = zapisz_z_potwierdzeniem(self.window(), self.rejestr, dane)
            if zapisany_id is None:
                self._status("invoice.overwrite_cancelled")
                return
            self.formularz.wczytaj_platnosc(self.rejestr.rachunek(self.aktualny_dokument_id))
            self._zapisany_formularz = self.formularz.stan()
            self.faktura_zapisana.emit(zapisany_id)
            self._aktualizuj_podsumowanie()
            self.formularz.btn_proponuj_wzorzec.show()
            self.formularz.info_propozycji_wzorca.show()
            self._aktualizuj_tekst_propozycji()
            self._message(self.formularz.info_faktury, "invoice.saved")
            self._status("msg.saved")
        except DataPlatnosciZPrzyszlosci:
            QMessageBox.warning(self.window(), t("msg.bill_save_error"), t("payment.future"))
            self.karty.setCurrentIndex(self.ETAP_EDYCJA)
            self.formularz.ed_oplacono.setFocus()
        except (BrakDatyWystawienia, BrakDatyOplacenia) as blad:
            wystawienia = isinstance(blad, BrakDatyWystawienia)
            klucz = "form.issued_required" if wystawienia else "form.paid_date_required"
            pole = self.formularz.ed_wystawiono if wystawienia else self.formularz.ed_oplacono
            QMessageBox.warning(self.window(), t("msg.bill_save_error"), t(klucz))
            self.karty.setCurrentIndex(self.ETAP_EDYCJA)
            pole.setFocus()
        except (ValueError, OSError, sqlite3.Error) as blad:
            QMessageBox.warning(self.window(), t("msg.bill_save_error"), str(blad))

    def _zmien_strone(self, krok: int) -> None:
        try:
            self.podglad.pokaz_strone(self.podglad.strona + krok)
        except ValueError as blad:
            QMessageBox.warning(self.window(), t("msg.render_error"), str(blad))

    def _aktualizuj_nawigacje(self, numer: int, razem: int) -> None:
        self.strony.setText(f"{numer + 1} / {razem}" if razem else t("doc.none"))
        self.poprzednia.setEnabled(razem > 0 and numer > 0)
        self.nastepna.setEnabled(razem > 0 and numer + 1 < razem)

    def _zaznaczenie(self, pole: Zaznaczenie | None) -> None:
        self._wybrany_obszar = pole
        self._aktualizuj_odczyt()
        if pole is None:
            self._message(self.opis_zaznaczenia, "doc.selection_hint")
            return
        self._message(
            self.opis_zaznaczenia, "doc.selection", page=pole.strona + 1,
            left=pole.lewo, top=pole.gora, right=pole.prawo, bottom=pole.dol
        )
