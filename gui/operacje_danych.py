# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Dialogi kopii, przywracania i czyszczenia danych Świstaka."""
from __future__ import annotations

import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

import ustawienia
from i18n import t
from uslugi.czyszczenie_bazy import (
    BladCzyszczenia, podmien_na_pusta, przygotuj_pusta_baze, usun_poprzednie_dane,
)
from uslugi.kopie_zapasowe import (
    BladKopii, cofnij_podmiane, podmien_dane, przygotuj_przywracanie, utworz_kopie,
)

if TYPE_CHECKING:
    from gui.okno_glowne import OknoGlowne


class OperacjeDanych:
    def __init__(self, okno: OknoGlowne):
        self.okno = okno

    def _czy_mozna_przywracac(self) -> bool:
        if self.okno._zadania_w_toku():
            QMessageBox.warning(self.okno, t("backup.title"), t("backup.busy"))
            return False
        return True

    def utworz_kopie(self) -> None:
        """Zapisz prywatną, spójną kopię danych bez nadpisania innych kopii."""
        if not self._czy_mozna_przywracac():
            return
        okno = self.okno
        default = Path.home() / (
            "Swistak-kopia-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip"
        )
        path, _ = QFileDialog.getSaveFileName(
            okno, t("backup.create_title"), str(default),
            t("backup.file_filter"),
        )
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        confirmed = QMessageBox.question(
            okno, t("backup.title"), t("backup.private_warning"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            opis = utworz_kopie(
                okno.rejestr, path, ustawienia=ustawienia.path_settings()
            )
        except (BladKopii, OSError, sqlite3.Error, ValueError) as exc:
            QMessageBox.warning(okno, t("backup.title"),
                                t("backup.create_error", error=str(exc)))
        else:
            QMessageBox.information(
                okno, t("backup.title"),
                t("backup.created", path=str(path), pdf=opis.dokumenty_pdf,
                  templates=opis.wzorce_json),
            )
        finally:
            QApplication.restoreOverrideCursor()

    def przywroc_kopie(self) -> None:
        """Sprawdź kopię przed potwierdzeniem i zachowaj oryginał do cofnięcia."""
        if not self._czy_mozna_przywracac():
            return
        okno = self.okno
        path, _ = QFileDialog.getOpenFileName(
            okno, t("backup.restore_title"), str(Path.home()),
            t("backup.file_filter"),
        )
        if not path:
            return
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            kopia = przygotuj_przywracanie(path, okno.rejestr.katalog)
        except (BladKopii, OSError, sqlite3.Error, ValueError, zipfile.BadZipFile) as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(okno, t("backup.title"),
                                t("backup.restore_invalid", error=str(exc)))
            return
        QApplication.restoreOverrideCursor()
        try:
            answer = QMessageBox.question(
                okno, t("backup.restore_title"),
                t("backup.restore_confirm",
                  date=kopia.opis.utworzona_utc,
                  pdf=kopia.opis.dokumenty_pdf,
                  templates=kopia.opis.wzorce_json),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            folder = okno.rejestr.katalog
            original_prefs = ustawienia.load()
            previous = None
            new_window = None
            # Windows: PDFium i SQLite nie mogą trzymać otwartych uchwytów
            # podczas zmiany nazwy katalogu danych.
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            try:
                okno.kreator.podglad.zamknij_dokument()
                okno.rejestr.zamknij()
                previous = podmien_dane(kopia, folder)
                okno.rejestr.otworz_ponownie()
                if kopia.ustawienia is not None:
                    ustawienia.save({**original_prefs, **kopia.ustawienia})
                new_window = type(okno)(okno.rejestr)
            except Exception as exc:
                if new_window is not None:
                    new_window.close()
                try:
                    okno.rejestr.zamknij()
                except sqlite3.Error:
                    pass
                try:
                    if previous is not None:
                        cofnij_podmiane(folder, previous)
                    okno.rejestr.otworz_ponownie()
                    ustawienia.save(original_prefs)
                    okno._odswiez_liste()
                except Exception as rollback:
                    QMessageBox.critical(
                        okno, t("backup.title"),
                        t("backup.restore_critical",
                          error=str(exc), rollback=str(rollback)),
                    )
                    return
                QMessageBox.warning(
                    okno, t("backup.title"),
                    t("backup.restore_error", error=str(exc)),
                )
                return
            finally:
                QApplication.restoreOverrideCursor()
            # Stare okno trzeba ukryć PRZED pokazaniem nowego.
            # Modalny komunikat może uruchomić wewnętrzną pętlę Qt,
            # dlatego nie może pozostawiać dwóch okien na ekranie.
            # RejestrRachunkow nadal pozostaje pod opieką main.py.
            okno._okno_po_przywroceniu = new_window
            self._przelacz_na_nowe_okno(new_window)
            QMessageBox.information(
                new_window, t("backup.title"),
                t("backup.restored", previous=str(previous)),
            )
        finally:
            kopia.sprzataj()

    def wyczysc_baze(self) -> None:
        """Całkowity reset danych aplikacji dopiero po sprawdzonym backupie.

        Kontrole: brak pracy w tle, ostrzeżenie, nowa kopia ZIP poza bazą,
        test przywracania tej kopii, wpisanie frazy i końcowe potwierdzenie.
        """
        if not self._czy_mozna_przywracac():
            return
        okno = self.okno
        answer = QMessageBox.warning(
            okno, t("clear.title"), t("clear.warning"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        default = Path.home() / (
            "Swistak-przed-wyczyszczeniem-"
            + datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip"
        )
        path, _ = QFileDialog.getSaveFileName(
            okno, t("clear.backup_title"), str(default), t("backup.file_filter"),
        )
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"

        # Kopia jest bezwarunkowo obowiązkowa — nie ma przycisku "Pomiń".
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            utworz_kopie(okno.rejestr, path,
                         ustawienia=ustawienia.path_settings())
            przygotuj_przywracanie(path, okno.rejestr.katalog).sprzataj()
        except (BladKopii, OSError, sqlite3.Error, ValueError,
                zipfile.BadZipFile) as exc:
            QMessageBox.warning(okno, t("clear.title"),
                                t("clear.backup_failed", error=str(exc)))
            return
        finally:
            QApplication.restoreOverrideCursor()

        phrase, accepted = QInputDialog.getText(
            okno, t("clear.title"),
            t("clear.type_phrase", phrase=t("clear.phrase")),
        )
        if not accepted or phrase != t("clear.phrase"):
            QMessageBox.information(okno, t("clear.title"),
                                    t("clear.cancelled", path=path))
            return
        answer = QMessageBox.question(
            okno, t("clear.title"),
            t("clear.last_confirm", path=path),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        root = okno.rejestr.katalog
        stage = None
        previous = None
        new_window = None
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            stage = przygotuj_pusta_baze(root)
            okno.kreator.podglad.zamknij_dokument()
            okno.rejestr.zamknij()
            previous = podmien_na_pusta(root, stage)
            stage = None  # nowy folder jest już głównym katalogiem danych
            okno.rejestr.otworz_ponownie()
            new_window = type(okno)(okno.rejestr)
        except Exception as exc:
            if new_window is not None:
                new_window.close()
            if previous is not None:
                try:
                    okno.rejestr.zamknij()
                except sqlite3.Error:
                    pass
            try:
                if previous is not None:
                    cofnij_podmiane(root, previous)
                okno.rejestr.otworz_ponownie()
            except Exception as rollback:
                QMessageBox.critical(
                    okno, t("clear.title"),
                    t("clear.critical", error=str(exc), rollback=str(rollback)),
                )
                return
            QMessageBox.warning(
                okno, t("clear.title"),
                t("clear.failed", error=str(exc)),
            )
            return
        finally:
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)
            QApplication.restoreOverrideCursor()

        # Usuń stare dane dopiero PO poprawnym otwarciu pustej bazy.
        # Jeśli usunięcie się nie powiedzie, poinformuj o zachowanej
        # lokalizacji zamiast fałszywie ogłaszać zakończenie czyszczenia.
        residual = None
        try:
            usun_poprzednie_dane(previous, root)
        except (BladCzyszczenia, OSError) as exc:
            residual = str(exc)

        okno._okno_po_wyczyszczeniu = new_window
        self._przelacz_na_nowe_okno(new_window)
        if residual is not None:
            QMessageBox.warning(
                new_window, t("clear.title"),
                t("clear.partial", previous=str(previous), error=residual,
                  path=path),
            )
        else:
            QMessageBox.information(
                new_window, t("clear.title"),
                t("clear.success", path=path),
            )

    def _przelacz_na_nowe_okno(self, nowe_okno: OknoGlowne) -> None:
        """Bez podwójnego okna: ukryj stare przed pokazaniem nowego.

        Samo hide() nie wywołuje zamknięcia ostatniego okna aplikacji,
        a close() wykonujemy dopiero po wyświetleniu nowego. Jeżeli Qt
        odmówi pokazania nowego okna, ponownie ujawnij poprzednie.
        """
        self.okno.hide()
        try:
            nowe_okno.show()
        except Exception:
            self.okno.show()
            raise
        self.okno.close()
