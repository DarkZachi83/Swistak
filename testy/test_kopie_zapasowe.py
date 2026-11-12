# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Backup danych finansowych — wyłącznie fikcyjne PDF-y i wzorce."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from uslugi.kopie_zapasowe import (
    BladKopii, cofnij_podmiane, podmien_dane, przygotuj_przywracanie,
    utworz_kopie,
)
from uslugi.rachunki import DaneRachunku, RejestrRachunkow
from uslugi.wzorce import MagazynWzorcow, nowy_wzorzec


class TestKopieZapasowe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.root = self.folder / "dane"
        self.db = RejestrRachunkow(self.root)

    def tearDown(self):
        self.db.zamknij()
        self.tmp.cleanup()

    def przygotuj_pdf(self):
        pdf = self.folder / "fikcyjna.pdf"
        data = b"%PDF-1.4\n% TYLKO TEST syntetyczny bez danych klienta\n%%EOF\n"
        pdf.write_bytes(data)
        doc_id, _ = self.db.importuj_pdf(pdf)
        kat = int(self.db.kategorie()[0]["id"])
        self.db.zapisz_rachunek(DaneRachunku(
            dokument_id=doc_id, dostawca="Firma Fikcyjna",
            numer="FAKE/2026/11", kwota="68,99", kategoria_id=kat
        ))
        return doc_id, data

    def przygotuj_wzorzec(self):
        store = MagazynWzorcow(self.root)
        template = store.utworz(nowy_wzorzec(
            "Fikcyjny operator", {"seller_nip": None,
                                  "seller_aliases": ["Fikcyjny operator"],
                                  "layout_labels": ["Faktura"]},
            category="Energia elektryczna",
        ))
        modified = dict(template, agent_notes=["Przykładowa wskazówka"])
        store.aktualizuj(template["template_id"], modified, expected_revision=1)
        return template["template_id"]

    def test_pelna_kopia_odtwarzanie_i_zachowanie_starych_danych(self):
        doc, content = self.przygotuj_pdf()
        template_id = self.przygotuj_wzorzec()
        self.db.dodaj_kategorie("Internet")
        settings = self.folder / "preferences.json"
        settings.write_text('{"language":"pl","ollama_model":"gemma3:4b"}')
        archive = self.folder / "bezpieczna-kopia.zip"
        info = utworz_kopie(self.db, archive, ustawienia=settings)
        self.assertTrue(archive.exists())
        self.assertEqual(info.dokumenty_pdf, 1)
        self.assertEqual(info.wzorce_json, 2)  # aktywny + historyczna rewizja
        self.assertTrue(info.ustawienia)
        self.assertGreater(info.bajty, 0)
        self.assertEqual(self.db.rachunek(doc)["kwota_grosze"], 6899)

        # Po utworzeniu kopii zmieniają się dane bieżące.
        self.db.dodaj_kategorie("Telewizja kablowa")
        self.assertIn("Telewizja kablowa",
                      [v["nazwa"] for v in self.db.kategorie()])
        prepared = przygotuj_przywracanie(archive, self.root)
        self.assertEqual(prepared.opis.dokumenty_pdf, 1)
        self.assertEqual(prepared.ustawienia["ollama_model"], "gemma3:4b")
        try:
            self.db.zamknij()
            previous = podmien_dane(prepared, self.root)
            self.db.__init__(self.root)
            self.assertTrue(previous.is_dir())
            previous_db = sqlite3.connect(previous / "swistak.sqlite3")
            try:
                previous_names = [
                    row[0] for row in previous_db.execute("SELECT nazwa FROM kategorie")
                ]
            finally:
                previous_db.close()
            self.assertIn("Telewizja kablowa", previous_names)
            self.assertNotIn("Telewizja kablowa",
                             [v["nazwa"] for v in self.db.kategorie()])
            self.assertEqual(self.db.rachunek(doc)["kwota_grosze"], 6899)
            self.assertEqual(self.db.sciezka_pdf(doc).read_bytes(), content)
            self.assertEqual(MagazynWzorcow(self.root).pobierz(
                template_id)["revision"], 2)
            self.assertTrue(list((self.root / "wzorce" / "historia").glob("*.json")))
            self.assertEqual(self.db.db.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(self.db.db.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            prepared.sprzataj()

    def test_kopia_nie_nadpisuje_i_nie_moze_byc_wewnatrz_danych(self):
        archive = self.folder / "kopia.zip"
        utworz_kopie(self.db, archive)
        original = archive.read_bytes()
        with self.assertRaises(BladKopii):
            utworz_kopie(self.db, archive)
        self.assertEqual(archive.read_bytes(), original)
        with self.assertRaises(BladKopii):
            utworz_kopie(self.db, self.root / "zabroniona.zip")

    def test_uszkodzony_manifest_lub_pdf_nie_dotyka_bazy(self):
        doc, data = self.przygotuj_pdf()
        archive = self.folder / "oryginal.zip"
        utworz_kopie(self.db, archive)
        corrupted = self.folder / "zepsuty.zip"
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(corrupted, "w") as dest:
            for file in source.infolist():
                if file.filename == "manifest.json":
                    dest.writestr(file.filename, b'{"format":"niepoprawny"}')
                else:
                    dest.writestr(file.filename, source.read(file.filename))
        with self.assertRaises(BladKopii):
            przygotuj_przywracanie(corrupted, self.root)
        self.assertEqual(self.db.sciezka_pdf(doc).read_bytes(), data)
        self.assertEqual(self.db.rachunek(doc)["kwota_grosze"], 6899)

        # PDF o zmienionych bajtach z oryginalnym manifestem jest odrzucany.
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(corrupted, "w") as dest:
            for file in source.infolist():
                contents = source.read(file.filename)
                if file.filename.endswith(".pdf"):
                    contents = b"PRZYPADKOWE ZMIANY W PDF"
                dest.writestr(file.filename, contents)
        with self.assertRaises(BladKopii):
            przygotuj_przywracanie(corrupted, self.root)
        self.assertEqual(self.db.sciezka_pdf(doc).read_bytes(), data)

    def test_niebezpieczne_sciezki_z_archiwum_sa_odrzucane(self):
        archive = self.folder / "zly.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("../prywatne.txt", "Nie wolno wypakować")
            z.writestr("manifest.json", json.dumps({
                "format": "swistak-backup", "version": 1,
                "created_utc": "2026-11-12T12:00:00Z",
                "files": [{"path": "../prywatne.txt", "size": 20,
                           "sha256": "0" * 64}],
            }))
        with self.assertRaises(BladKopii):
            przygotuj_przywracanie(archive, self.root)
        self.assertFalse((self.folder / "prywatne.txt").exists())

    def test_rollback_po_samym_przelaczeniu_katalogu(self):
        doc, data = self.przygotuj_pdf()
        archive = self.folder / "kopia.zip"
        utworz_kopie(self.db, archive)
        prepared = przygotuj_przywracanie(archive, self.root)
        try:
            self.db.zamknij()
            previous = podmien_dane(prepared, self.root)
            cofnij_podmiane(self.root, previous)
            self.db.__init__(self.root)
            self.assertEqual(self.db.rachunek(doc)["kwota_grosze"], 6899)
            self.assertEqual(self.db.sciezka_pdf(doc).read_bytes(), data)
        finally:
            prepared.sprzataj()

    def test_po_przerwaniu_przelaczenia_katalog_wraca_na_miejsce(self):
        doc, data = self.przygotuj_pdf()
        archive = self.folder / "kopia.zip"
        utworz_kopie(self.db, archive)
        prepared = przygotuj_przywracanie(archive, self.root)
        try:
            self.db.zamknij()
            from uslugi.kopie_zapasowe import os as backups_os
            real_replace = backups_os.replace

            def przerwij_drugi_krok(src, dst):
                if Path(src) == prepared.katalog_danych:
                    raise OSError("symulowana awaria podczas przywracania")
                return real_replace(src, dst)

            with patch("uslugi.kopie_zapasowe.os.replace",
                       side_effect=przerwij_drugi_krok):
                with self.assertRaises(OSError):
                    podmien_dane(prepared, self.root)
            self.db.__init__(self.root)
            self.assertEqual(self.db.rachunek(doc)["kwota_grosze"], 6899)
            self.assertEqual(self.db.sciezka_pdf(doc).read_bytes(), data)
        finally:
            prepared.sprzataj()

    def test_brak_glownego_katalogu_z_poprzednim_nie_tworzy_pustej_bazy(self):
        # Tak może wyglądać stan po nagłym wyłączeniu między rename(2).
        missing = self.folder / "inna-baza"
        old = self.folder / "inna-baza-przed-przywroceniem-20261112-123000"
        old.mkdir()
        with self.assertRaisesRegex(RuntimeError, "przerwane przywracanie"):
            RejestrRachunkow(missing)
        self.assertFalse(missing.exists())

    def test_reject_symlink_inside_document_folder(self):
        link = self.root / "dokumenty" / "wyciek.pdf"
        external = self.folder / "poza.pdf"
        external.write_bytes(b"POZA KATALOGIEM")
        try:
            link.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink nie jest dostępny")
        with self.assertRaises(BladKopii):
            utworz_kopie(self.db, self.folder / "zabroniona.zip")
        self.assertFalse((self.folder / "zabroniona.zip").exists())


if __name__ == "__main__":
    unittest.main()
