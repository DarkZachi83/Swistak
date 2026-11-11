# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Lokalny menedżer wzorców: formularz, dezaktywacja i historia rewizji."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout,
)

from gui.dialog_wzorca import zaakceptuj_wzorzec
from i18n import t
from uslugi.wzorce import MagazynWzorcow


class OknoWzorcow(QDialog):
    def __init__(self, parent, magazyn: MagazynWzorcow):
        super().__init__(parent)
        self.magazyn = magazyn
        self.setWindowTitle(t("patterns.manage"))
        self.resize(780, 440)
        layout = QVBoxLayout(self)
        opis = QLabel(t("patterns.manage_help"))
        opis.setWordWrap(True)
        layout.addWidget(opis)

        self.lista = QListWidget()
        self.lista.setObjectName("listaWzorcow")
        self.lista.currentRowChanged.connect(self._aktualizuj_przyciski)
        self.lista.itemDoubleClicked.connect(lambda _: self._edytuj())
        layout.addWidget(self.lista, 1)

        buttons = QHBoxLayout()
        self.edytuj = QPushButton(t("patterns.manage_edit"))
        self.edytuj.clicked.connect(self._edytuj)
        buttons.addWidget(self.edytuj)
        self.zmien_status = QPushButton(t("patterns.manage_toggle"))
        self.zmien_status.clicked.connect(self._zmien_status)
        buttons.addWidget(self.zmien_status)
        self.przywroc = QPushButton(t("patterns.manage_restore"))
        self.przywroc.clicked.connect(self._przywroc)
        buttons.addWidget(self.przywroc)
        layout.addLayout(buttons)

        close = QPushButton(t("patterns.manage_close"))
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self._odswiez()

    def _odswiez(self, wybrane_id: str | None = None) -> None:
        self.lista.clear()
        try:
            all_templates = self.magazyn.lista()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, t("patterns.title"), str(exc))
            all_templates = []
        for item in all_templates:
            label = t(
                "patterns.manage_item",
                name=item["name"], revision=item["revision"],
                status=t(
                    "patterns.form.active"
                    if item["status"] == "approved" else "patterns.form.inactive"
                )
            )
            row = QListWidgetItem(label)
            row.setData(Qt.ItemDataRole.UserRole, item["template_id"])
            self.lista.addItem(row)
            if item["template_id"] == wybrane_id:
                self.lista.setCurrentItem(row)
        if self.lista.currentRow() < 0 and self.lista.count() > 0:
            self.lista.setCurrentRow(0)
        self._aktualizuj_przyciski()

    def _aktualizuj_przyciski(self, *args) -> None:
        enabled = self.lista.currentItem() is not None
        for button in (self.edytuj, self.zmien_status, self.przywroc):
            button.setEnabled(enabled)

    def _selected(self) -> dict | None:
        selected = self.lista.currentItem()
        if selected is None:
            return None
        return self.magazyn.pobierz(selected.data(Qt.ItemDataRole.UserRole))

    def _edytuj(self) -> None:
        try:
            original = self._selected()
            if original is None:
                return
            approved = zaakceptuj_wzorzec(self, original, aktualizacja=True)
            if approved is None:
                return
            saved = self.magazyn.aktualizuj(
                original["template_id"], approved,
                expected_revision=original["revision"]
            )
            self._odswiez(saved["template_id"])
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, t("patterns.title"), str(exc))

    def _zmien_status(self) -> None:
        try:
            original = self._selected()
            if original is None:
                return
            target = (
                "inactive" if original["status"] == "approved" else "approved"
            )
            confirmation = QMessageBox.question(
                self, t("patterns.title"),
                t("patterns.manage_status_confirm", name=original["name"],
                  status=t(
                      "patterns.form.inactive" if target == "inactive"
                      else "patterns.form.active"
                  )),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirmation != QMessageBox.StandardButton.Yes:
                return
            changed = dict(original, status=target)
            saved = self.magazyn.aktualizuj(
                original["template_id"], changed,
                expected_revision=original["revision"],
            )
            self._odswiez(saved["template_id"])
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, t("patterns.title"), str(exc))

    def _przywroc(self) -> None:
        try:
            original = self._selected()
            if original is None:
                return
            history = self.magazyn.katalog / "historia"
            revisions = sorted(
                (int(item.stem.rsplit(".rev-", 1)[1]) for item in
                 history.glob(original["template_id"] + ".rev-*.json")
                 if not item.is_symlink()),
                reverse=True,
            )
            if not revisions:
                QMessageBox.information(
                    self, t("patterns.title"), t("patterns.manage_no_history")
                )
                return
            choices = [str(value) for value in revisions]
            chosen, ok = QInputDialog.getItem(
                self, t("patterns.manage_restore"),
                t("patterns.manage_which_revision"),
                choices, 0, False,
            )
            if not ok:
                return
            confirmation = QMessageBox.question(
                self, t("patterns.title"),
                t("patterns.manage_restore_confirm", revision=chosen,
                  name=original["name"]),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirmation != QMessageBox.StandardButton.Yes:
                return
            saved = self.magazyn.przywroc(
                original["template_id"], int(chosen),
                expected_revision=original["revision"],
            )
            self._odswiez(saved["template_id"])
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, t("patterns.title"), str(exc))
