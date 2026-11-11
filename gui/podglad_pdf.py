# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Podgląd PDF, zoom i zaznaczanie prostokąta bez odczytu OCR (etap 0)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QBrush, QImage, QPainter, QPen, QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
)

from uslugi.geometria import Zaznaczenie, ogranicz, zaznaczenie_z_pikseli


class PodgladPDF(QGraphicsView):
    zaznaczono = Signal(object)  # Zaznaczenie | None
    zmiana_strony = Signal(int, int)  # indeks od zera, liczba stron

    def __init__(self, rodzic=None):
        super().__init__(rodzic)
        self._pdf = QPdfDocument(self)
        self._scena = QGraphicsScene(self)
        self.setScene(self._scena)
        self._obraz = QGraphicsPixmapItem()
        self._scena.addItem(self._obraz)
        self._prostokat = QGraphicsRectItem()
        self._prostokat.setZValue(2)
        self._prostokat.setBrush(QBrush(QColor(79, 163, 227, 60)))
        self._prostokat.setPen(QPen(QColor(79, 163, 227), 2))
        self._prostokat.hide()
        self._scena.addItem(self._prostokat)
        self._start: QPointF | None = None
        self._strona = 0
        self._zoom = 1.0  # mnożnik względem ostatniego dopasowania
        self._tryb_dopasowania = "szerokosc"
        # Biały papier pozostaje niezależny od ciemnego motywu aplikacji.
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.RenderHint.Antialiasing |
                            QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    @property
    def liczba_stron(self) -> int:
        return self._pdf.pageCount()

    @property
    def strona(self) -> int:
        return self._strona

    def otworz(self, sciezka: str | Path) -> None:
        sciezka = Path(sciezka).expanduser()
        if not sciezka.is_file():
            raise FileNotFoundError(f"Nie znaleziono dokumentu: {sciezka}")
        self._pdf.close()
        self._obraz.setPixmap(QPixmap())
        self._prostokat.hide()
        self.zaznaczono.emit(None)
        self._pdf.load(str(sciezka))
        if self._pdf.status() != QPdfDocument.Status.Ready or self._pdf.pageCount() < 1:
            raise ValueError("Nie można wczytać PDF (uszkodzony lub zabezpieczony hasłem).")
        self.pokaz_strone(0)

    def pokaz_strone(self, numer: int) -> None:
        if not (0 <= numer < self.liczba_stron):
            return
        rozmiar = self._pdf.pagePointSize(numer)
        # Wyższa rozdzielczość pomaga zachować ostrość po powiększeniu.
        # Limit 3200 px po dłuższym boku ogranicza zużycie pamięci.
        skala = min(3.0, 3200.0 / max(1.0, rozmiar.width(), rozmiar.height()))
        szer = max(1, round(rozmiar.width() * skala))
        wys = max(1, round(rozmiar.height() * skala))
        obraz = self._pdf.render(numer, QSize(szer, wys))
        if obraz.isNull():
            raise ValueError(f"Nie udało się wyrenderować strony {numer + 1}")

        # Qt PDF może zwrócić obraz z przezroczystym tłem. Na ciemnym motywie
        # czarny tekst staje się wtedy niemal niewidoczny. Renderujemy więc
        # nieprzezroczysty biały papier, NIE zmieniając oryginalnego pliku PDF.
        papier = QImage(szer, wys, QImage.Format.Format_RGB32)
        papier.fill(Qt.GlobalColor.white)
        malarz = QPainter(papier)
        try:
            malarz.drawImage(0, 0, obraz)
        finally:
            malarz.end()

        self._strona = numer
        self._start = None
        self._prostokat.hide()
        self._obraz.setPixmap(QPixmap.fromImage(papier))
        self._scena.setSceneRect(QRectF(0, 0, szer, wys))
        self.dopasuj_szerokosc()
        self.zaznaczono.emit(None)
        self.zmiana_strony.emit(numer, self.liczba_stron)

    def _dopasuj_szerokosc(self, *, od_poczatku: bool) -> None:
        if self._obraz.pixmap().isNull():
            return
        poprzednia_pozycja = self.verticalScrollBar().value()
        self._tryb_dopasowania = "szerokosc"
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.resetTransform()
        szerokosc = self._obraz.boundingRect().width()
        dostepna = max(1, self.viewport().width() - 24)
        self.scale(dostepna / max(1, szerokosc), dostepna / max(1, szerokosc))
        self._zoom = 1.0
        self.verticalScrollBar().setValue(
            0 if od_poczatku else poprzednia_pozycja
        )

    def dopasuj_szerokosc(self) -> None:
        """Czytelna strona zajmuje szerokość panelu; wysokość można przewijać."""
        self._dopasuj_szerokosc(od_poczatku=True)

    def dopasuj(self) -> None:
        """Cała strona w panelu (alternatywa dla czytelnego widoku szerokości)."""
        if self._obraz.pixmap().isNull():
            return
        self._tryb_dopasowania = "strona"
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.resetTransform()
        self.fitInView(self._obraz, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = 1.0

    def powieksz(self, mnoznik: float) -> None:
        if self._obraz.pixmap().isNull():
            return
        docelowy = max(0.5, min(8.0, self._zoom * mnoznik))
        skala = docelowy / self._zoom
        self._tryb_dopasowania = None
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scale(skala, skala)
        self._zoom = docelowy

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._tryb_dopasowania == "szerokosc":
            self._dopasuj_szerokosc(od_poczatku=False)
        elif self._tryb_dopasowania == "strona":
            self.dopasuj()

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.powieksz(1.25 if event.angleDelta().y() > 0 else 0.8)
            event.accept()
            return
        super().wheelEvent(event)

    def _punkt_w_stronie(self, pozycja: QPointF) -> QPointF:
        obraz = self._obraz.pixmap()
        return QPointF(ogranicz(pozycja.x(), obraz.width()),
                       ogranicz(pozycja.y(), obraz.height()))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._obraz.pixmap().isNull():
            pozycja = self.mapToScene(event.position().toPoint())
            if self._obraz.boundingRect().contains(pozycja):
                self._start = pozycja
                self._prostokat.setRect(QRectF(pozycja, pozycja))
                self._prostokat.show()
                self.zaznaczono.emit(None)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._start is not None:
            punkt = self._punkt_w_stronie(self.mapToScene(event.position().toPoint()))
            self._prostokat.setRect(QRectF(self._start, punkt).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._start is not None:
            obraz = self._obraz.pixmap()
            koniec = self._punkt_w_stronie(self.mapToScene(event.position().toPoint()))
            zaznaczenie: Zaznaczenie | None = zaznaczenie_z_pikseli(
                self._strona,
                (self._start.x(), self._start.y()),
                (koniec.x(), koniec.y()),
                obraz.width(), obraz.height(),
            )
            self._start = None
            if zaznaczenie is None:
                self._prostokat.hide()
            self.zaznaczono.emit(zaznaczenie)
            event.accept()
            return
        super().mouseReleaseEvent(event)
