# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Regresja podglądu PDF: biały papier, szerokość panelu i zoom."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication

from gui.podglad_pdf import PodgladPDF


class TestPodgladPDF(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _pdf(folder: Path) -> Path:
        path = folder / "syntetyczny.pdf"
        writer = QPdfWriter(str(path))
        writer.setResolution(72)
        painter = QPainter(writer)
        if not painter.isActive():
            raise RuntimeError("Nie można utworzyć syntetycznego PDF")
        painter.drawText(80, 100, "Syntetyczna faktura testowa")
        painter.end()
        return path

    def test_opaque_white_and_default_fit_width(self):
        with tempfile.TemporaryDirectory() as tmp:
            viewer = PodgladPDF()
            viewer.resize(920, 580)
            viewer.show()
            self.app.processEvents()
            viewer.otworz(self._pdf(Path(tmp)))
            self.app.processEvents()

            image = viewer._obraz.pixmap().toImage()
            self.assertFalse(image.isNull())
            corner = image.pixelColor(15, 15)
            self.assertEqual((corner.red(), corner.green(), corner.blue()),
                             (255, 255, 255))
            self.assertEqual(corner.alpha(), 255)
            self.assertGreater(image.width(), 1200)

            # Zamiast miniaturowej pełnej strony: szerokość prawie całego panelu.
            document_screen_width = (
                viewer._obraz.boundingRect().width() * viewer.transform().m11()
            )
            self.assertGreater(document_screen_width, viewer.viewport().width() * 0.85)
            self.assertLessEqual(document_screen_width, viewer.viewport().width())
            self.assertGreater(viewer.verticalScrollBar().maximum(), 0)
            self.assertEqual(viewer._tryb_dopasowania, "szerokosc")
            viewer.close()

    def test_fit_page_zoom_and_resize(self):
        with tempfile.TemporaryDirectory() as tmp:
            viewer = PodgladPDF()
            viewer.resize(850, 590)
            viewer.show()
            self.app.processEvents()
            viewer.otworz(self._pdf(Path(tmp)))
            self.app.processEvents()

            width_scale = viewer.transform().m11()
            viewer.dopasuj()
            page_scale = viewer.transform().m11()
            self.assertLess(page_scale, width_scale)
            self.assertEqual(viewer._tryb_dopasowania, "strona")
            viewer.powieksz(1.25)
            self.assertGreater(viewer.transform().m11(), page_scale)
            self.assertIsNone(viewer._tryb_dopasowania)

            viewer.dopasuj_szerokosc()
            scale_before = viewer.transform().m11()
            viewer.resize(1030, 590)
            self.app.processEvents()
            self.assertGreater(viewer.transform().m11(), scale_before)
            self.assertEqual(viewer._tryb_dopasowania, "szerokosc")
            viewer.close()

    def test_przelaczenie_strony_nie_zmienia_oryginalu_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = self._pdf(Path(tmp))
            before = pdf.read_bytes()
            viewer = PodgladPDF()
            viewer.resize(900, 600)
            viewer.show()
            self.app.processEvents()
            viewer.otworz(pdf)
            viewer.dopasuj()
            viewer.powieksz(1.25)
            viewer.dopasuj_szerokosc()
            self.assertEqual(pdf.read_bytes(), before)
            self.assertEqual(viewer.strona, 0)
            viewer.close()


if __name__ == "__main__":
    unittest.main()
