# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Zakładka analizy AI i pracy ze wzorcami faktur."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from ai_core.errors import ExtractionContextExceeded
from gui.analiza_worker import ZadanieAnalizy
from gui.dialog_wzorca import zaakceptuj_wzorzec
from gui.uklad import Siatka
from i18n import t
from uslugi.analiza_llm import AnalizaModelu, ETYKIETY, POLA, ocena_json
from uslugi.dopasowanie_wzorca import Dopasowanie, dopasuj, zaproponuj_wzorzec
from uslugi.propozycja_wzorca import zaproponuj_aktualizacje
from uslugi.rachunki import RejestrRachunkow
from uslugi.wzorce import MagazynWzorcow


class ZakladkaAnalizy(QWidget):
    """Konfiguracja analizy, postęp, sprawdzanie wyników i wzorce faktur."""

    pokaz_agenta = Signal()
    wybor_modelu = Signal()
    model_zmieniony = Signal(str)
    wybor_kategorii = Signal()
    analiza_zadana = Signal()
    rozpoczeto = Signal()
    stan_pracy_zmieniony = Signal()
    limit_kontekstu = Signal()
    sugestie_zatwierdzone = Signal(dict)
    wzorzec_odswiezony = Signal()
    status_zmieniony = Signal(str, dict)

    _VALIDATION_KEYS = {
        "Brak danych — uzupełnij ręcznie": "validation.missing",
        "Brak potwierdzenia w tekście": "validation.evidence",
        "Dowód z obrazu niepotwierdzony przez OCR — sprawdź w PDF": "validation.image_unverified",
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

    def __init__(self, rejestr: RejestrRachunkow, magazyn_wzorcow: MagazynWzorcow, prefs: dict):
        super().__init__()
        self.rejestr = rejestr
        self.magazyn_wzorcow = magazyn_wzorcow
        self._dokument_id: int | None = None
        self._tekst = ""
        self._odczyt_trwa = False
        self._dopasowanie_wzorca: Dopasowanie | None = None
        self._aktywny_wzorzec: dict | None = None
        self._wzorzec_pominiety = False
        self._tekst_dopasowania = ""
        self._wzorzec_dokument_id: int | None = None
        self._komentarze_wzorca: dict[str, str] = {}
        self._zadanie_ai: ZadanieAnalizy | None = None
        self._analiza: AnalizaModelu | None = None
        self._analiza_dokument_id: int | None = None
        self._aktualizuje_tabele_ai = False
        self._pola_potwierdzone_recznie: set[str] = set()
        uklad = QVBoxLayout(self)
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
        self.btn_analizuj.clicked.connect(self.uruchom)
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
        self.btn_dodaj_kategorie_ai.clicked.connect(self.wybor_kategorii)
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
        self.ed_model.textChanged.connect(self.model_zmieniony)
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
        self._message("ai.start")
        self.wczytaj_ustawienia(prefs)

    @property
    def pracuje(self) -> bool:
        return self._zadanie_ai is not None

    @property
    def model(self) -> str:
        return self.ed_model.text()

    @property
    def ma_aktywny_wzorzec(self) -> bool:
        return self._aktywny_wzorzec is not None

    def wczytaj_ustawienia(self, prefs: dict) -> None:
        self.ed_model.setText(prefs.get("ollama_model", "gemma3:4b"))
        self._model_ekstrakcji = prefs.get("model_extractor") or None

    def ustaw_wejscie(self, dokument_id: int | None, tekst: str, *, odczyt_trwa: bool) -> None:
        self._dokument_id = dokument_id
        self._tekst = tekst
        self._odczyt_trwa = odczyt_trwa
        self._aktualizuj_ai()

    def zamknij(self) -> None:
        if self._zadanie_ai is not None:
            self._zadanie_ai.anuluj()

    def _message(self, klucz: str, **wartosci) -> None:
        self._komunikat = (klucz, wartosci)
        self.info_ai.setText(t(klucz, **wartosci))

    def przetlumacz(self) -> None:
        self.zakladki_ai.setTabText(0, t("ai.tab_data"))
        self.zakladki_ai.setTabText(1, t("ai.tab_agent"))
        self.btn_info_ai.setToolTip(t("ai.info_title"))
        self.postep_ai.setAccessibleName(t("ai.progress.accessible"))
        self.btn_wybierz_wzorzec.setText(t("patterns.choose"))
        self.etykieta_notatek_wzorca.setText(t("patterns.notes"))
        self.notatki_wzorca.setPlaceholderText(t("patterns.notes_placeholder"))
        self.info_notatek_agenta.setText(t("ai.notes_scope"))
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
        self._aktualizuj_info_wzorca()
        klucz, wartosci = self._komunikat
        self.info_ai.setText(t(klucz, **wartosci))

    def _validation_message(self, value: str) -> str:
        key = self._VALIDATION_KEYS.get(value)
        return t(key) if key else value

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

    @Slot(int, str)
    def _etap_postepu_ai(self, dokument_id: int, etap: str) -> None:
        """Etapy pochodzą z pracującego wątku; GUI aktualizuje wyłącznie Qt."""
        if (self._zadanie_ai is None or
                dokument_id != self._dokument_id or
                self._zadanie_ai.przerwij.is_set()):
            return
        if etap in ("prepare", "ollama", "validate"):
            self._message("ai.progress." + etap,
                          model=self._zadanie_ai.model)

    def _koniec_postepu_ai(self, sukces: bool) -> None:
        self.postep_ai.setRange(0, 100)
        self.postep_ai.setValue(100 if sukces else 0)
        self.postep_ai.setVisible(sukces)

    def wyczysc_wynik(self) -> None:
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
        self._message("ai.none")

    def _przelicz_sugestie_ai(self) -> None:
        """Zastosuj te same walidacje co po odpowiedzi Ollamy, ale bez żądania AI."""
        if self._analiza is None or self._analiza_dokument_id != self._dokument_id:
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
            dane, self._tekst,
            [wiersz["nazwa"] for wiersz in self.rejestr.kategorie()],
            potwierdzone_recznie=self._pola_potwierdzone_recznie,
            obraz=self._analiza.zrodlo == "obraz",
        )
        self._analiza = AnalizaModelu(self._analiza.model, oceny, self._analiza.zrodlo)
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
        if self._analiza is None or self._analiza_dokument_id != self._dokument_id:
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
        zajete = self._zadanie_ai is not None or self._odczyt_trwa
        dokument = self._dokument_id is not None
        mozna = dokument and not zajete
        self.btn_analizuj.setEnabled(mozna)
        self.btn_anuluj_ai.setEnabled(self._zadanie_ai is not None)
        analiza_dokumentu = (
            self._analiza is not None
            and self._analiza_dokument_id == self._dokument_id
        )
        self.btn_przenies.setEnabled(
            not zajete and analiza_dokumentu
            and any(x.poprawne for x in self._analiza.oceny.values())
        )
        self.btn_potwierdz_recznie.setEnabled(not zajete and analiza_dokumentu)
        self.btn_dodaj_kategorie_ai.setEnabled(not zajete and analiza_dokumentu)

    @Slot()
    def uruchom(self) -> None:
        if self._zadanie_ai is not None or self._odczyt_trwa:
            return
        if self._dokument_id is None:
            QMessageBox.information(self.window(), t("tab.ai"), t("msg.no_pdf"))
            return
        tekst = self._tekst
        model = self.ed_model.text().strip()
        if not model:
            QMessageBox.warning(self.window(), t("tab.ai"), t("msg.model_required"))
            return
        # Analiza żądana przez użytkownika ma pierwszeństwo nad monitorem
        # uruchomionym automatycznie w tle.
        self.analiza_zadana.emit()
        if (self._wzorzec_dokument_id != self._dokument_id
                or self._tekst_dopasowania != tekst):
            self.wykryj_wzorzec()
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
        try:
            sciezka = self.rejestr.sciezka_pdf(self._dokument_id)
        except (ValueError, OSError) as blad:
            QMessageBox.warning(self.window(), t("msg.ai_error"), str(blad))
            return
        kategorie = [wiersz["nazwa"] for wiersz in self.rejestr.kategorie()]
        zadanie = ZadanieAnalizy(
            self._dokument_id, tekst, kategorie, model,
            wzorzec=self._aktywny_wzorzec,
            model_ekstrakcji=self._model_ekstrakcji,
            sciezka_pdf=sciezka,
        )
        self.wyczysc_wynik()
        self._zadanie_ai = zadanie
        self.rozpoczeto.emit()
        self.zakladki_ai.setCurrentIndex(0)
        self._message("ai.progress.prepare", model=model)
        self._start_postep_ai()
        zadanie.sygnaly.etap.connect(self._etap_postepu_ai)
        zadanie.sygnaly.gotowe.connect(self._analiza_gotowa)
        zadanie.sygnaly.blad.connect(self._analiza_blad)
        zadanie.sygnaly.anulowano.connect(self._analiza_anulowana)
        self.stan_pracy_zmieniony.emit()
        QThreadPool.globalInstance().start(zadanie)

    @Slot(int, object)
    def _analiza_gotowa(self, dokument_id: int, wynik: AnalizaModelu) -> None:
        self._zadanie_ai = None
        if dokument_id != self._dokument_id:
            self._koniec_postepu_ai(False)
            self.stan_pracy_zmieniony.emit()
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
        self._message("ai.done", model=wynik.model, count=ile, total=len(POLA))
        self.zakladki_ai.setCurrentIndex(0)
        self.stan_pracy_zmieniony.emit()

    @Slot(int, str)
    def _analiza_blad(self, dokument_id: int, komunikat: str) -> None:
        self._koniec_postepu_ai(False)
        self._zadanie_ai = None
        za_dlugi = komunikat == ExtractionContextExceeded.code
        klucz = "ai.context_exceeded" if za_dlugi else "ai.failed"
        self._message(klucz)
        self.stan_pracy_zmieniony.emit()
        if dokument_id == self._dokument_id:
            QMessageBox.warning(self.window(), t("msg.ai_error"), t(klucz) if za_dlugi else komunikat)
            if za_dlugi:
                self.limit_kontekstu.emit()

    @Slot(int)
    def _analiza_anulowana(self, dokument_id: int) -> None:
        self._koniec_postepu_ai(False)
        self._zadanie_ai = None
        self._message("ai.cancelled")
        self.stan_pracy_zmieniony.emit()

    def _anuluj_analize(self) -> None:
        if self._zadanie_ai is not None:
            self._zadanie_ai.anuluj()
            self._message("ai.cancelling")

    def _przenies_sugestie(self) -> None:
        if self._analiza is None or self._analiza_dokument_id != self._dokument_id:
            return
        oceny = self._analiza.oceny
        sugestie = {
            pole: oceny[pole].wartosc for pole in POLA
            if pole != "waluta" and oceny[pole].poprawne
        }
        if not sugestie:
            return
        odp = QMessageBox.question(
            self.window(), t("ai.confirm_title"),
            t("ai.confirm_body", count=len(sugestie)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if odp != QMessageBox.StandardButton.Yes:
            return
        self._analiza = None  # nie pozwól ponownie użyć nieaktualnej propozycji
        self._pola_potwierdzone_recznie.clear()
        self._aktualizuj_ai()
        self.sugestie_zatwierdzone.emit(sugestie)

    def wprowadz_kategorie(self, nazwa: str) -> None:
        if self._analiza is None or self._analiza_dokument_id != self._dokument_id:
            return
        pole = "kategoria_sugerowana"
        element = self.tabela_ai.item(POLA.index(pole), 1)
        if element is None:
            return
        self._aktualizuje_tabele_ai = True
        try:
            element.setText(nazwa)
        finally:
            self._aktualizuje_tabele_ai = False
        self._pola_potwierdzone_recznie.add(pole)
        self._przelicz_sugestie_ai()

    def resetuj_dokument(self) -> None:
        self.wyczysc_wynik()
        self._komentarze_wzorca.clear()
        self._odswiez_komentarze_ai()
        self.notatki_wzorca.clear()
        self._dopasowanie_wzorca = None
        self._aktywny_wzorzec = None
        self._wzorzec_pominiety = False
        self._wzorzec_dokument_id = None
        self._tekst_dopasowania = ""
        self._aktualizuj_info_wzorca()

    def _aktualizuj_info_wzorca(self) -> None:
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
        self.wzorzec_odswiezony.emit()

    def wykryj_wzorzec(self) -> None:
        """Rozpoznanie tylko po wstępnym OCR; żadnego zapisu i żadnego LLM."""
        tekst = self._tekst
        self._wzorzec_dokument_id = self._dokument_id
        self._tekst_dopasowania = tekst
        self._dopasowanie_wzorca = None
        self._aktywny_wzorzec = None
        self._wzorzec_pominiety = False
        if tekst.strip() and self._dokument_id is not None:
            try:
                self._dopasowanie_wzorca = dopasuj(
                    tekst, self.magazyn_wzorcow.lista(tylko_aktywne=True)
                )
                if (self._dopasowanie_wzorca is not None
                        and self._dopasowanie_wzorca.poziom == "automatic"):
                    self._aktywny_wzorzec = self._dopasowanie_wzorca.wzorzec
            except (OSError, ValueError):
                self.info_wzorca.setText(t("patterns.load_error"))
                self.wzorzec_odswiezony.emit()
                self.status_zmieniony.emit("patterns.load_error", {})
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
        if self._dokument_id is None:
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

    def zaproponuj_zapis_wzorca(self, dostawca: str, kategoria: str | None) -> None:
        """Pokaż osobny przegląd wzorca przed zapisaniem zatwierdzonych reguł."""
        tekst = self._tekst
        if not tekst.strip():
            QMessageBox.information(
                self.window(), t("patterns.title"), t("patterns.read_first")
            )
            return
        try:
            candidate = zaproponuj_wzorzec(
                tekst, dostawca, kategoria,
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
            self.status_zmieniony.emit("patterns.saved", {"name": saved["name"]})
        except (ValueError, OSError, TypeError) as error:
            QMessageBox.warning(self.window(), t("patterns.title"), str(error))
