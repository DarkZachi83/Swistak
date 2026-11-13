# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Wyszukiwarka modeli w Ustawieniach: Ollama, standardowe i własne katalogi."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog, QPushButton

import ustawienia
from gui.dialog_modele_lokalne import DialogModeleLokalne
from gui.okno_glowne import OknoGlowne
from uslugi.modele_lokalne import lokalizacje_skanowania, modele_na_dysku
from uslugi.rachunki import RejestrRachunkow
from i18n import set_language


class TestCustomModelScan(unittest.TestCase):
    def test_only_selected_folder_finds_gguf_by_header(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            selected=root/"my-models"
            selected.mkdir()
            (selected/"valid.gguf").write_bytes(b"GGUF"+b"\x00"*16)
            (selected/"fake.gguf").write_bytes(b"NOPE"+b"\x00"*16)
            (selected/"nothing.txt").write_text("not a model",encoding="utf-8")
            locations=lokalizacje_skanowania(standardowe=False,dodatkowy=selected)
            self.assertEqual(locations,[("Wskazany katalog",selected)])
            disk=modele_na_dysku(lokalizacje=locations)
            self.assertEqual([(x.nazwa,x.program) for x in disk],
                             [("valid","Wskazany katalog")])
            with self.assertRaises(ValueError):
                lokalizacje_skanowania(standardowe=False,dodatkowy=root/"missing")

    def test_chosen_ollama_store_reads_manifests_not_sha_names(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Path(folder)/"chosen"
            manifest=store/"manifests"/"registry.ollama.ai"/"library"/"demo"/"latest"
            manifest.parent.mkdir(parents=True)
            blob=store/"blobs"/("sha256-"+"a"*64)
            blob.parent.mkdir()
            blob.write_bytes(b"GGUF"+b"\x00"*16)
            manifest.write_text(json.dumps({"layers":[{
                "mediaType":"application/vnd.ollama.image.model",
                "digest":"sha256:"+"a"*64,"size":1000
            }]}),encoding="utf-8")
            roots=lokalizacje_skanowania(standardowe=False,dodatkowy=store)
            self.assertEqual(roots,[("Ollama",store)])
            disk=modele_na_dysku(lokalizacje=roots)
            self.assertEqual([(m.nazwa,m.program) for m in disk],
                             [("demo:latest","Ollama")])

    def test_hugging_face_transformers_safetensors_tylko_podglad(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"hub"
            snapshot=root/"models--example--local-llm"/"snapshots"/"abc"
            snapshot.mkdir(parents=True)
            (snapshot/"config.json").write_text(json.dumps({
                "architectures":["DemoForCausalLM"],"model_type":"demo"
            }))
            (snapshot/"model.safetensors").write_bytes(b"synthetic weights")
            disk=modele_na_dysku(lokalizacje=[("Hugging Face",root)])
            self.assertEqual([(x.nazwa,x.program) for x in disk],
                             [("example/local-llm","Hugging Face")])
            (snapshot/"config.json").write_text(json.dumps({
                "architectures":["DemoForImageClassification"]
            }))
            self.assertEqual(modele_na_dysku(lokalizacje=[("Hugging Face",root)]),[])

    def test_ustawienia_zapis_i_czytanie_starego_pliku(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"settings.json"
            path.write_text(json.dumps({"language":"pl","ollama_model":"gemma3:4b"}))
            self.assertEqual(ustawienia.load(path)["model_scan_dir"],"")
            custom=Path(folder)/"models"
            custom.mkdir()
            ustawienia.save({"language":"en","ollama_model":"qwen3:8b",
                              "model_scan_dir":str(custom)},path)
            loaded=ustawienia.load(path)
            self.assertEqual(loaded["model_scan_dir"],str(custom))
            self.assertEqual(loaded["ollama_model"],"qwen3:8b")
            with self.assertRaises(ValueError):
                ustawienia.save({"language":"pl","ollama_model":"demo",
                                  "model_scan_dir":"abc\nsecret"},path)


class TestModelSettingsGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def tearDown(self):
        set_language("pl")

    def test_dialog_standardowe_i_wskazany_katalog_zadanie_w_tle(self):
        # Patch musi obejmować ponowne skanowanie — nie uruchamiaj
        # prawdziwych skanów katalogów w syntetycznym teście Qt.
        with patch("gui.dialog_modele_lokalne.QThreadPool.globalInstance") as pool:
            dialog=DialogModeleLokalne(katalog_uzytkownika="/tmp/syntetyczny")
            try:
                initial=pool.return_value.start.call_args.args[0]
                self.assertTrue(initial.standardowe)
                self.assertEqual(initial.dodatkowy,"/tmp/syntetyczny")
                dialog._gotowe(["gemma3:4b"],[],"")
                dialog.standardowe.setChecked(False)
                self.assertFalse(dialog.standardowe.isChecked())
                with patch("gui.dialog_modele_lokalne.QFileDialog.getExistingDirectory",
                           return_value="/tmp/modele-testowe"):
                    dialog._wybierz_katalog()
                latest=pool.return_value.start.call_args.args[0]
                self.assertFalse(latest.standardowe)
                self.assertEqual(latest.dodatkowy,"/tmp/modele-testowe")
                self.assertEqual(dialog.katalog_uzytkownika,"/tmp/modele-testowe")
                dialog._gotowe(["gemma3:4b"],[],"")
                dialog.btn_wyczysc_katalog.click()
                latest=pool.return_value.start.call_args.args[0]
                self.assertEqual(latest.dodatkowy,"")
                self.assertEqual(dialog.katalog_uzytkownika,"")
                self.assertEqual(pool.return_value.start.call_count,3)
            finally:
                dialog.close()

    def test_settings_search_list_saves_only_after_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            registry=RejestrRachunkow(root/"dane")
            try:
                with patch.object(ustawienia,"path_settings",
                                  return_value=root/"settings.json"):
                    ustawienia.save({"language":"pl","ollama_model":"gemma3:4b"})
                    win=OknoGlowne(registry)
                    try:
                        scan_dir=str(root/"faked-models")
                        with patch("gui.okno_glowne.DialogModeleLokalne") as picker:
                            picker.return_value.exec.return_value=QDialog.DialogCode.Accepted
                            picker.return_value.wybrany_model="qwen3:8b"
                            picker.return_value.dostepne_modele=["gemma3:4b","qwen3:8b"]
                            picker.return_value.katalog_uzytkownika=scan_dir

                            def open_settings():
                                box=next(w for w in QApplication.topLevelWidgets()
                                         if w.objectName()=="ustawieniaSwistaka")
                                combo=box.findChild(type(win.wybor_kategoria),
                                                    "ustawieniaListaModeli")
                                self.assertTrue(combo.isEditable())
                                self.assertEqual(combo.currentText(),"gemma3:4b")
                                box.findChild(QPushButton,"ustawieniaSzukajLokalnie").click()
                                self.assertEqual(combo.currentText(),"qwen3:8b")
                                self.assertEqual(combo.count(),2)
                                return QDialog.DialogCode.Accepted

                            with patch("gui.okno_glowne.QDialog.exec",
                                       side_effect=open_settings):
                                win._open_settings()
                            self.assertEqual(ustawienia.load()["ollama_model"],"qwen3:8b")
                            self.assertEqual(ustawienia.load()["model_scan_dir"],scan_dir)
                            self.assertEqual(win.ed_model.text(),"qwen3:8b")

                        with patch("gui.okno_glowne.DialogModeleLokalne") as picker:
                            picker.return_value.exec.return_value=QDialog.DialogCode.Accepted
                            picker.return_value.wybrany_model="another:1b"
                            picker.return_value.dostepne_modele=["another:1b"]
                            picker.return_value.katalog_uzytkownika=scan_dir
                            with patch("gui.okno_glowne.QDialog.exec",
                                       side_effect=lambda: QDialog.DialogCode.Rejected):
                                win._open_settings()
                            self.assertEqual(ustawienia.load()["ollama_model"],"qwen3:8b")
                    finally:
                        win.close()
            finally:
                registry.zamknij()


if __name__=="__main__":
    unittest.main()
