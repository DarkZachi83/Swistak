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
        QPushButton:disabled { color: #737a80; }
        QLabel#naglowek { font-size: 19px; font-weight: 700; }
        QLabel#podpowiedz { color: #a3a9b1; }
        QGraphicsView { background: #171b1f; border: 1px solid #45484b;
                        border-radius: 8px; }
        QStatusBar { background: #2b3035; }
    """)
