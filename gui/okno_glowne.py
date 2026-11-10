# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Świstak — podgląd PDF, import, formularz i lokalna lista rachunków."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QTextEdit, QVBoxLayout,
    QWidget, QComboBox,
)

from gui.podglad_pdf import PodgladPDF
from gui.odczyt_worker import ZadanieOdczytu
from gui.analiza_worker import ZadanieAnalizy
from uslugi.geometria import Zaznaczenie
from uslugi.odczyt_pdf import WynikOdczytu
from uslugi.analiza_llm import AnalizaModelu, ETYKIETY, POLA
from uslugi.rachunki import DaneRachunku, RejestrRachunkow, grosze_na_kwote
from i18n import LANGUAGES, current_language, set_language, system_language, t
import ustawienia


class OknoGlowne(QMainWindow):
    def __init__(self, rejestr: RejestrRachunkow):
        super().__init__()
        self.rejestr = rejestr
        self.prefs = ustawienia.load()
        set_language(self.prefs["language"])
        self._messages: dict[object, tuple[str, dict]] = {}
        self._status_message: tuple[str, dict] | None = None
        self.aktualny_dokument_id: int | None = None
        self._wybrany_obszar: Zaznaczenie | None = None
        self._zadanie_odczytu: ZadanieOdczytu | None = None
        self._zadanie_ai: ZadanieAnalizy | None = None
        self._analiza: AnalizaModelu | None = None
        self._analiza_dokument_id: int | None = None
        self.setWindowTitle("Świstak — rachunki i analiza AI (etap 3)")
        self.resize(1250, 820)
        self.setMinimumSize(870, 560)

        centrum = QWidget()
        self.setCentralWidget(centrum)
        pion = QVBoxLayout(centrum)
        pion.setContentsMargins(15, 14, 15, 14)
        pion.setSpacing(12)

        naglowek = QHBoxLayout()
        tytul = QLabel("Świstak")
        self.tytul = tytul
        tytul.setObjectName("naglowek")
        naglowek.addWidget(tytul)
        opis = QLabel("Archiwum rachunków • lokalna Ollama")
        self.opis_aplikacji = opis
        opis.setObjectName("podpowiedz")
        naglowek.addWidget(opis)
        naglowek.addStretch()
        pion.addLayout(naglowek)

        pasek = QFrame()
        pasek.setObjectName("pasek")
        przyciski = QHBoxLayout(pasek)
        przyciski.setContentsMargins(10, 8, 10, 8)
        przyciski.setSpacing(7)

        self.otworz_przycisk = QPushButton("Importuj PDF")
        self.otworz_przycisk.clicked.connect(self.wybierz_plik)
        przyciski.addWidget(self.otworz_przycisk)

        self.poprzednia = QPushButton("◀ Poprzednia")
        self.poprzednia.clicked.connect(lambda: self._zmien_strone(-1))
        przyciski.addWidget(self.poprzednia)

        self.strony = QLabel("Brak dokumentu")
        self.strony.setMinimumWidth(100)
        self.strony.setAlignment(Qt.AlignmentFlag.AlignCenter)
        przyciski.addWidget(self.strony)

        self.nastepna = QPushButton("Następna ▶")
        self.nastepna.clicked.connect(lambda: self._zmien_strone(1))
        przyciski.addWidget(self.nastepna)
        przyciski.addStretch()
        for etykieta, akcja in (
            ("−", lambda: self.podglad.powieksz(0.8)),
            ("+", lambda: self.podglad.powieksz(1.25)),
            ("Dopasuj", self.podglad_dopasuj),
        ):
            przycisk = QPushButton(etykieta)
            przycisk.clicked.connect(akcja)
            if etykieta == "Dopasuj":
                self.btn_dopasuj = przycisk
            przyciski.addWidget(przycisk)
        pion.addWidget(pasek)

        dzielnik = QSplitter(Qt.Orientation.Horizontal)
        self.podglad = PodgladPDF()
        self.podglad.zaznaczono.connect(self._zaznaczenie)
        self.podglad.zmiana_strony.connect(self._aktualizuj_nawigacje)
        dzielnik.addWidget(self.podglad)

        self.karty = QTabWidget()
        self.karty.setMinimumWidth(315)
        self.karty.addTab(self._zbuduj_formularz(), "Rachunek")
        self.karty.addTab(self._zbuduj_liste(), "Dokumenty")
        self.karty.addTab(self._zbuduj_odczyt(), "Odczyt PDF")
        self.karty.addTab(self._zbuduj_analize(), "Analiza AI")
        dzielnik.addWidget(self.karty)
        dzielnik.setStretchFactor(0, 3)
        dzielnik.setStretchFactor(1, 2)
        dzielnik.setSizes([800, 410])
        pion.addWidget(dzielnik, 1)

        self.opis_zaznaczenia = QLabel("Zaznacz fragment PDF lewym przyciskiem myszy.")
        self.opis_zaznaczenia.setObjectName("podpowiedz")
        pion.addWidget(self.opis_zaznaczenia)
        self._status("msg.status")
        self._aktualizuj_nawigacje(0, 0)
        self._odswiez_liste()
        self._wyczysc_formularz()
        self._message(self.info_odczytu, "read.start")
        self._message(self.info_ai, "ai.start")
        self._message(self.opis_zaznaczenia, "doc.selection_hint")
        self._aktualizuj_odczyt()
        self._build_menu()
        self._retranslate_ui()

    # UI localization is done IN PLACE: no destruction of the current PDF,
    # input widgets, list selection, OCR output or AI suggestions.
    _FORM_KEYS = (
        "form.supplier", "form.invoice", "form.account", "form.amount",
        "form.category", "form.issued", "form.due", "form.period_from",
        "form.period_to", "form.status", "form.notes",
    )
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

    def _build_menu(self) -> None:
        menu = self.menuBar()
        menu.setNativeMenuBar(False)  # Linux: menu remains inside app window
        self.menu_pliki = menu.addMenu("")
        self.akcja_import = self.menu_pliki.addAction("", self.wybierz_plik)
        self.akcja_odswiez = self.menu_pliki.addAction("", self._odswiez_liste)
        self.menu_pliki.addSeparator()
        self.akcja_zakoncz = self.menu_pliki.addAction("", self.close)

        self.menu_ustawienia = menu.addMenu("")
        self.akcja_konfiguruj = self.menu_ustawienia.addAction("", self._open_settings)

        self.menu_jezyki = menu.addMenu("")
        self._lang_group = QActionGroup(self)
        self._lang_group.setExclusive(True)
        self._lang_actions: dict[str, QAction] = {}
        for code in ("", *LANGUAGES):
            action = QAction("", self)
            action.setCheckable(True)
            self._lang_group.addAction(action)
            self.menu_jezyki.addAction(action)
            action.triggered.connect(lambda checked=False, lang=code: self.change_language(lang))
            self._lang_actions[code] = action
            if code == "":
                self.menu_jezyki.addSeparator()

        self.menu_informacje = menu.addMenu("")
        self.akcja_informacje = self.menu_informacje.addAction("", self._about)

    def change_language(self, code: str) -> None:
        """Mirror AI Bóbr's language policy, preserve existing Qt widgets."""
        if code not in ("", *LANGUAGES):
            raise ValueError("Unknown language")
        if code == self.prefs["language"]:
            self._retranslate_ui()
            return
        saved = dict(self.prefs)
        new = dict(saved, language=code)
        try:
            ustawienia.save(new)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, t("menu.settings"),
                                t("settings.save_failed", error=error))
            self._lang_actions[saved["language"]].setChecked(True)
            return
        self.prefs = new
        set_language(code)
        self._retranslate_ui()

    def _open_settings(self) -> None:
        box = QDialog(self)
        box.setWindowTitle(t("settings.title"))
        layout = QVBoxLayout(box)
        layout.addWidget(QLabel(t("settings.help")))
        form = QFormLayout()
        model = QLineEdit(self.ed_model.text())
        form.addRow(t("settings.model"), model)
        folder = QLineEdit(str(self.rejestr.katalog))
        folder.setReadOnly(True)
        form.addRow(t("settings.data_dir"), folder)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(t("settings.apply"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("settings.cancel"))
        buttons.accepted.connect(box.accept)
        buttons.rejected.connect(box.reject)
        layout.addWidget(buttons)
        if box.exec() != QDialog.DialogCode.Accepted:
            return
        name = model.text().strip()
        if not name or len(name) > 120:
            QMessageBox.warning(self, t("settings.title"), t("settings.invalid"))
            return
        updated = dict(self.prefs, ollama_model=name)
        try:
            ustawienia.save(updated)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, t("settings.title"),
                                t("settings.save_failed", error=error))
            return
        self.prefs = updated
        self.ed_model.setText(name)

    def _about(self) -> None:
        QMessageBox.about(self, t("about.title"), t("about.body"))

    def _message(self, widget: QLabel, key: str, **values) -> None:
        self._messages[widget] = (key, values)
        widget.setText(t(key, **values))

    def _status(self, key: str, **values) -> None:
        self._status_message = (key, values)
        self.statusBar().showMessage(t(key, **values))

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("app.title"))
        self.tytul.setText(t("app.header"))
        self.opis_aplikacji.setText(t("app.subtitle"))
        for menu, key in (
            (self.menu_pliki, "menu.file"),
            (self.menu_ustawienia, "menu.settings"),
            (self.menu_jezyki, "menu.language"),
            (self.menu_informacje, "menu.about"),
        ):
            menu.setTitle(t(key))
        for action, key in (
            (self.akcja_import, "menu.import"),
            (self.akcja_odswiez, "menu.refresh"),
            (self.akcja_zakoncz, "menu.exit"),
            (self.akcja_konfiguruj, "menu.configure"),
            (self.akcja_informacje, "menu.about_dialog"),
        ):
            action.setText(t(key))
        self._lang_actions[""].setText(
            t("language.auto", name=t("language." + system_language()))
        )
        for lang in LANGUAGES:
            self._lang_actions[lang].setText(t("language." + lang))
        self._lang_actions[self.prefs["language"]].setChecked(True)

        self.otworz_przycisk.setText(t("button.import"))
        self.poprzednia.setText(t("button.previous"))
        self.nastepna.setText(t("button.next"))
        self.btn_dopasuj.setText(t("button.fit"))
        self.btn_dodaj_kategorie.setToolTip(t("button.add_category_tip"))
        self.zapisz_przycisk.setText(t("button.save"))
        self.tekst_ostrzezenia_form.setText(t("form.hint"))
        for label, key in zip(self._form_labels, self._FORM_KEYS):
            label.setText(t(key))
        self.ed_konto.setPlaceholderText(t("form.placeholder_account"))
        self.ed_kwota.setPlaceholderText(t("form.placeholder_amount"))
        for field in (self.ed_wystawiono, self.ed_termin, self.ed_od, self.ed_do):
            field.setPlaceholderText(t("form.placeholder_date"))
        self.ed_uwagi.setPlaceholderText(t("form.placeholder_notes"))
        self.wybor_status.setItemText(0, t("form.status_due"))
        self.wybor_status.setItemText(1, t("form.status_paid"))
        self.wybor_kategoria.setItemText(0, t("form.choose_category"))
        for index, key in enumerate(("tab.bill", "tab.documents", "tab.read", "tab.ai")):
            self.karty.setTabText(index, t(key))

        self.hint_listy.setText(t("list.hint"))
        self.btn_odswiez.setText(t("button.refresh"))
        self.hint_odczytu.setText(t("read.hint"))
        self.btn_odczytaj.setText(t("button.read_all"))
        self.btn_odczytaj_obszar.setText(t("button.read_selection"))
        self.btn_anuluj.setText(t("button.cancel"))
        self.btn_kopiuj.setText(t("button.copy"))
        self.pole_odczytu.setPlaceholderText(t("read.placeholder"))
        self.btn_analizuj_z_odczytu.setText(t("button.analyze_text"))
        self.hint_ai.setText(t("ai.hint"))
        self.etykieta_modelu.setText(t("ai.model"))
        self.ed_model.setToolTip(t("ai.model_tip"))
        self.btn_analizuj.setText(t("button.analyze"))
        self.btn_anuluj_ai.setText(t("button.cancel"))
        self.btn_przenies.setText(t("button.apply"))
        self.btn_przenies.setToolTip(t("ai.apply_tip"))
        self.hint_ai_stopka.setText(t("ai.next_step"))
        self.tabela_ai.setHorizontalHeaderLabels([
            t("ai.table.field"), t("ai.table.suggestion"),
            t("ai.table.evidence"), t("ai.table.verdict"),
        ])
        for row, field in enumerate(POLA):
            self.tabela_ai.setItem(row, 0, QTableWidgetItem(t(self._AI_FIELDS[field])))
        # Refresh dynamically displayed messages from keys, without clearing
        # OCR text, form data, selections or analysis rows.
        for widget, (key, values) in list(self._messages.items()):
            widget.setText(t(key, **values))
        if self._status_message is not None:
            key, values = self._status_message
            self.statusBar().showMessage(t(key, **values))
        self._aktualizuj_nawigacje(self.podglad.strona, self.podglad.liczba_stron)

    def _zbuduj_formularz(self) -> QWidget:
        przewijanie = QScrollArea()
        przewijanie.setWidgetResizable(True)
        przewijanie.setFrameShape(QFrame.Shape.NoFrame)
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(10, 14, 10, 12)
        uklad.setSpacing(10)
        self.nazwa_dokumentu = QLabel("Najpierw zaimportuj dokument PDF.")
        self.nazwa_dokumentu.setWordWrap(True)
        uklad.addWidget(self.nazwa_dokumentu)
        forma = QFormLayout()
        forma.setSpacing(8)

        self.ed_dostawca = QLineEdit()
        self.ed_numer = QLineEdit()
        self.ed_konto = QLineEdit()
        self.ed_konto.setPlaceholderText("NRB (26 cyfr) lub IBAN — opcjonalnie")
        self.ed_kwota = QLineEdit()
        self.ed_kwota.setPlaceholderText("np. 245,80")
        self.ed_wystawiono = QLineEdit()
        self.ed_termin = QLineEdit()
        self.ed_od = QLineEdit()
        self.ed_do = QLineEdit()
        for pole in (self.ed_wystawiono, self.ed_termin, self.ed_od, self.ed_do):
            pole.setPlaceholderText("RRRR-MM-DD (opcjonalnie)")

        self.wybor_kategoria = QComboBox()
        wybor_i_dodaj = QWidget()
        kategoria_uklad = QHBoxLayout(wybor_i_dodaj)
        kategoria_uklad.setContentsMargins(0, 0, 0, 0)
        kategoria_uklad.addWidget(self.wybor_kategoria, 1)
        dodaj = QPushButton("+")
        self.btn_dodaj_kategorie = dodaj
        dodaj.setToolTip("Dodaj nową kategorię")
        dodaj.clicked.connect(self._dodaj_kategorie)
        kategoria_uklad.addWidget(dodaj)

        self.wybor_status = QComboBox()
        self.wybor_status.addItem("Do zapłaty", "do_zaplaty")
        self.wybor_status.addItem("Opłacony", "oplacony")
        self.ed_uwagi = QTextEdit()
        self.ed_uwagi.setPlaceholderText("Opcjonalna notatka")
        self.ed_uwagi.setMaximumHeight(86)

        self._form_labels = []
        for etykieta, element in (
            ("Dostawca *", self.ed_dostawca),
            ("Numer faktury", self.ed_numer),
            ("Konto bankowe", self.ed_konto),
            ("Kwota [zł] *", self.ed_kwota),
            ("Kategoria *", wybor_i_dodaj),
            ("Wystawiono", self.ed_wystawiono),
            ("Termin płatności", self.ed_termin),
            ("Okres od", self.ed_od),
            ("Okres do", self.ed_do),
            ("Status", self.wybor_status),
            ("Uwagi", self.ed_uwagi),
        ):
            forma.addRow(etykieta, element)
            self._form_labels.append(forma.labelForField(element))
        uklad.addLayout(forma)
        self.zapisz_przycisk = QPushButton("Zapisz rachunek")
        self.zapisz_przycisk.clicked.connect(self._zapisz_rachunek)
        uklad.addWidget(self.zapisz_przycisk)
        komunikat = QLabel("Dane od AI są wyłącznie propozycjami. Sprawdź PDF, popraw pola i dopiero kliknij Zapisz rachunek.")
        self.tekst_ostrzezenia_form = komunikat
        komunikat.setWordWrap(True)
        komunikat.setObjectName("podpowiedz")
        uklad.addWidget(komunikat)
        uklad.addStretch()
        przewijanie.setWidget(panel)
        return przewijanie

    def _zbuduj_odczyt(self) -> QWidget:
        """Podgląd surowego tekstu, zanim trafi do Ollamy."""
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(10, 12, 10, 12)
        uklad.setSpacing(10)
        instrukcja = QLabel(
            "Tekst pozyskany z PDF lub OCR jest tylko materiałem wejściowym. "
            "Po odczycie możesz uruchomić lokalny model w zakładce Analiza AI."
        )
        self.hint_odczytu = instrukcja
        instrukcja.setWordWrap(True)
        instrukcja.setObjectName("podpowiedz")
        uklad.addWidget(instrukcja)
        przyciski = QHBoxLayout()
        self.btn_odczytaj = QPushButton("Odczytaj cały PDF")
        self.btn_odczytaj.clicked.connect(lambda: self._start_odczytu(False))
        przyciski.addWidget(self.btn_odczytaj)
        self.btn_odczytaj_obszar = QPushButton("Odczytaj zaznaczenie")
        self.btn_odczytaj_obszar.clicked.connect(lambda: self._start_odczytu(True))
        przyciski.addWidget(self.btn_odczytaj_obszar)
        uklad.addLayout(przyciski)
        self.btn_anuluj = QPushButton("Anuluj")
        self.btn_anuluj.clicked.connect(self._anuluj_odczyt)
        uklad.addWidget(self.btn_anuluj)
        self.info_odczytu = QLabel("Wybierz dokument PDF, aby odczytać jego tekst.")
        self.info_odczytu.setWordWrap(True)
        uklad.addWidget(self.info_odczytu)
        self.pole_odczytu = QTextEdit()
        self.pole_odczytu.setReadOnly(True)
        self.pole_odczytu.setPlaceholderText(
            "Tutaj pojawi się tekst dokumentu. Odczyt nie zmienia oryginalnego PDF."
        )
        uklad.addWidget(self.pole_odczytu, 1)
        kopiuj = QPushButton("Kopiuj tekst")
        self.btn_kopiuj = kopiuj
        kopiuj.clicked.connect(
            lambda: QApplication.clipboard().setText(self.pole_odczytu.toPlainText())
        )
        uklad.addWidget(kopiuj)
        self.btn_analizuj_z_odczytu = QPushButton("Analizuj tekst przez AI (Ollama)")
        self.btn_analizuj_z_odczytu.clicked.connect(self._start_analizy)
        uklad.addWidget(self.btn_analizuj_z_odczytu)
        return panel

    def _zbuduj_analize(self) -> QWidget:
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(10, 12, 10, 12)
        uklad.setSpacing(8)

        instrukcja = QLabel(
            "Najpierw użyj Odczyt PDF. Lokalny LLM proponuje wartości; "
            "Świstak sprawdza format, a Ty decydujesz, co przenieść do formularza. "
            "Nic nie jest zapisywane automatycznie."
        )
        self.hint_ai = instrukcja
        instrukcja.setWordWrap(True)
        instrukcja.setObjectName("podpowiedz")
        uklad.addWidget(instrukcja)

        model_uklad = QHBoxLayout()
        self.etykieta_modelu = QLabel("Model Ollama:")
        model_uklad.addWidget(self.etykieta_modelu)
        self.ed_model = QLineEdit(self.prefs.get("ollama_model", "gemma3:4b"))
        self.ed_model.setToolTip("Nazwa lokalnie zainstalowanego modelu (ollama list)")
        model_uklad.addWidget(self.ed_model)
        uklad.addLayout(model_uklad)

        akcje = QHBoxLayout()
        self.btn_analizuj = QPushButton("Analizuj rachunek przez AI")
        self.btn_analizuj.clicked.connect(self._start_analizy)
        akcje.addWidget(self.btn_analizuj)
        self.btn_anuluj_ai = QPushButton("Anuluj")
        self.btn_anuluj_ai.clicked.connect(self._anuluj_analize)
        akcje.addWidget(self.btn_anuluj_ai)
        uklad.addLayout(akcje)

        self.info_ai = QLabel("Odczytaj PDF, aby rozpocząć analizę lokalnym modelem.")
        self.info_ai.setWordWrap(True)
        uklad.addWidget(self.info_ai)

        self.tabela_ai = QTableWidget(len(POLA), 4)
        self.tabela_ai.setHorizontalHeaderLabels(["Pole", "Sugestia AI", "Dowód z tekstu", "Ocena"])
        self.tabela_ai.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela_ai.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela_ai.setWordWrap(True)
        self.tabela_ai.setColumnWidth(0, 130)
        self.tabela_ai.setColumnWidth(1, 150)
        self.tabela_ai.setColumnWidth(2, 210)
        self.tabela_ai.setColumnWidth(3, 190)
        for n, pole in enumerate(POLA):
            self.tabela_ai.setItem(n, 0, QTableWidgetItem(ETYKIETY[pole]))
        uklad.addWidget(self.tabela_ai, 1)

        self.btn_przenies = QPushButton("Przenieś zweryfikowane pola do formularza")
        self.btn_przenies.setToolTip("Nie zapisuje rachunku w SQLite")
        self.btn_przenies.clicked.connect(self._przenies_sugestie)
        uklad.addWidget(self.btn_przenies)
        self.hint_ai_stopka = QLabel("Następnie sprawdź wszystkie dane i użyj Zapisz rachunek w karcie Rachunek.")
        self.hint_ai_stopka.setWordWrap(True)
        uklad.addWidget(self.hint_ai_stopka)
        return panel

    def _wyczysc_analize(self) -> None:
        self._analiza = None
        self._analiza_dokument_id = None
        for r in range(len(POLA)):
            for c in range(1, 4):
                self.tabela_ai.setItem(r, c, QTableWidgetItem(""))
        self._message(self.info_ai, "ai.none")

    def _aktualizuj_ai(self) -> None:
        zajete = self._zadanie_ai is not None or self._zadanie_odczytu is not None
        dokument = self.aktualny_dokument_id is not None
        tekst = bool(self.pole_odczytu.toPlainText().strip())
        mozna = dokument and tekst and not zajete
        self.btn_analizuj.setEnabled(mozna)
        self.btn_analizuj_z_odczytu.setEnabled(mozna)
        self.btn_anuluj_ai.setEnabled(self._zadanie_ai is not None)
        self.btn_przenies.setEnabled(
            not zajete and self._analiza is not None
            and self._analiza_dokument_id == self.aktualny_dokument_id
            and any(x.poprawne for x in self._analiza.oceny.values())
        )

    def _start_analizy(self) -> None:
        if self._zadanie_ai is not None or self._zadanie_odczytu is not None:
            return
        if self.aktualny_dokument_id is None:
            QMessageBox.information(self, t("tab.ai"), t("msg.no_pdf"))
            return
        tekst = self.pole_odczytu.toPlainText()
        if not tekst.strip():
            QMessageBox.information(
                self, t("tab.ai"), t("msg.read_before_ai")
            )
            return
        model = self.ed_model.text().strip()
        if not model:
            QMessageBox.warning(self, t("tab.ai"), t("msg.model_required"))
            return
        kategorie = [wiersz["nazwa"] for wiersz in self.rejestr.kategorie()]
        zadanie = ZadanieAnalizy(self.aktualny_dokument_id, tekst, kategorie, model)
        self._wyczysc_analize()
        self._zadanie_ai = zadanie
        self.karty.setCurrentIndex(3)
        self._message(self.info_ai, "ai.working", model=model)
        zadanie.sygnaly.gotowe.connect(self._analiza_gotowa)
        zadanie.sygnaly.blad.connect(self._analiza_blad)
        zadanie.sygnaly.anulowano.connect(self._analiza_anulowana)
        self._aktualizuj_odczyt()
        QThreadPool.globalInstance().start(zadanie)

    def _analiza_gotowa(self, dokument_id: int, wynik: AnalizaModelu) -> None:
        self._zadanie_ai = None
        if dokument_id != self.aktualny_dokument_id:
            self._aktualizuj_odczyt()
            return
        self._analiza = wynik
        self._analiza_dokument_id = dokument_id
        ile = 0
        for r, pole in enumerate(POLA):
            ocena = wynik.oceny[pole]
            if ocena.poprawne:
                ile += 1
            tresci = (
                ocena.wartosc if ocena.wartosc is not None else "—",
                ocena.dowod or "—",
                ("✓ " if ocena.poprawne else "⚠ ") + ocena.komunikat,
            )
            for c, napis in enumerate(tresci, 1):
                element = QTableWidgetItem(napis)
                element.setToolTip(napis)
                self.tabela_ai.setItem(r, c, element)
        self.tabela_ai.resizeRowsToContents()
        self._message(self.info_ai, "ai.done", model=wynik.model, count=ile, total=len(POLA))
        self._aktualizuj_odczyt()

    def _analiza_blad(self, dokument_id: int, komunikat: str) -> None:
        self._zadanie_ai = None
        self._message(self.info_ai, "ai.failed")
        self._aktualizuj_odczyt()
        if dokument_id == self.aktualny_dokument_id:
            QMessageBox.warning(self, t("msg.ai_error"), komunikat)

    def _analiza_anulowana(self, dokument_id: int) -> None:
        self._zadanie_ai = None
        self._message(self.info_ai, "ai.cancelled")
        self._aktualizuj_odczyt()

    def _anuluj_analize(self) -> None:
        if self._zadanie_ai is not None:
            self._zadanie_ai.przerwij.set()
            self._message(self.info_ai, "ai.cancelling")

    def _przenies_sugestie(self) -> None:
        if (self._analiza is None or
                self._analiza_dokument_id != self.aktualny_dokument_id):
            return
        oceny = self._analiza.oceny
        pola_do_formularza = {
            "dostawca": self.ed_dostawca,
            "numer_faktury": self.ed_numer,
            "kwota_do_zaplaty": self.ed_kwota,
            "data_wystawienia": self.ed_wystawiono,
            "termin_platnosci": self.ed_termin,
            "okres_od": self.ed_od,
            "okres_do": self.ed_do,
            "numer_konta_bankowego": self.ed_konto,
        }
        do_zastosowania = [
            p for p in pola_do_formularza if oceny[p].poprawne
        ]
        if oceny["kategoria_sugerowana"].poprawne:
            do_zastosowania.append("kategoria_sugerowana")
        if not do_zastosowania:
            return
        odp = QMessageBox.question(
            self, t("ai.confirm_title"),
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
            id_kategorii = self.wybor_kategoria.findText(
                oceny["kategoria_sugerowana"].wartosc, Qt.MatchFlag.MatchFixedString
            )
            if id_kategorii >= 0:
                self.wybor_kategoria.setCurrentIndex(id_kategorii)
        self._analiza = None  # nie pozwól ponownie użyć nieaktualnej propozycji
        self._aktualizuj_odczyt()
        self.karty.setCurrentIndex(0)
        self._status("ai.saved_hint")

    def _aktualizuj_odczyt(self) -> None:
        pracuje = self._zadanie_odczytu is not None or self._zadanie_ai is not None
        jest_dokument = self.aktualny_dokument_id is not None
        self.btn_odczytaj.setEnabled(jest_dokument and not pracuje)
        self.btn_odczytaj_obszar.setEnabled(
            jest_dokument and self._wybrany_obszar is not None and not pracuje
        )
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
            QMessageBox.warning(self, t("msg.pdf"), str(blad))
            return
        zadanie = ZadanieOdczytu(sciezka, obszar)
        self._wyczysc_analize()
        self._zadanie_odczytu = zadanie
        self._aktualizuj_odczyt()
        self.pole_odczytu.clear()
        self._message(self.info_odczytu, "read.running")
        self.karty.setCurrentIndex(2)
        zadanie.sygnaly.gotowe.connect(self._odczyt_gotowy)
        zadanie.sygnaly.blad.connect(self._odczyt_blad)
        zadanie.sygnaly.anulowano.connect(self._odczyt_anulowano)
        QThreadPool.globalInstance().start(zadanie)

    def _odczyt_gotowy(self, wynik: WynikOdczytu) -> None:
        self._zadanie_odczytu = None
        self._aktualizuj_odczyt()
        self.pole_odczytu.setPlainText(wynik.tekst_dla_llm)
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
        QMessageBox.warning(self, t("msg.pdf"), komunikat)

    def _odczyt_anulowano(self) -> None:
        self._zadanie_odczytu = None
        self._aktualizuj_odczyt()
        self._message(self.info_odczytu, "read.cancelled")

    def _anuluj_odczyt(self) -> None:
        if self._zadanie_odczytu is not None:
            self._zadanie_odczytu.przerwij.set()
            self._message(self.info_odczytu, "msg.read_cancelling")

    def closeEvent(self, event) -> None:
        if self._zadanie_odczytu is not None:
            self._zadanie_odczytu.przerwij.set()
        if self._zadanie_ai is not None:
            self._zadanie_ai.przerwij.set()
        super().closeEvent(event)

    def _zbuduj_liste(self) -> QWidget:
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(8, 10, 8, 10)
        opis = QLabel("Wybierz zaimportowany dokument, aby go otworzyć lub uzupełnić.")
        self.hint_listy = opis
        opis.setWordWrap(True)
        uklad.addWidget(opis)
        self.lista_dokumentow = QListWidget()
        self.lista_dokumentow.itemClicked.connect(self._wybierz_z_listy)
        uklad.addWidget(self.lista_dokumentow)
        przycisk = QPushButton("Odśwież listę")
        self.btn_odswiez = przycisk
        przycisk.clicked.connect(self._odswiez_liste)
        uklad.addWidget(przycisk)
        return panel

    def _odswiez_kategorie(self, wybrana: int | None = None) -> None:
        self.wybor_kategoria.clear()
        self.wybor_kategoria.addItem("— wybierz kategorię —", None)
        for wiersz in self.rejestr.kategorie():
            self.wybor_kategoria.addItem(wiersz["nazwa"], int(wiersz["id"]))
        if wybrana is not None:
            numer = self.wybor_kategoria.findData(wybrana)
            if numer >= 0:
                self.wybor_kategoria.setCurrentIndex(numer)

    def _dodaj_kategorie(self) -> None:
        nazwa, zaakceptowano = QInputDialog.getText(self, t("msg.new_category"), t("msg.category_name"))
        if not zaakceptowano:
            return
        try:
            identyfikator = self.rejestr.dodaj_kategorie(nazwa)
            self._odswiez_kategorie(identyfikator)
        except (ValueError, sqlite3.Error) as blad:
            QMessageBox.warning(self, t("msg.category"), str(blad))

    def _odswiez_liste(self) -> None:
        self.lista_dokumentow.clear()
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

    def _wyczysc_formularz(self) -> None:
        self._message(self.nazwa_dokumentu, "doc.import_first")
        for pole in (self.ed_dostawca, self.ed_numer, self.ed_konto, self.ed_kwota, self.ed_wystawiono,
                     self.ed_termin, self.ed_od, self.ed_do):
            pole.clear()
        self.ed_uwagi.clear()
        self.wybor_status.setCurrentIndex(0)
        self._odswiez_kategorie()
        self.zapisz_przycisk.setEnabled(False)

    def _wyswietl_dokument(self, dokument_id: int) -> None:
        self._wybrany_obszar = None
        self._wyczysc_analize()
        self.pole_odczytu.clear()
        self._message(self.info_odczytu, "doc.opened")
        sciezka = self.rejestr.sciezka_pdf(dokument_id)
        # Przy błędzie (np. uszkodzony plik archiwalny) nie pozwalaj zapisywać
        # pól pod niewłaściwym dokumentem.
        self.aktualny_dokument_id = None
        self.zapisz_przycisk.setEnabled(False)
        self.podglad.otworz(sciezka)
        dokument = self.rejestr.dokument(dokument_id)
        self.aktualny_dokument_id = dokument_id
        self._message(self.nazwa_dokumentu, "doc.original", name=dokument["nazwa_zrodlowa"])
        zapis = self.rejestr.rachunek(dokument_id)
        self._wyczysc_formularz()
        self.nazwa_dokumentu.setText("Oryginał: " + dokument["nazwa_zrodlowa"])
        if zapis is not None:
            self.ed_dostawca.setText(zapis["dostawca"])
            self.ed_numer.setText(zapis["numer"])
            self.ed_konto.setText(zapis["numer_konta"])
            self.ed_kwota.setText(grosze_na_kwote(zapis["kwota_grosze"]))
            self.ed_wystawiono.setText(zapis["data_wystawienia"] or "")
            self.ed_termin.setText(zapis["termin_platnosci"] or "")
            self.ed_od.setText(zapis["okres_od"] or "")
            self.ed_do.setText(zapis["okres_do"] or "")
            self.ed_uwagi.setPlainText(zapis["uwagi"])
            self._odswiez_kategorie(zapis["kategoria_id"])
            idx = self.wybor_status.findData(zapis["status"])
            if idx >= 0:
                self.wybor_status.setCurrentIndex(idx)
        self.zapisz_przycisk.setEnabled(True)
        self._aktualizuj_odczyt()
        self.karty.setCurrentIndex(0)
        self._status("msg.opened", name=dokument["nazwa_zrodlowa"])

    def _wybierz_z_listy(self, element: QListWidgetItem) -> None:
        try:
            self._wyswietl_dokument(int(element.data(Qt.ItemDataRole.UserRole)))
        except (ValueError, OSError, sqlite3.Error) as blad:
            QMessageBox.warning(self, t("msg.document_open_error"), str(blad))

    def podglad_dopasuj(self) -> None:
        self.podglad.dopasuj()

    def wybierz_plik(self) -> None:
        sciezka, _ = QFileDialog.getOpenFileName(
            self, t("msg.import_dialog"), "", t("msg.pdf_filter")
        )
        if sciezka:
            self.otworz_pdf(sciezka)

    def otworz_pdf(self, sciezka: str | Path) -> None:
        try:
            # Zweryfikuj PDF w Qt przed dodaniem go do archiwum i bazy.
            self.aktualny_dokument_id = None
            self.zapisz_przycisk.setEnabled(False)
            self.podglad.otworz(sciezka)
            dokument_id, czy_nowy = self.rejestr.importuj_pdf(sciezka)
            self._wyswietl_dokument(dokument_id)
            self._odswiez_liste()
            if not czy_nowy:
                self._status("msg.duplicate")
        except (OSError, ValueError, sqlite3.Error) as blad:
            QMessageBox.warning(self, t("msg.document_import_error"), str(blad))

    def _zapisz_rachunek(self) -> None:
        if self.aktualny_dokument_id is None:
            return
        try:
            dane = DaneRachunku(
                dokument_id=self.aktualny_dokument_id,
                dostawca=self.ed_dostawca.text(),
                numer=self.ed_numer.text(),
                numer_konta=self.ed_konto.text(),
                kwota=self.ed_kwota.text(),
                kategoria_id=self.wybor_kategoria.currentData(),
                data_wystawienia=self.ed_wystawiono.text(),
                termin_platnosci=self.ed_termin.text(),
                okres_od=self.ed_od.text(),
                okres_do=self.ed_do.text(),
                status=self.wybor_status.currentData(),
                uwagi=self.ed_uwagi.toPlainText(),
            )
            self.rejestr.zapisz_rachunek(dane)
            self._odswiez_liste()
            self._status("msg.saved")
        except (ValueError, OSError, sqlite3.Error) as blad:
            QMessageBox.warning(self, t("msg.bill_save_error"), str(blad))

    def _zmien_strone(self, krok: int) -> None:
        try:
            self.podglad.pokaz_strone(self.podglad.strona + krok)
        except ValueError as blad:
            QMessageBox.warning(self, t("msg.render_error"), str(blad))

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
