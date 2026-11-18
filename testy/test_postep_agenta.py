# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Postęp lokalnej analizy AI: testy na fikcyjnych danych, bez Ollamy i faktur."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

import ustawienia
from testy.pomoc_qt import zamknij_widget
from gui.analiza_worker import ZadanieAnalizy
from gui.okno_glowne import OknoGlowne
from i18n import set_language
from uslugi.analiza_llm import POLA, analizuj_lokalnie
from uslugi.rachunki import RejestrRachunkow


class TestPostepAgenta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        set_language("pl")

    def test_pasek_nie_pokazuje_fikcyjnych_procentow(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = RejestrRachunkow(root / "dane")
            try:
                with patch.object(ustawienia, "path_settings",
                                  return_value=root / "prefs.json"):
                    ustawienia.save({"language": "pl", "ollama_model": "gemma3:4b"})
                    win = OknoGlowne(db)
                    kreator = win.kreator
                    analiza = kreator.analiza
                    win.show()
                    self.app.processEvents()
                    # Pasek należy do karty DANE wewnątrz kreatora faktury.
                    win.nawigacja_glowna["new_invoice"].click()
                    kreator.karty.setCurrentIndex(kreator.ETAP_ANALIZA)
                    analiza.zakladki_ai.setCurrentIndex(0)
                    self.app.processEvents()
                    try:
                        self.assertFalse(analiza.postep_ai.isVisible())
                        self.assertEqual(analiza.postep_ai.objectName(), "postepPracyAgenta")
                        self.assertTrue(analiza.karta_ai_dane.isAncestorOf(analiza.postep_ai))
                        analiza._start_postep_ai()
                        self.assertTrue(analiza.postep_ai.isVisible())
                        self.assertEqual(analiza.postep_ai.minimum(), 0)
                        self.assertEqual(analiza.postep_ai.maximum(), 0)

                        # Etap raportowany z wątku dla odpowiedniego dokumentu.
                        job = ZadanieAnalizy(10, "Fikcyjny tekst", ["Inne"], "gemma3:4b")
                        analiza.ustaw_wejscie(10, "", odczyt_trwa=False)
                        analiza._zadanie_ai = job
                        analiza._etap_postepu_ai(9, "ollama")
                        self.assertNotIn("Ollama (", analiza.info_ai.text())
                        analiza._etap_postepu_ai(10, "ollama")
                        self.assertIn("gemma3:4b", analiza.info_ai.text())
                        analiza._etap_postepu_ai(10, "validate")
                        self.assertIn("Sprawdzanie odpowiedzi", analiza.info_ai.text())

                        # Anulowanie nie pozwala na pozorne przejście do kolejnego etapu.
                        job.przerwij.set()
                        state = analiza.info_ai.text()
                        analiza._etap_postepu_ai(10, "ollama")
                        self.assertEqual(analiza.info_ai.text(), state)

                        analiza._analiza_anulowana(10)
                        self.assertFalse(analiza.postep_ai.isVisible())
                        self.assertEqual(analiza.postep_ai.maximum(), 100)
                        self.assertEqual(analiza.postep_ai.value(), 0)

                        analiza._start_postep_ai()
                        analiza._koniec_postepu_ai(True)
                        self.assertTrue(analiza.postep_ai.isVisible())
                        self.assertEqual(analiza.postep_ai.value(), 100)
                        self.assertEqual(analiza.postep_ai.maximum(), 100)

                        analiza.wyczysc_wynik()
                        self.assertFalse(analiza.postep_ai.isVisible())
                        self.assertEqual(analiza.postep_ai.value(), 0)
                        win.change_language("en")
                        self.assertEqual(analiza.postep_ai.accessibleName(),
                                         "AI agent progress")
                    finally:
                        zamknij_widget(win)
            finally:
                db.zamknij()

    def test_transport_raportuje_istniejace_etapy(self):
        fake_fields = {name: {"wartosc": None, "dowod": None} for name in POLA}
        response = {"message": {"content": json.dumps(fake_fields)}}
        handler = MagicMock()
        handler.open.return_value = io.BytesIO(
            json.dumps(response).encode("utf-8")
        )
        stages = []
        with patch("ai_core.ollama.OllamaProvider.get_capabilities",
                   return_value={"declared": {"context_tokens": None}}), patch("ai_core.ollama.build_opener", return_value=handler):
            result = analizuj_lokalnie(
                "FAKTURA FIKCYJNA. Kwota nieznana.",
                ["Inne"], postep=stages.append,
            )
        self.assertEqual(stages, ["ollama", "validate"])
        self.assertEqual(result.model, "gemma3:4b")



if __name__ == "__main__":
    unittest.main()
