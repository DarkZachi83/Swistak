# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Spójna ciemna paleta inspirowana interfejsem AI Bobra."""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


TLO = "#212529"
PANEL = "#2b3035"
TEKST = "#e9ecef"
WYGASZONY = "#a3a9b1"
AKCENT = "#3fa66b"
ZAZNACZENIE = "#4fa3e3"


def ustaw_motyw(aplikacja: QApplication) -> None:
    aplikacja.setStyle("Fusion")
    paleta = QPalette()
    paleta.setColor(QPalette.ColorRole.Window, QColor(TLO))
    paleta.setColor(QPalette.ColorRole.WindowText, QColor(TEKST))
    paleta.setColor(QPalette.ColorRole.Base, QColor(PANEL))
    paleta.setColor(QPalette.ColorRole.AlternateBase, QColor(TLO))
    paleta.setColor(QPalette.ColorRole.Text, QColor(TEKST))
    paleta.setColor(QPalette.ColorRole.Button, QColor(PANEL))
    paleta.setColor(QPalette.ColorRole.ButtonText, QColor(TEKST))
    paleta.setColor(QPalette.ColorRole.Highlight, QColor(ZAZNACZENIE))
    paleta.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    aplikacja.setPalette(paleta)
    aplikacja.setStyleSheet("""
        QMainWindow, QWidget { background: #212529; color: #e9ecef; }
        QFrame#pasek { background: #2b3035; border-radius: 8px; }
        QPushButton { background: #353b41; border: 1px solid #45484b;
                      border-radius: 6px; padding: 8px 12px; }
        QPushButton:hover { background: #414a51; }
        QPushButton:pressed { background: #4e5860; }
        QPushButton:disabled { color: #a3a9b1; background: #2b3035; }
        QPushButton:focus { border-color: #4fa3e3; }
        QLabel#naglowek { font-size: 19px; font-weight: 700; }
        QLabel#podpowiedz { color: #a3a9b1; }
        QFrame#menuBoczne, QFrame#pulpitKarta {
            background: #2b3035; border: 1px solid #383e44; border-radius: 8px;
        }
        QFrame#menuBoczne QLabel, QFrame#pulpitKarta QLabel { background: transparent; }
        QFrame#menuBoczne QLabel { padding-left: 10px; }
        QFrame#menuBoczne QToolButton {
            text-align: left; background: transparent; border: 1px solid transparent;
            border-radius: 6px; padding: 5px 8px;
        }
        QFrame#menuBoczne QToolButton:hover:enabled { background: #414a51; }
        QFrame#menuBoczne QToolButton:checked { background: #305643; color: #f0fff5; }
        QFrame#menuBoczne QToolButton:focus { border-color: #4fa3e3; }
        QFrame#etapyPanel { background: #292e33; border-radius: 8px; }
        QListWidget#etapyMenu { background: transparent; border: none; color: #e4e7e9; }
        QListWidget#etapyMenu::item { padding: 9px 8px; margin: 2px; border-radius: 5px; }
        QListWidget#etapyMenu::item:selected { background: #305643; color: #f0fff5; }
        QListWidget#etapyMenu::item:hover:!selected { background: #3a4248; }
        QFrame#etapyPanel QLabel, QFrame#pasek QWidget { background: transparent; }
        QFrame#pasek QPushButton { background: #353b41; }
        QFrame#pasek QPushButton:hover:enabled { background: #414a51; }
        QFrame#pasek QPushButton:disabled { background: #2b3035; }
        QScrollBar:vertical, QScrollBar:horizontal { background: #212529; border: none; }
        QScrollBar:vertical { width: 11px; }
        QScrollBar:horizontal { height: 11px; }
        QScrollBar::handle { background: #59636d; border-radius: 4px; min-height: 23px; min-width: 23px; }
        QScrollBar::handle:hover { background: #77838e; }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
        QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
        QLabel#pulpitTytul { font-size: 27px; font-weight: 700; }
        QLabel#pulpitSekcja { font-size: 16px; font-weight: 700; }
        QLabel#pulpitWartosc { font-size: 22px; font-weight: 700; }
        QProgressBar#slupekStatystyk {
            background: #292e33; border: 0; border-radius: 3px; max-height: 12px;
            margin: 0 8px;
        }
        QProgressBar#slupekStatystyk::chunk { background: #3fa66b; border-radius: 3px; }
        QGraphicsView { background: #171b1f; border: 1px solid #45484b;
                        border-radius: 8px; }
        QStatusBar { background: #2b3035; }
        QMenuBar { background: #2b3035; color: #e9ecef;
                   padding: 2px 5px; border-bottom: 1px solid #45484b; }
        QMenuBar::item { padding: 5px 13px; border-radius: 4px; }
        QMenuBar::item:selected { background: #414a51; }
        QMenu { background: #2b3035; color: #e9ecef;
                border: 1px solid #45484b; padding: 5px; }
        QMenu::item { padding: 7px 28px 7px 18px; }
        QMenu::item:selected { background: #414a51; }
        QMenu::separator { background: #45484b; height: 1px; margin: 4px; }
        QDialog { background: #212529; }

    """)
