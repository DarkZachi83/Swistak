# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Proces importu, OCR, analizy i zapisu faktury."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
    QSplitter, QStackedWidget, QStyle, QVBoxLayout, QWidget,
)

from gui.dialog_kategorie import DialogKategorie
from gui.dialog_qr import DialogQR
from gui.formularz_faktury import FormularzFaktury, StanFormularza
from gui.okno_wzorcow import OknoWzorcow
from gui.podglad_pdf import PodgladPDF
from gui.uklad import Siatka
from gui.zakladka_analizy import ZakladkaAnalizy
from gui.zakladka_odczytu import ZakladkaOdczytu
from gui.zapis_faktury import zapisz_z_potwierdzeniem
from i18n import t
from uslugi.finanse import DataPlatnosciZPrzyszlosci, sprawdz_date_platnosci
from uslugi.geometria import Zaznaczenie
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
    odswiez_dokumenty = Signal()
    kategorie_zmienione = Signal()
    faktura_zapisana = Signal(int)
    status_zmieniony = Signal(str, dict)

    def __init__(self, rejestr: RejestrRachunkow, prefs: dict):
        super().__init__()
        self.rejestr = rejestr
        self._messages: dict[QLabel, tuple[str, dict]] = {}
        self.magazyn_wzorcow = MagazynWzorcow(rejestr.katalog)
        self.aktualny_dokument_id: int | None = None
        self._zapisany_formularz: StanFormularza | None = None
        self._wybrany_obszar: Zaznaczenie | None = None
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
        self.odczyt = ZakladkaOdczytu()
        self.analiza = ZakladkaAnalizy(self.rejestr, self.magazyn_wzorcow, prefs)
        self.karty.addWidget(self.odczyt)
        self.karty.addWidget(self.analiza)
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
        self.odczyt.odczyt_zadany.connect(self._start_odczytu)
        self.odczyt.analiza_zadana.connect(self.analiza.uruchom)
        self.odczyt.qr_zadany.connect(self._otworz_qr)
        self.odczyt.tekst_zmieniony.connect(self._aktualizuj_dostepnosc)
        self.odczyt.tekst_odczytany.connect(self.analiza.wykryj_wzorzec)
        self.odczyt.stan_pracy_zmieniony.connect(self._aktualizuj_dostepnosc)
        self.odczyt.status_zmieniony.connect(self.status_zmieniony)
        self.analiza.wybor_kategorii.connect(self._dodaj_kategorie)
        self.analiza.rozpoczeto.connect(self._pokaz_analize)
        self.analiza.stan_pracy_zmieniony.connect(self._aktualizuj_dostepnosc)
        self.analiza.limit_kontekstu.connect(self._pokaz_limit_kontekstu)
        self.analiza.sugestie_zatwierdzone.connect(self._zastosuj_sugestie)
        self.analiza.wzorzec_odswiezony.connect(self._aktualizuj_tekst_propozycji)
        self.analiza.status_zmieniony.connect(self.status_zmieniony)
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
        self._message(self.opis_zaznaczenia, "doc.selection_hint")
        self._aktualizuj_dostepnosc()

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
        self._aktualizuj_podsumowanie(zachowaj_komunikat=True)

        self.hint_listy.setText(t("list.hint"))
        self.btn_odswiez.setText(t("button.refresh"))
        self.odczyt.przetlumacz()
        self.analiza.przetlumacz()
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
            self.analiza.wykryj_wzorzec()

    def _status(self, key: str, **values) -> None:
        self.status_zmieniony.emit(key, values)

    def pracuje(self) -> bool:
        return self.odczyt.pracuje or self.analiza.pracuje

    def zamknij(self) -> None:
        self.odczyt.zamknij()
        self.analiza.zamknij()
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

    @Slot(dict)
    def _zastosuj_sugestie(self, sugestie: dict[str, str]) -> None:
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
        for pole, kontrolka in pola_do_formularza.items():
            if pole in sugestie:
                kontrolka.setText(sugestie[pole])
        if "kategoria_sugerowana" in sugestie:
            nazwa = sugestie["kategoria_sugerowana"]
            identyfikator = next(
                (int(row["id"]) for row in self.rejestr.kategorie()
                 if row["nazwa"] == nazwa), None
            )
            id_kategorii = self.formularz.wybor_kategoria.findData(identyfikator)
            if id_kategorii >= 0:
                self.formularz.wybor_kategoria.setCurrentIndex(id_kategorii)
        self.karty.setCurrentIndex(self.ETAP_EDYCJA)
        self._status("ai.saved_hint")

    @Slot()
    def _aktualizuj_dostepnosc(self) -> None:
        self.odczyt.ustaw_dostepnosc(
            dokument=self.aktualny_dokument_id is not None,
            obszar=self._wybrany_obszar is not None,
            analiza_trwa=self.analiza.pracuje,
        )
        self.analiza.ustaw_wejscie(
            self.aktualny_dokument_id, self.odczyt.tekst, odczyt_trwa=self.odczyt.pracuje,
        )
        pracuje = self.pracuje()
        self.otworz_przycisk.setEnabled(not pracuje)
        self.lista_dokumentow.setEnabled(not pracuje)

    @Slot()
    def _pokaz_analize(self) -> None:
        self.karty.setCurrentIndex(self.ETAP_ANALIZA)

    @Slot()
    def _pokaz_limit_kontekstu(self) -> None:
        self.karty.setCurrentIndex(self.ETAP_ODCZYT)
        self.odczyt.komunikat("ai.context_exceeded")

    @Slot(bool)
    def _start_odczytu(self, tylko_obszar: bool) -> None:
        if self.aktualny_dokument_id is None or self.pracuje():
            return
        obszar = self._wybrany_obszar if tylko_obszar else None
        if tylko_obszar and obszar is None:
            return
        try:
            sciezka = self.rejestr.sciezka_pdf(self.aktualny_dokument_id)
        except (OSError, ValueError) as blad:
            QMessageBox.warning(self.window(), t("msg.pdf"), str(blad))
            return
        self.analiza.wyczysc_wynik()
        self.karty.setCurrentIndex(self.ETAP_ODCZYT)
        self.odczyt.uruchom(sciezka, obszar)

    def _otworz_qr(self) -> None:
        """Odczytaj QR lokalnie, bez zapisu i bez wywołania bankowości."""
        if self.aktualny_dokument_id is None or self.pracuje():
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

    def _aktualizuj_tekst_propozycji(self) -> None:
        existing = self.analiza.ma_aktywny_wzorzec
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
        kategoria = (
            self.formularz.wybor_kategoria.currentText()
            if self.formularz.wybor_kategoria.currentData() is not None else None
        )
        self.analiza.zaproponuj_zapis_wzorca(self.formularz.ed_dostawca.text(), kategoria)

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
        if self.karty.currentIndex() == self.ETAP_ANALIZA:
            self.analiza.wprowadz_kategorie(row["nazwa"])

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
        self.analiza.resetuj_dokument()
        self.formularz.btn_proponuj_wzorzec.hide()
        self.formularz.info_propozycji_wzorca.hide()
        self.odczyt.resetuj_dokument()
        sciezka = self.rejestr.sciezka_pdf(dokument_id)
        # Przy błędzie (np. uszkodzony plik archiwalny) nie pozwalaj zapisywać
        # pól pod niewłaściwym dokumentem.
        self.aktualny_dokument_id = None
        self.formularz.zapisz_przycisk.setEnabled(False)
        self._aktualizuj_dostepnosc()
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
        self._aktualizuj_dostepnosc()
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
        if self.pracuje():
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
            self._aktualizuj_dostepnosc()
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
        self._aktualizuj_dostepnosc()
        if pole is None:
            self._message(self.opis_zaznaczenia, "doc.selection_hint")
            return
        self._message(
            self.opis_zaznaczenia, "doc.selection", page=pole.strona + 1,
            left=pole.lewo, top=pole.gora, right=pole.prawo, bottom=pole.dol
        )
