# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Główna nawigacja Świstaka i połączenia między modułami GUI."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QScrollArea, QSizePolicy, QStackedWidget, QStyle, QToolButton, QVBoxLayout, QWidget,
)

import ustawienia
from ai_core.gateway import ToolGateway
from gui.dialog_modele_lokalne import DialogModeleLokalne
from gui.dialog_plan_historia import DialogPlanHistoria
from gui.ikony import ikona_nawigacji
from gui.kreator_faktury import KreatorFaktury
from gui.monitor_agenta import MonitorAgenta
from gui.okno_o_programie import OknoOProgramie
from gui.operacje_danych import OperacjeDanych
from gui.pulpit import Pulpit
from gui.statystyki import Statystyki
from gui.tabela_faktur import TabelaFaktur
from gui.ustawienia import Ustawienia
from i18n import LANGUAGES, set_language, system_language, t
from uslugi.rachunki import RejestrRachunkow


class OknoGlowne(QMainWindow):
    """Łączy moduły Świstaka, nawigację i ustawienia aplikacji."""

    def __init__(self, rejestr: RejestrRachunkow):
        super().__init__()
        self.rejestr = rejestr
        self.operacje_danych = OperacjeDanych(self)
        self.prefs = ustawienia.load()
        set_language(self.prefs["language"])
        self._status_message: tuple[str, dict] | None = None
        self.setMinimumSize(600, 400)
        ekran = self.screen().availableGeometry()
        self.resize(min(1450, ekran.width() - 48), min(860, ekran.height() - 70))

        centrum = QWidget()
        self.setCentralWidget(centrum)
        uklad = QHBoxLayout(centrum)
        uklad.setContentsMargins(10, 10, 10, 10)
        uklad.setSpacing(10)
        self.menu_boczne = self._zbuduj_menu_boczne()
        uklad.addWidget(self.menu_boczne)

        self.moduly = QStackedWidget()
        uklad.addWidget(self.moduly, 1)
        self.pulpit = Pulpit(self.rejestr)
        self.moduly.addWidget(self.pulpit)
        self.pulpit.pokaz_faktury.connect(self._pokaz_faktury)
        self.pulpit.pokaz_naleznosci.connect(self._pokaz_faktury)
        self.pulpit.pokaz_plan.connect(lambda cykl: self._open_plan_historia(cykl=cykl))
        self.pulpit.pokaz_historie.connect(
            lambda cykl: self._open_plan_historia(historia=True, cykl=cykl)
        )
        self.pulpit.pokaz_agenta.connect(self._agent_show_panel)
        self.pulpit.pokaz_sprawdzana.connect(self._otworz_fakture_agenta)
        self.statystyki = Statystyki(self.rejestr)
        self.moduly.addWidget(self.statystyki)
        self.kreator = KreatorFaktury(self.rejestr, self.prefs)
        self.kreator.pokaz_kreator.connect(self._pokaz_kreator)
        self.kreator.pokaz_agenta.connect(self._agent_show_panel)
        self.kreator.wybor_modelu.connect(self._wybierz_model_lokalny)
        self.kreator.odswiez_dokumenty.connect(self._odswiez_liste)
        self.kreator.faktura_zapisana.connect(self._po_zapisie_faktury)
        self.kreator.status_zmieniony.connect(self._status_kreatora)
        self.moduly.addWidget(self.kreator)
        self.tabela_faktur = TabelaFaktur(self.rejestr)
        self.kreator.kategorie_zmienione.connect(self.tabela_faktur.odswiez)
        self.tabela_faktur.otworz_dokument.connect(self.kreator.otworz_fakture)
        self.moduly.addWidget(self.tabela_faktur)
        self._status("msg.status")
        self.plan_historia = DialogPlanHistoria(self.rejestr, embedded=True)
        self.plan_historia.daneZmienione.connect(self._plan_financial_change)
        self.plan_historia.otworz_dokument.connect(self.kreator.otworz_fakture)
        self.moduly.addWidget(self.plan_historia)

        self.monitor = MonitorAgenta(
            self.rejestr.katalog / "swistak.sqlite3", self.prefs, self,
        )
        self.kreator.ed_model.textChanged.connect(self.monitor.zmien_model)
        self.monitor.status_zmieniony.connect(self.pulpit.aktualizuj_agenta)
        self.monitor.panel.otworz_fakture.connect(self._otworz_fakture_agenta)
        self.kreator.analiza_zadana.connect(self.monitor.przerwij_tlo)
        self.moduly.addWidget(self.monitor.panel)

        self.ustawienia = Ustawienia(self.rejestr.katalog, self._zastosuj_ustawienia)
        self.ustawienia.btn_wzorce.clicked.connect(self.kreator.otworz_menedzer_wzorcow)
        self.ustawienia.wczytaj(self.prefs, self.kreator.ed_model.text())
        self.moduly.addWidget(self.ustawienia)

        self._build_menu()
        self._menu_skroty = []
        for numer, (klucz, przycisk) in enumerate(self.nawigacja_glowna.items(), 1):
            akcja = QAction(self)
            akcja.setShortcut(QKeySequence(f"Alt+{numer}"))
            akcja.triggered.connect(przycisk.click)
            self.addAction(akcja)
            self._menu_skroty.append((klucz, przycisk, akcja))
        self._retranslate_ui()

    def _zbuduj_menu_boczne(self) -> QScrollArea:
        panel = QFrame()
        panel.setObjectName("menuBoczne")
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(9, 14, 9, 9)
        uklad.setSpacing(5)
        self.tytul = QLabel()
        self.tytul.setObjectName("naglowek")
        uklad.addWidget(self.tytul)
        uklad.addSpacing(4)

        self.nawigacja_glowna = {}
        strony = QButtonGroup(panel)
        for klucz, akcja in (
            ("dashboard", self._pokaz_pulpit),
            ("new_invoice", self._pokaz_kreator),
            ("invoices", lambda: self._pokaz_faktury()),
            ("statistics", self._pokaz_statystyki),
            ("plan", self._open_plan_historia),
            ("history", lambda: self._open_plan_historia(historia=True)),
            ("agent", self._agent_show_panel),
            ("settings", self._open_settings),
            ("about", self._about),
        ):
            przycisk = QToolButton()
            przycisk.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            przycisk.setIcon(ikona_nawigacji(klucz, 18))
            przycisk.setIconSize(QSize(18, 18))
            przycisk.setObjectName("otworzPlanHistoria" if klucz == "plan" else "nav_" + klucz)
            przycisk.clicked.connect(akcja)
            if klucz != "about":
                przycisk.setCheckable(True)
                strony.addButton(przycisk)
            self.nawigacja_glowna[klucz] = przycisk
            uklad.addWidget(przycisk)
        self.nawigacja_glowna["dashboard"].setChecked(True)
        self.btn_plan_historia = self.nawigacja_glowna["plan"]
        uklad.addStretch()
        przewijanie = QScrollArea()
        przewijanie.setFrameShape(QFrame.Shape.NoFrame)
        przewijanie.setWidgetResizable(True)
        przewijanie.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        przewijanie.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        przewijanie.setWidget(panel)
        return przewijanie

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_menu_skroty"):
            self._dopasuj_uklad()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            if hasattr(self, "_menu_skroty"):
                self._dopasuj_uklad()

    def _dopasuj_uklad(self) -> None:
        compact = self.width() < 1000
        self.menu_boczne.widget().layout().setSpacing(2 if compact else 5)
        self.menu_boczne.widget().layout().setContentsMargins(9, 5 if compact else 14, 9, 5)
        for przycisk in self.nawigacja_glowna.values():
            przycisk.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly if compact
                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
        self.tytul.setVisible(not compact)
        max_width = max(b.sizeHint().width() for b in self.nawigacja_glowna.values())
        self.menu_boczne.setFixedWidth(max_width + 22 + self.style().pixelMetric(
            QStyle.PixelMetric.PM_ScrollBarExtent
        ))
        width = self.width() - self.menu_boczne.width()
        self.kreator.dopasuj_uklad(width)

    def _pokaz_modul(self, klucz: str, widok: QWidget) -> None:
        self.moduly.setCurrentWidget(widok)
        self.nawigacja_glowna[klucz].setChecked(True)

    def _pokaz_pulpit(self) -> None:
        self._pokaz_modul("dashboard", self.pulpit)
        self.pulpit.odswiez()

    def _pokaz_statystyki(self) -> None:
        self.statystyki.odswiez()
        self._pokaz_modul("statistics", self.statystyki)

    def _pokaz_kreator(self) -> None:
        self._pokaz_modul("new_invoice", self.kreator)

    def _pokaz_faktury(self, termin: str | None = None) -> None:
        if termin:
            self.tabela_faktur.pokaz_naleznosci(termin)
        self.tabela_faktur.odswiez()
        self._pokaz_modul("invoices", self.tabela_faktur)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.monitor.zaplanuj_start()

    def closeEvent(self, event) -> None:
        self.monitor.zamknij()
        self.ustawienia.anuluj_odswiezanie()
        self.kreator.zamknij()
        super().closeEvent(event)

    def _agent_show_panel(self) -> None:
        self.monitor.odswiez_panel()
        self._pokaz_modul("agent", self.monitor.panel)

    def _otworz_fakture_agenta(self, ident: int, rewizja: str) -> None:
        try:
            gateway = ToolGateway(self.rejestr.katalog / "swistak.sqlite3")
            if gateway.revision() != rewizja:
                self._status("agent.stale_invoice")
                return
            faktura = self.rejestr.db.execute(
                "SELECT dokument_id FROM rachunki WHERE id=?", (ident,)
            ).fetchone()
        except (sqlite3.Error, OSError, ValueError):
            self._status("agent.stale_invoice")
            return
        if faktura is None:
            self._status("agent.stale_invoice")
            return
        self.kreator.otworz_fakture(faktura["dokument_id"])

    def _open_plan_historia(self, *, historia: bool = False, cykl: str = "") -> None:
        modul = "history" if historia else "plan"
        self.plan_historia.pokaz(modul, cykl)
        self._pokaz_modul(modul, self.plan_historia)

    def _plan_financial_change(self, invoice_id) -> None:
        # Płatności/profil/plan zaktualizowano transakcyjnie. Natychmiast
        # odśwież istniejące ekrany, następnie analizę w tle.
        self._odswiez_liste()
        self.kreator.odswiez_platnosc(invoice_id)
        if isinstance(invoice_id, int) and not isinstance(invoice_id, bool):
            self.monitor.zlec("change", invoice_id)
        else:
            self.monitor.zlec("manual")

    def _po_zapisie_faktury(self, invoice_id: int) -> None:
        self.monitor.zlec("change", invoice_id)
        self._odswiez_liste()

    def _odswiez_liste(self) -> None:
        self.kreator.odswiez_liste()
        self.tabela_faktur.odswiez()
        if self.moduly.currentWidget() is self.pulpit:
            self.pulpit.odswiez()
        elif self.moduly.currentWidget() is self.statystyki:
            self.statystyki.odswiez()

    def _build_menu(self) -> None:
        menu = self.menuBar()
        menu.setNativeMenuBar(False)  # Linux: menu remains inside app window
        self.menu_pliki = menu.addMenu("")
        self.akcja_import = self.menu_pliki.addAction("", self.kreator.wybierz_plik)
        self.akcja_import.setShortcut(QKeySequence.StandardKey.Open)
        self.akcja_odswiez = self.menu_pliki.addAction("", self._odswiez_liste)
        self.menu_pliki.addSeparator()
        self.akcja_kopia = self.menu_pliki.addAction("", self.operacje_danych.utworz_kopie)
        self.akcja_przywroc = self.menu_pliki.addAction("", self.operacje_danych.przywroc_kopie)
        self.menu_pliki.addSeparator()
        self.akcja_wyczysc = self.menu_pliki.addAction("", self.operacje_danych.wyczysc_baze)
        self.menu_pliki.addSeparator()
        self.akcja_zakoncz = self.menu_pliki.addAction("", self.close)

        self.menu_ustawienia = menu.addMenu("")
        self.akcja_konfiguruj = self.menu_ustawienia.addAction("", self._open_settings)
        self.akcja_wzorce = self.menu_ustawienia.addAction(
            "", self.kreator.otworz_menedzer_wzorcow
        )
        self.menu_ustawienia.addSeparator()
        self.akcja_plan_historia = self.menu_ustawienia.addAction(
            "", self._open_plan_historia
        )

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

    def _wybierz_model_lokalny(self) -> None:
        """Wybór TYLKO modelu gotowego w lokalnej Ollamie.

        Dodatkowy skan dysku jest podglądem, nie próbą uruchomienia
        przypadkowego GGUF przez API Ollamy.
        """
        dialog = DialogModeleLokalne(
            self, katalog_uzytkownika=self.prefs.get("model_scan_dir", "")
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.wybrany_model
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            return
        scan_dir = dialog.katalog_uzytkownika
        updated = dict(
            self.prefs, ollama_model=name,
            model_scan_dir=scan_dir if isinstance(scan_dir, str)
                           else self.prefs.get("model_scan_dir", ""),
        )
        try:
            ustawienia.save(updated)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, t("models.title"),
                                t("settings.save_failed", error=error))
            return
        self._wczytaj_ustawienia_modeli(updated)
        self.ustawienia.wczytaj(self.prefs, name)
        self._status("models.selected", name=name)

    def _open_settings(self) -> None:
        if self.moduly.currentWidget() is not self.ustawienia:
            self.ustawienia.odswiez_modele()
        self._pokaz_modul("settings", self.ustawienia)

    def _zastosuj_ustawienia(self, zmiany: dict) -> bool:
        updated = dict(self.prefs, **zmiany)
        try:
            ustawienia.save(updated)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, t("settings.title"),
                                t("settings.save_failed", error=error))
            return False
        self._wczytaj_ustawienia_modeli(updated)
        return True

    def _wczytaj_ustawienia_modeli(self, prefs: dict[str, str]) -> None:
        self.prefs = prefs
        self.monitor.wczytaj_ustawienia(prefs)
        self.kreator.wczytaj_ustawienia(prefs)

    def _about(self) -> None:
        OknoOProgramie(self).exec()

    def _status(self, key: str, **values) -> None:
        self._status_message = (key, values)
        self.statusBar().showMessage(t(key, **values))

    def _status_kreatora(self, key: str, values: dict) -> None:
        self._status(key, **values)

    def _zadania_w_toku(self) -> bool:
        return self.kreator.pracuje() or self.monitor.pracuje

    def otworz_pdf(self, sciezka: str | Path) -> None:
        self.kreator.otworz_pdf(sciezka)

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(t("app.title"))
        self.tytul.setText(t("app.header"))
        for klucz, przycisk, akcja in self._menu_skroty:
            nazwa = t("nav." + klucz)
            przycisk.setText(nazwa)
            przycisk.setAccessibleName(nazwa)
            przycisk.setToolTip(f"{nazwa} ({akcja.shortcut().toString()})")
            akcja.setText(nazwa)
        self._dopasuj_uklad()
        self.pulpit.przetlumacz()
        self.statystyki.przetlumacz()
        self.pulpit.aktualizuj_agenta(self.monitor.status_key, self.monitor.report)
        self.monitor.panel.przetlumacz()
        self.ustawienia.przetlumacz()
        self.plan_historia.przetlumacz()
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
            (self.akcja_kopia, "backup.menu_create"),
            (self.akcja_przywroc, "backup.menu_restore"),
            (self.akcja_wyczysc, "clear.menu"),
            (self.akcja_zakoncz, "menu.exit"),
            (self.akcja_konfiguruj, "menu.configure"),
            (self.akcja_wzorce, "patterns.manage"),
            (self.akcja_plan_historia, "plan.open"),
            (self.akcja_informacje, "menu.about_dialog"),
        ):
            action.setText(t(key))
        self._lang_actions[""].setText(
            t("language.auto", name=t("language." + system_language()))
        )
        for lang in LANGUAGES:
            self._lang_actions[lang].setText(t("language." + lang))
        self._lang_actions[self.prefs["language"]].setChecked(True)

        self.kreator.przetlumacz()
        self.tabela_faktur.przetlumacz()
        if self._status_message is not None:
            key, values = self._status_message
            self.statusBar().showMessage(t(key, **values))
        self._odswiez_liste()
