# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Główna nawigacja Świstaka, pulpit i kreator faktur."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import QEvent, QSignalBlocker, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QProgressBar, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QStyle, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QPlainTextEdit, QTextEdit, QToolButton, QVBoxLayout,
    QWidget, QComboBox, QTabWidget,
)

from gui.okno_o_programie import OknoOProgramie
from gui.podglad_pdf import PodgladPDF
from gui.odczyt_worker import ZadanieOdczytu
from gui.dialog_qr import DialogQR
from gui.analiza_worker import ZadanieAnalizy
from gui.agent_worker import ZadanieMonitora
from gui.panel_agenta import PanelAgenta
from gui.pulpit import Pulpit
from gui.statystyki import Statystyki
from gui.dialog_plan_historia import DialogPlanHistoria
from ai_core.hybrid import AgentLog, MonitorReport
from ai_core.errors import ExtractionContextExceeded
from ai_core.gateway import ToolGateway
from ai_core.hybrid_queue import MonitorJob, MonitorQueue
from uslugi.geometria import Zaznaczenie
from uslugi.odczyt_pdf import WynikOdczytu
from uslugi.analiza_llm import AnalizaModelu, ETYKIETY, POLA, ocena_json
from uslugi.wzorce import MagazynWzorcow
from uslugi.dopasowanie_wzorca import Dopasowanie, dopasuj, zaproponuj_wzorzec
from uslugi.propozycja_wzorca import zaproponuj_aktualizacje
from gui.dialog_wzorca import zaakceptuj_wzorzec
from gui.dialog_modele_lokalne import DialogModeleLokalne
from gui.ustawienia import Ustawienia
from gui.dialog_kategorie import DialogKategorie
from gui.operacje_danych import OperacjeDanych
from gui.zapis_faktury import zapisz_z_potwierdzeniem
from gui.okno_wzorcow import OknoWzorcow
from gui.tabela_faktur import TabelaFaktur
from gui.ikony import ikona_nawigacji
from gui.uklad import Siatka
from uslugi.finanse import DataPlatnosciZPrzyszlosci, sprawdz_date_platnosci
from uslugi.rachunki import (
    BrakDatyOplacenia, BrakDatyWystawienia, DaneRachunku, RejestrRachunkow,
    grosze_na_kwote,
)
from i18n import LANGUAGES, category_name, current_language, set_language, system_language, t
import ustawienia


class _StanFormularza(NamedTuple):
    dostawca: str
    numer: str
    numer_konta: str
    kwota: str
    kategoria_id: int | None
    wystawiono: str
    termin: str
    okres_od: str
    okres_do: str
    status: str
    uwagi: str
    oplacono: str


class OknoGlowne(QMainWindow):
    """Pulpit rachunków i zachowany proces OCR → AI → korekta → faktura."""

    ETAP_ODCZYT = 0
    ETAP_ANALIZA = 1
    ETAP_EDYCJA = 2
    ETAP_FAKTURA = 3
    ETAP_DOKUMENTY = 4
    ETAPY = ("tab.read", "tab.ai", "tab.edit", "tab.bill", "tab.documents")

    def __init__(self, rejestr: RejestrRachunkow):
        super().__init__()
        self.rejestr = rejestr
        self.operacje_danych = OperacjeDanych(self)
        self.magazyn_wzorcow = MagazynWzorcow(rejestr.katalog)
        self._dopasowanie_wzorca: Dopasowanie | None = None
        self._aktywny_wzorzec: dict | None = None
        self._wzorzec_pominiety = False
        self._tekst_dopasowania = ""
        self._wzorzec_dokument_id: int | None = None
        self._komentarze_wzorca: dict[str, str] = {}
        self.prefs = ustawienia.load()
        set_language(self.prefs["language"])
        self._messages: dict[object, tuple[str, dict]] = {}
        self._status_message: tuple[str, dict] | None = None
        self.aktualny_dokument_id: int | None = None
        self._zapisany_formularz: _StanFormularza | None = None
        self._wybrany_obszar: Zaznaczenie | None = None
        self._zadanie_odczytu: ZadanieOdczytu | None = None
        self._zadanie_ai: ZadanieAnalizy | None = None
        self._analiza: AnalizaModelu | None = None
        self._analiza_dokument_id: int | None = None
        self._aktualizuje_tabele_ai = False
        self._pola_potwierdzone_recznie: set[str] = set()
        self._agent_log = AgentLog()
        self._agent_queue = MonitorQueue()
        self._agent_task: ZadanieMonitora | None = None
        self._agent_current_job: MonitorJob | None = None
        self._agent_report: MonitorReport | None = None
        self._agent_closed = False
        self._agent_startup_scheduled = False
        self._agent_status_key = "agent.state.waiting"
        self._agent_timer = QTimer(self)
        self._agent_timer.setSingleShot(True)
        self._agent_timer.timeout.connect(lambda: self._agent_submit("startup"))
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
        self.kreator = QScrollArea()
        self.kreator.setFrameShape(QFrame.Shape.NoFrame)
        self.kreator.setWidgetResizable(True)
        self.moduly.addWidget(self.kreator)
        tresc_kreatora = QWidget()
        self.kreator.setWidget(tresc_kreatora)
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
        self.karty.addWidget(self._zbuduj_formularz())
        self.karty.addWidget(self._zbuduj_fakture())
        self.karty.addWidget(self._zbuduj_liste())
        self.tabela_faktur = TabelaFaktur(self.rejestr)
        self.tabela_faktur.otworz_dokument.connect(self._otworz_fakture_z_tabeli)
        self.moduly.addWidget(self.tabela_faktur)
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
        self._status("msg.status")
        self._aktualizuj_nawigacje(0, 0)
        self._wyczysc_formularz()
        self._message(self.info_odczytu, "read.start")
        self._message(self.info_ai, "ai.start")
        self._message(self.opis_zaznaczenia, "doc.selection_hint")
        self._aktualizuj_odczyt()
        self.plan_historia = DialogPlanHistoria(self.rejestr, embedded=True)
        self.plan_historia.daneZmienione.connect(self._plan_financial_change)
        self.plan_historia.otworz_dokument.connect(self._otworz_fakture_z_tabeli)
        self.moduly.addWidget(self.plan_historia)

        self._agent_panel = PanelAgenta(embedded=True)
        self._agent_panel.manualRequested.connect(lambda: self._agent_submit("manual"))
        self._agent_panel.cancelRequested.connect(self._agent_cancel)
        self._agent_panel.otworz_fakture.connect(self._otworz_fakture_agenta)
        self.moduly.addWidget(self._agent_panel)
        self._agent_refresh_panel()

        self.ustawienia = Ustawienia(self.rejestr.katalog, self._zastosuj_ustawienia)
        self.ustawienia.btn_wzorce.clicked.connect(self._open_patterns_manager)
        self.ustawienia.wczytaj(self.prefs, self.ed_model.text())
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
        if not self._agent_startup_scheduled and not self._agent_closed:
            self._agent_startup_scheduled = True
            # Po pokazaniu okna, nigdy nie blokuj jego inicjalizacji.
            self._agent_timer.start(1200)

    def _agent_set_status(self, key: str) -> None:
        self._agent_status_key = key
        self.pulpit.aktualizuj_agenta(key, self._agent_report)

    def _agent_refresh_panel(self) -> None:
        self._agent_panel.update_content(
            self._agent_report, self._agent_log.text(),
            self._agent_task is not None,
        )

    def _agent_show_panel(self) -> None:
        self._agent_refresh_panel()
        self._pokaz_modul("agent", self._agent_panel)

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
        self._otworz_fakture_z_tabeli(faktura["dokument_id"])

    def _open_plan_historia(self, *, historia: bool = False, cykl: str = "") -> None:
        modul = "history" if historia else "plan"
        self.plan_historia.pokaz(modul, cykl)
        self._pokaz_modul(modul, self.plan_historia)

    def _plan_financial_change(self, invoice_id) -> None:
        # Płatności/profil/plan zaktualizowano transakcyjnie. Natychmiast
        # odśwież istniejące ekrany, następnie analizę w tle.
        self._odswiez_liste()
        if self.aktualny_dokument_id is not None and isinstance(invoice_id, int):
            faktura = self.rejestr.rachunek(self.aktualny_dokument_id)
            if faktura is not None and faktura["id"] == invoice_id:
                zapisany = self._zapisany_formularz
                status = faktura["status"]
                oplacono = faktura["data_oplacenia"] or ""
                if zapisany is not None and (
                    status != zapisany.status or oplacono != zapisany.oplacono
                ):
                    self._wczytaj_stan_platnosci(faktura)
                    self._zapisany_formularz = zapisany._replace(status=status, oplacono=oplacono)
                self.zapisz_przycisk.setEnabled(faktura["wycofano_utc"] is None)
        self._aktualizuj_podsumowanie()
        if isinstance(invoice_id, int) and not isinstance(invoice_id, bool):
            self._agent_submit("change", invoice_id)
        else:
            self._agent_submit("manual")

    def _agent_submit(self, mode: str, invoice_id: int | None = None) -> None:
        if self._agent_closed:
            return
        if mode == "manual":
            # Nie uruchamiaj ponownie kontroli startowej tuż po zakończeniu
            # pełnej analizy ręcznej.
            self._agent_timer.stop()
        job = MonitorJob(mode, invoice_id)
        # Nawet jeśli użytkownik ręcznie uruchamia analizę, tylko jego
        # świadomy zapis formularza może zmieniać SQLite.
        if mode == "change":
            self._agent_report = None
            self.pulpit.aktualizuj_agenta(self._agent_status_key, None)
            self._agent_refresh_panel()
        if self._agent_current_job == job:
            return
        if self._agent_queue.add(job):
            self._agent_log.append(mode, "queued", invoice_id)
        if mode == "manual" and self._agent_task is not None:
            # Ręczne polecenie ma pierwszeństwo przed długim LLM w tle.
            if self._agent_current_job and self._agent_current_job.mode != "manual":
                self._agent_task.anuluj()
        self._agent_dispatch()
        self._agent_refresh_panel()

    def _agent_dispatch(self) -> None:
        if self._agent_closed or self._agent_task is not None:
            return
        job = self._agent_queue.take()
        if job is None:
            self._agent_set_status("agent.state.ready")
            self._agent_refresh_panel()
            return
        model = self.ed_model.text().strip() or self.prefs.get("ollama_model", "gemma3:4b")
        worker = ZadanieMonitora(
            self.rejestr.katalog / "swistak.sqlite3",
            model, job, locale=current_language(),
            specialists=ustawienia.modele_specjalistyczne(self.prefs),
        )
        self._agent_task = worker
        self._agent_current_job = job
        self._agent_log.append(job.mode, "started", job.invoice_id)
        self._agent_set_status("agent.state.working")
        worker.sygnaly.etap.connect(self._agent_progress)
        worker.sygnaly.gotowe.connect(self._agent_completed)
        worker.sygnaly.blad.connect(self._agent_error)
        worker.sygnaly.anulowano.connect(self._agent_cancelled)
        QThreadPool.globalInstance().start(worker)

    def _agent_progress(self, stage: str) -> None:
        if self._agent_closed:
            return
        if stage in {"local", "health", "llm"}:
            job = self._agent_current_job
            if job is not None:
                event = {
                    "local": "local_check",
                    "health": "model_check",
                    "llm": "model_run",
                }[stage]
                self._agent_log.append(job.mode, event, job.invoice_id)
            self._agent_set_status("agent.state." + stage)
            self._agent_refresh_panel()

    def _agent_finish(self, state: str, report: MonitorReport | None = None) -> None:
        if self._agent_closed:
            return
        job = self._agent_current_job
        self._agent_task = None
        self._agent_current_job = None
        if job is not None:
            self._agent_log.append(job.mode, state, job.invoice_id)
        if report is not None:
            self._agent_report = report
        if state == "error":
            self._agent_set_status("agent.state.error")
        elif state == "cancelled":
            self._agent_set_status("agent.state.cancelled")
        elif report is not None:
            self._agent_set_status({
                "local_only": "agent.state.offline",
                "model_idle": "agent.state.model_idle",
                "model_no_tools": "agent.state.model_no_tools",
                "model_ready": "agent.state.ready",
                "model_error": "agent.state.model_error",
            }[report.model_status])
        else:
            self._agent_set_status("agent.state.ready")
        self._agent_refresh_panel()
        # Jedno zadanie na raz: następne startuje dopiero po zakończeniu
        # poprzedniego. Użytkownik może je anulować w dowolnym momencie.
        if len(self._agent_queue):
            self._agent_dispatch()

    def _agent_completed(self, report: MonitorReport) -> None:
        event = {"model_ready": "ai_done", "local_only": "offline"}.get(
            report.model_status, report.model_status
        )
        self._agent_finish(event, report)

    def _agent_error(self, _code: str) -> None:
        self._agent_finish("error")

    def _agent_cancelled(self) -> None:
        self._agent_finish("cancelled")

    def _agent_cancel(self) -> None:
        self._agent_queue.clear()
        if self._agent_task is not None:
            self._agent_task.anuluj()
        self._agent_refresh_panel()

    # UI localization is done IN PLACE: no destruction of the current PDF,
    # input widgets, list selection, OCR output or AI suggestions.
    _FORM_KEYS = (
        "form.supplier", "form.invoice", "form.account", "form.amount",
        "form.category", "form.issued", "form.due", "form.period_from",
        "form.period_to", "form.status", "form.paid_date", "form.notes",
    )
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

    def _localize_categories(self) -> None:
        # Only display labels change. IDs and DB names remain untouched.
        by_id = {int(row["id"]): row["nazwa"] for row in self.rejestr.kategorie()}
        for i in range(1, self.wybor_kategoria.count()):
            category_id = self.wybor_kategoria.itemData(i)
            original_name = by_id.get(category_id)
            if original_name is not None:
                self.wybor_kategoria.setItemText(i, category_name(original_name))

    def _build_menu(self) -> None:
        menu = self.menuBar()
        menu.setNativeMenuBar(False)  # Linux: menu remains inside app window
        self.menu_pliki = menu.addMenu("")
        self.akcja_import = self.menu_pliki.addAction("", self.wybierz_plik)
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
            "", self._open_patterns_manager
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
        self.prefs = updated
        self.ed_model.setText(name)
        self.ustawienia.wczytaj(self.prefs, name)
        self._status("models.selected", name=name)

    def _zadania_w_toku(self) -> bool:
        return (self._zadanie_odczytu is not None or self._zadanie_ai is not None
                or self._agent_task is not None)

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
        self.prefs = updated
        self.ed_model.setText(updated["ollama_model"])
        return True

    def _open_patterns_manager(self) -> None:
        OknoWzorcow(self, self.magazyn_wzorcow).exec()
        # Menedżer może zmienić/wyłączyć aktywny wzorzec:
        # ponów dopasowanie przed kolejną analizą.
        if self.aktualny_dokument_id is not None:
            self._wykryj_wzorzec(self.pole_odczytu.toPlainText())

    def _about(self) -> None:
        OknoOProgramie(self).exec()

    def _message(self, widget: QLabel, key: str, **values) -> None:
        self._messages[widget] = (key, values)
        widget.setText(t(key, **values))

    def _status(self, key: str, **values) -> None:
        self._status_message = (key, values)
        self.statusBar().showMessage(t(key, **values))

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
        self.pulpit.aktualizuj_agenta(self._agent_status_key, self._agent_report)
        self.btn_panel_agenta.setText(t("agent.open"))
        self._agent_panel.przetlumacz()
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

        self.otworz_przycisk.setText(t("button.import"))
        self.poprzednia.setText(t("button.previous"))
        self.nastepna.setText(t("button.next"))
        self.btn_dopasuj.setText(t("button.fit"))
        self.btn_szerokosc.setText(t("button.fit_width"))
        self.zapisz_przycisk.setText(t("button.save"))
        self.tekst_ostrzezenia_form.setText(t("form.hint"))
        for label, key in zip(self._form_labels, self._FORM_KEYS):
            label.setText(t(key))
        self.ed_konto.setPlaceholderText(t("form.placeholder_account"))
        self.ed_kwota.setPlaceholderText(t("form.placeholder_amount"))
        for field in (self.ed_termin, self.ed_od, self.ed_do):
            field.setPlaceholderText(t("form.placeholder_date"))
        for field in (self.ed_wystawiono, self.ed_oplacono):
            field.setPlaceholderText(t("form.placeholder_required_date"))
        self.ed_uwagi.setPlaceholderText(t("form.placeholder_notes"))
        self.wybor_status.setItemText(0, t("form.status_due"))
        self.wybor_status.setItemText(1, t("form.status_paid"))
        self.wybor_kategoria.setItemText(0, t("form.choose_category"))
        self._localize_categories()
        self.tytul_etapow.setText(t("workflow.title"))
        for index, key in enumerate(self.ETAPY):
            self.nawigacja.item(index).setText(t(key))
            self.nawigacja.item(index).setToolTip(t(key))
        self.btn_przejdz_faktura.setText(t("button.review_invoice"))
        self.btn_powrot_edycja.setText(t("button.back_to_edit"))
        self.tytul_faktury.setText(t("invoice.title"))
        self._aktualizuj_tekst_propozycji()
        for key, label in self.podsumowanie_etykiety.items():
            label.setText(t(key))
        self._aktualizuj_podsumowanie(zachowaj_komunikat=True)

        self.hint_listy.setText(t("list.hint"))
        self.btn_odswiez.setText(t("button.refresh"))
        self.tabela_faktur.przetlumacz()
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
        self.btn_proponuj_wzorzec.setText(t("patterns.propose"))
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
        self.btn_dodaj_kategorie.setToolTip(t("categories.open"))
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
        if self._status_message is not None:
            key, values = self._status_message
            self.statusBar().showMessage(t(key, **values))
        self._aktualizuj_nawigacje(self.podglad.strona, self.podglad.liczba_stron)
        self._odswiez_liste()

    def _zbuduj_formularz(self) -> QWidget:
        przewijanie = QScrollArea()
        przewijanie.setWidgetResizable(True)
        przewijanie.setFrameShape(QFrame.Shape.NoFrame)
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(10, 14, 10, 12)
        uklad.setSpacing(10)
        self.nazwa_dokumentu = QLabel()
        self.nazwa_dokumentu.setWordWrap(True)
        uklad.addWidget(self.nazwa_dokumentu)
        forma = QFormLayout()
        forma.setSpacing(8)

        self.ed_dostawca = QLineEdit()
        self.ed_numer = QLineEdit()
        self.ed_konto = QLineEdit()
        self.ed_kwota = QLineEdit()
        self.ed_wystawiono = QLineEdit()
        self.ed_termin = QLineEdit()
        self.ed_od = QLineEdit()
        self.ed_do = QLineEdit()
        self.wybor_kategoria = QComboBox()
        wybor_i_dodaj = QWidget()
        kategoria_uklad = QHBoxLayout(wybor_i_dodaj)
        kategoria_uklad.setContentsMargins(0, 0, 0, 0)
        kategoria_uklad.addWidget(self.wybor_kategoria, 1)
        dodaj = QPushButton("+")
        self.btn_dodaj_kategorie = dodaj
        dodaj.clicked.connect(self._dodaj_kategorie)
        kategoria_uklad.addWidget(dodaj)

        self.wybor_status = QComboBox()
        self.wybor_status.addItem("", "do_zaplaty")
        self.wybor_status.addItem("", "oplacony")
        self.ed_oplacono = QLineEdit()
        self.ed_oplacono.setEnabled(False)
        self.wybor_status.currentIndexChanged.connect(self._zmiana_statusu_platnosci)
        self.ed_uwagi = QTextEdit()
        self.ed_uwagi.setMaximumHeight(86)

        self._form_labels = []
        for element in (
            self.ed_dostawca,
            self.ed_numer,
            self.ed_konto,
            self.ed_kwota,
            wybor_i_dodaj,
            self.ed_wystawiono,
            self.ed_termin,
            self.ed_od,
            self.ed_do,
            self.wybor_status,
            self.ed_oplacono,
            self.ed_uwagi,
        ):
            etykieta = QLabel()
            forma.addRow(etykieta, element)
            self._form_labels.append(etykieta)
        uklad.addLayout(forma)
        self.btn_przejdz_faktura = QPushButton()
        self.btn_przejdz_faktura.clicked.connect(
            lambda: self.karty.setCurrentIndex(self.ETAP_FAKTURA)
        )
        uklad.addWidget(self.btn_przejdz_faktura)
        komunikat = QLabel()
        self.tekst_ostrzezenia_form = komunikat
        komunikat.setWordWrap(True)
        komunikat.setObjectName("podpowiedz")
        uklad.addWidget(komunikat)
        uklad.addStretch()
        przewijanie.setWidget(panel)
        return przewijanie

    def _zbuduj_fakture(self) -> QWidget:
        """Podsumowanie faktury — osobny, świadomy etap zapisu do SQLite."""
        przewijanie = QScrollArea()
        przewijanie.setWidgetResizable(True)
        przewijanie.setFrameShape(QFrame.Shape.NoFrame)
        panel = QWidget()
        uklad = QVBoxLayout(panel)
        uklad.setContentsMargins(14, 16, 14, 14)
        uklad.setSpacing(12)
        self.tytul_faktury = QLabel()
        self.tytul_faktury.setStyleSheet("font-size: 20px; font-weight: 700;")
        uklad.addWidget(self.tytul_faktury)
        self.info_faktury = QLabel()
        self.info_faktury.setWordWrap(True)
        self.info_faktury.setObjectName("podpowiedz")
        uklad.addWidget(self.info_faktury)

        podsumowanie = QFormLayout()
        podsumowanie.setSpacing(12)
        self.podsumowanie_wartosci = {}
        self.podsumowanie_etykiety = {}
        pola = (
            ("form.supplier", "dostawca"), ("form.invoice", "numer"),
            ("form.account", "konto"), ("form.amount", "kwota"),
            ("form.category", "kategoria"), ("form.issued", "wystawiono"),
            ("form.due", "termin"), ("form.period_from", "od"),
            ("form.period_to", "do"), ("form.status", "status"),
            ("form.paid_date", "oplacono"), ("form.notes", "uwagi"),
        )
        for klucz, pole in pola:
            etykieta = QLabel()
            wartosc = QLabel("—")
            wartosc.setWordWrap(True)
            wartosc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            podsumowanie.addRow(etykieta, wartosc)
            self.podsumowanie_wartosci[pole] = wartosc
            self.podsumowanie_etykiety[klucz] = etykieta
        uklad.addLayout(podsumowanie)

        self.btn_powrot_edycja = QPushButton()
        self.btn_powrot_edycja.clicked.connect(
            lambda: self.karty.setCurrentIndex(self.ETAP_EDYCJA)
        )
        uklad.addWidget(self.btn_powrot_edycja)

        self.zapisz_przycisk = QPushButton()
        self.zapisz_przycisk.setObjectName("zapiszFakture")
        self.zapisz_przycisk.clicked.connect(self._zapisz_rachunek)
        uklad.addWidget(self.zapisz_przycisk)
        self.info_propozycji_wzorca = QLabel()
        self.info_propozycji_wzorca.setWordWrap(True)
        self.info_propozycji_wzorca.setObjectName("podpowiedz")
        self.info_propozycji_wzorca.hide()
        uklad.addWidget(self.info_propozycji_wzorca)
        self.btn_proponuj_wzorzec = QPushButton()
        self.btn_proponuj_wzorzec.clicked.connect(self._zaproponuj_zapis_wzorca)
        self.btn_proponuj_wzorzec.hide()
        uklad.addWidget(self.btn_proponuj_wzorzec)
        uklad.addStretch()
        przewijanie.setWidget(panel)
        return przewijanie

    def _zmieniony_etap(self, indeks: int) -> None:
        if indeks == self.ETAP_FAKTURA:
            self._aktualizuj_podsumowanie()

    def _aktualizuj_podsumowanie(self, *, zachowaj_komunikat: bool = False) -> None:
        """Wartości po korekcie, bez odczytu/zapisu bazy przy zmianie widoku."""
        wartosci = {
            "dostawca": self.ed_dostawca.text(),
            "numer": self.ed_numer.text(),
            "konto": self.ed_konto.text(),
            "kwota": self.ed_kwota.text(),
            "kategoria": self.wybor_kategoria.currentText()
            if self.wybor_kategoria.currentData() is not None else "",
            "wystawiono": self.ed_wystawiono.text(),
            "termin": self.ed_termin.text(),
            "od": self.ed_od.text(),
            "do": self.ed_do.text(),
            "status": self.wybor_status.currentText(),
            "oplacono": self.ed_oplacono.text() if self.ed_oplacono.isEnabled() else "",
            "uwagi": self.ed_uwagi.toPlainText(),
        }
        for pole, wartosc in wartosci.items():
            self.podsumowanie_wartosci[pole].setText(wartosc.strip() or "—")
        if not zachowaj_komunikat or self.info_faktury not in self._messages:
            self._message(
                self.info_faktury,
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
        self.ed_model = QLineEdit(self.prefs.get("ollama_model", "gemma3:4b"))
        self.ed_model.setObjectName("modelOllamaAgent")
        model_wiersz = QHBoxLayout()
        model_wiersz.addWidget(self.ed_model, 1)
        self.btn_szukaj_modeli = QPushButton()
        self.btn_szukaj_modeli.setObjectName("szukajModeliLokalnych")
        self.btn_szukaj_modeli.clicked.connect(self._wybierz_model_lokalny)
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
        self.btn_panel_agenta.clicked.connect(self._agent_show_panel)
        agent_uklad.addWidget(self.btn_panel_agenta)

        self.zakladki_ai.addTab(self.karta_ai_dane, "")
        self.zakladki_ai.addTab(self.karta_ai_agent, "")
        return panel

    def _pokaz_info_ai(self) -> None:
        """Pełna instrukcja dostępna pod INFO, bez zabierania miejsca tabeli."""
        QMessageBox.information(
            self, t("ai.info_title"),
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
            self, t("ai.manual_title"),
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
                self, t("ai.manual_title"),
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
        # Analiza żądana przez użytkownika ma pierwszeństwo nad monitorem
        # uruchomionym automatycznie w tle.
        if (self._agent_task is not None and self._agent_current_job is not None
                and self._agent_current_job.mode != "manual"):
            self._agent_task.anuluj()
        if (self._wzorzec_dokument_id != self.aktualny_dokument_id
                or self._tekst_dopasowania != tekst):
            self._wykryj_wzorzec(tekst)
        if (self._dopasowanie_wzorca is not None
                and self._dopasowanie_wzorca.poziom == "suggest"
                and self._aktywny_wzorzec is None and not self._wzorzec_pominiety):
            decyzja = QMessageBox.question(
                self, t("patterns.match_title"),
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
            model_ekstrakcji=self.prefs.get("model_extractor") or None,
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
            QMessageBox.warning(self, t("msg.ai_error"), t(klucz) if za_dlugi else komunikat)
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
            nazwa = oceny["kategoria_sugerowana"].wartosc
            identyfikator = next(
                (int(row["id"]) for row in self.rejestr.kategorie()
                 if row["nazwa"] == nazwa), None
            )
            id_kategorii = self.wybor_kategoria.findData(identyfikator)
            if id_kategorii >= 0:
                self.wybor_kategoria.setCurrentIndex(id_kategorii)
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
            QMessageBox.warning(self, t("msg.pdf"), str(blad))
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
        QMessageBox.warning(self, t("msg.pdf"), komunikat)

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
            dialog = DialogQR(self, pdf)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            platnosc = dialog.wybrana_platnosc
            if platnosc is None:
                return
            # Zgoda w oknie QR dotyczy tylko dwóch pól. Żadnych
            # automatycznych zapisów do SQLite ani operacji bankowych.
            self.ed_kwota.setText(grosze_na_kwote(platnosc.kwota_grosze))
            self.ed_konto.setText(platnosc.numer_konta)
            self.karty.setCurrentIndex(self.ETAP_EDYCJA)
            self._status("qr.applied")
        except (OSError, ValueError, sqlite3.Error) as blad:
            QMessageBox.warning(self, t("qr.title"), str(blad))

    def _anuluj_odczyt(self) -> None:
        if self._zadanie_odczytu is not None:
            self._zadanie_odczytu.przerwij.set()
            self._message(self.info_odczytu, "msg.read_cancelling")

    def closeEvent(self, event) -> None:
        self._agent_closed = True
        self._agent_timer.stop()
        self.ustawienia.anuluj_odswiezanie()
        self._agent_queue.clear()
        if self._agent_task is not None:
            self._agent_task.anuluj()
        if self._zadanie_odczytu is not None:
            self._zadanie_odczytu.przerwij.set()
        if self._zadanie_ai is not None:
            self._zadanie_ai.anuluj()
        self.podglad.zamknij_dokument()
        super().closeEvent(event)

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
            QMessageBox.warning(self, t("patterns.title"), str(error))
            return
        choices = [t("patterns.no_template")] + [
            f"{item['name']} ({item['template_id'][-8:]}, r{item['revision']})"
            for item in templates
        ]
        choice, accepted = QInputDialog.getItem(
            self, t("patterns.choose"), t("patterns.select"), choices, 0, False
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
            QMessageBox.information(self, t("patterns.title"), t("patterns.select_field"))
            return
        pole = POLA[row]
        text, accepted = QInputDialog.getMultiLineText(
            self, t("patterns.field_note"), t("patterns.field_note_help"),
            self._komentarze_wzorca.get(pole, ""),
        )
        if accepted:
            if len(text.strip()) > 450:
                QMessageBox.warning(self, t("patterns.title"), t("patterns.note_too_long"))
                return
            if text.strip():
                self._komentarze_wzorca[pole] = text.strip()
            else:
                self._komentarze_wzorca.pop(pole, None)
            self._odswiez_komentarze_ai()

    def _aktualizuj_tekst_propozycji(self) -> None:
        if not hasattr(self, "btn_proponuj_wzorzec"):
            return
        existing = self._aktywny_wzorzec is not None
        self.btn_proponuj_wzorzec.setText(t(
            "patterns.propose_update" if existing else "patterns.propose"
        ))
        self.info_propozycji_wzorca.setText(t(
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
                self, t("patterns.title"), t("patterns.read_first")
            )
            return
        kategoria = (
            self.wybor_kategoria.currentText()
            if self.wybor_kategoria.currentData() is not None else None
        )
        try:
            candidate = zaproponuj_wzorzec(
                tekst, self.ed_dostawca.text(), kategoria,
                self._komentarze_wzorca, self.notatki_wzorca.toPlainText(),
            )
            original = self._aktywny_wzorzec
            if original is not None:
                proposal = zaproponuj_aktualizacje(original, candidate)
            else:
                proposal = candidate
            # Dialog nie zapisuje niczego; anulowanie pozostawia pliki bez zmian.
            approved = zaakceptuj_wzorzec(
                self, proposal, aktualizacja=original is not None
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
            QMessageBox.warning(self, t("patterns.title"), str(error))

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
        przycisk.clicked.connect(self._odswiez_liste)
        uklad.addWidget(przycisk)
        return panel

    def _odswiez_kategorie(self, wybrana: int | None = None) -> None:
        self.wybor_kategoria.clear()
        self.wybor_kategoria.addItem(t("form.choose_category"), None)
        for wiersz in self.rejestr.kategorie():
            self.wybor_kategoria.addItem(wiersz["nazwa"], int(wiersz["id"]))
        self._localize_categories()
        if wybrana is not None:
            numer = self.wybor_kategoria.findData(wybrana)
            if numer >= 0:
                self.wybor_kategoria.setCurrentIndex(numer)

    def _dodaj_kategorie(self) -> None:
        """Wspólny dialog dla DANE i Edycji: najpierw wybór istniejącej."""
        dialog = DialogKategorie(self.rejestr, self.magazyn_wzorcow, self)
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
            QMessageBox.warning(self, t("categories.title"),
                                t("categories.no_longer_available"))
            return
        self._odswiez_kategorie(selected)
        self.tabela_faktur.odswiez()
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

    def _odswiez_liste(self) -> None:
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
        self.tabela_faktur.odswiez()
        if self.moduly.currentWidget() is self.pulpit:
            self.pulpit.odswiez()
        elif self.moduly.currentWidget() is self.statystyki:
            self.statystyki.odswiez()

    def _zmiana_statusu_platnosci(self) -> None:
        oplacony = self.wybor_status.currentData() == "oplacony"
        self.ed_oplacono.setEnabled(oplacony)

    def _wczytaj_stan_platnosci(self, zapis: sqlite3.Row) -> None:
        with QSignalBlocker(self.wybor_status):
            self.wybor_status.setCurrentIndex(self.wybor_status.findData(zapis["status"]))
        self.ed_oplacono.setEnabled(zapis["status"] == "oplacony")
        self.ed_oplacono.setText(zapis["data_oplacenia"] or "")

    def _wyczysc_formularz(self) -> None:
        self._message(self.nazwa_dokumentu, "doc.import_first")
        for pole in (self.ed_dostawca, self.ed_numer, self.ed_konto, self.ed_kwota, self.ed_wystawiono,
                     self.ed_termin, self.ed_od, self.ed_do):
            pole.clear()
        self.ed_uwagi.clear()
        self.wybor_status.setCurrentIndex(0)
        self.ed_oplacono.clear()
        self._odswiez_kategorie()
        self.zapisz_przycisk.setEnabled(False)

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
        self.btn_proponuj_wzorzec.hide()
        self.info_propozycji_wzorca.hide()
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
        zapis = self.rejestr.rachunek(dokument_id)
        self._wyczysc_formularz()
        self._message(self.nazwa_dokumentu, "doc.original", name=dokument["nazwa_zrodlowa"])
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
            self._wczytaj_stan_platnosci(zapis)
        self.zapisz_przycisk.setEnabled(zapis is None or zapis["wycofano_utc"] is None)
        self._zapisany_formularz = self._stan_formularza()
        self._aktualizuj_odczyt()
        self.karty.setCurrentIndex(
            self.ETAP_FAKTURA if zapis is not None else self.ETAP_ODCZYT
        )
        self._status("msg.opened", name=dokument["nazwa_zrodlowa"])

    def _otworz_fakture_z_tabeli(self, dokument_id: int) -> None:
        if dokument_id == self.aktualny_dokument_id:
            self._pokaz_kreator()
            self.karty.setCurrentIndex(self.ETAP_FAKTURA)
            return
        if not self._zgoda_na_zmiane_dokumentu():
            return
        try:
            self._wyswietl_dokument(dokument_id)
            self._pokaz_kreator()
        except (ValueError, OSError, sqlite3.Error) as blad:
            QMessageBox.warning(self, t("msg.document_open_error"), str(blad))

    def _wybierz_z_listy(self, element: QListWidgetItem) -> None:
        dokument_id = int(element.data(Qt.ItemDataRole.UserRole))
        if dokument_id != self.aktualny_dokument_id:
            self._otworz_fakture_z_tabeli(dokument_id)

    def _stan_formularza(self) -> _StanFormularza:
        return _StanFormularza(
            dostawca=self.ed_dostawca.text(),
            numer=self.ed_numer.text(),
            numer_konta=self.ed_konto.text(),
            kwota=self.ed_kwota.text(),
            kategoria_id=self.wybor_kategoria.currentData(),
            wystawiono=self.ed_wystawiono.text(),
            termin=self.ed_termin.text(),
            okres_od=self.ed_od.text(),
            okres_do=self.ed_do.text(),
            status=self.wybor_status.currentData(),
            uwagi=self.ed_uwagi.toPlainText(),
            oplacono=self.ed_oplacono.text(),
        )

    def _zgoda_na_zmiane_dokumentu(self) -> bool:
        if self._zadanie_odczytu is not None or self._zadanie_ai is not None:
            QMessageBox.information(self, t("nav.new_invoice"), t("invoice.document_busy"))
            return False
        if self.aktualny_dokument_id is None or self._stan_formularza() == self._zapisany_formularz:
            return True
        return QMessageBox.question(
            self, t("nav.new_invoice"), t("invoice.leave_draft"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def podglad_dopasuj(self) -> None:
        self.podglad.dopasuj()

    def wybierz_plik(self) -> None:
        sciezka, _ = QFileDialog.getOpenFileName(
            self, t("msg.import_dialog"), "", t("msg.pdf_filter")
        )
        if sciezka:
            self.otworz_pdf(sciezka)

    def otworz_pdf(self, sciezka: str | Path) -> None:
        if not self._zgoda_na_zmiane_dokumentu():
            return
        try:
            # Zweryfikuj PDF w Qt przed dodaniem go do archiwum i bazy.
            self.aktualny_dokument_id = None
            self.zapisz_przycisk.setEnabled(False)
            self.podglad.otworz(sciezka)
            dokument_id, czy_nowy = self.rejestr.importuj_pdf(sciezka)
            self._wyswietl_dokument(dokument_id)
            self._pokaz_kreator()
            self._odswiez_liste()
            if not czy_nowy:
                self._status("msg.duplicate")
        except (OSError, ValueError, sqlite3.Error) as blad:
            QMessageBox.warning(self, t("msg.document_import_error"), str(blad))

    def _zapisz_rachunek(self) -> None:
        if self.aktualny_dokument_id is None:
            return
        try:
            formularz = self._stan_formularza()
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
                    self, t("payment.confirm_title"),
                    t("payment.before_issue", paid=data_oplacenia, issued=wystawiono),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if odpowiedz != QMessageBox.StandardButton.Yes:
                    self.karty.setCurrentIndex(self.ETAP_EDYCJA)
                    self.ed_oplacono.setFocus()
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
            zapisany_id = zapisz_z_potwierdzeniem(self, self.rejestr, dane)
            if zapisany_id is None:
                self._status("invoice.overwrite_cancelled")
                return
            self._wczytaj_stan_platnosci(self.rejestr.rachunek(self.aktualny_dokument_id))
            self._zapisany_formularz = self._stan_formularza()
            self._agent_submit("change", zapisany_id)
            self._odswiez_liste()
            self._aktualizuj_podsumowanie()
            self.btn_proponuj_wzorzec.show()
            self.info_propozycji_wzorca.show()
            self._aktualizuj_tekst_propozycji()
            self._message(self.info_faktury, "invoice.saved")
            self._status("msg.saved")
        except DataPlatnosciZPrzyszlosci:
            QMessageBox.warning(self, t("msg.bill_save_error"), t("payment.future"))
            self.karty.setCurrentIndex(self.ETAP_EDYCJA)
            self.ed_oplacono.setFocus()
        except (BrakDatyWystawienia, BrakDatyOplacenia) as blad:
            wystawienia = isinstance(blad, BrakDatyWystawienia)
            klucz = "form.issued_required" if wystawienia else "form.paid_date_required"
            pole = self.ed_wystawiono if wystawienia else self.ed_oplacono
            QMessageBox.warning(self, t("msg.bill_save_error"), t(klucz))
            self.karty.setCurrentIndex(self.ETAP_EDYCJA)
            pole.setFocus()
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
