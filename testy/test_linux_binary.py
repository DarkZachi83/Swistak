# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Bezpieczny manifest pakowania binarnego, bez odpalania PyInstaller."""
from __future__ import annotations

import sys
import tempfile
import tarfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tools.build_linux_binary as binary
from wersja import __version__


class TestLinuxBinary(unittest.TestCase):
    def test_nazwa_z_wersji(self):
        self.assertEqual(binary.ARCHIVE_NAME, f"swistak-linux-{__version__}-bin.tar.gz")

    @unittest.skipUnless(sys.platform == "linux", "Pakiet tylko Linux")
    def test_spec_uwzglednia_baze_jezyki_jpeg_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            cmd = binary.pyinstaller_command(work / "dist", work / "build", work / "spec")
            self.assertIn("--onedir", cmd)
            self.assertNotIn("--onefile", cmd)
            self.assertIn("--collect-all=pypdfium2_raw", cmd)
            self.assertIn("--hidden-import=PySide6.QtPdf", cmd)
            text = " ".join(cmd)
            self.assertIn("assets/branding/swistak-banner.jpeg", text)
            self.assertIn("baza/schemat", text)
            self.assertIn("i18n/pl.json", text)
            self.assertIn("i18n/en.json", text)
            self.assertNotIn("swistak.sqlite3", text)
            self.assertNotIn(".webp", text)
            self.assertNotIn("dokumenty/", text)

    def test_archiwum_nie_miesza_innych_katalogow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "Swistak"
            fake.mkdir()
            (fake / "Swistak").write_bytes(b"ELF-test")
            (fake / "VERSION").write_text(__version__, encoding="utf-8")
            (root / "rachunki.sqlite3").write_bytes(b"PRIVATE")
            (root / "rachunek.pdf").write_bytes(b"PRIVATE")
            archive = binary.package_bundle(fake, root / "out")
            with tarfile.open(archive, "r:gz") as tar:
                names = {item.name for item in tar.getmembers()}
            self.assertIn(binary.ARCHIVE_ROOT + "/Swistak", names)
            self.assertIn(binary.ARCHIVE_ROOT + "/VERSION", names)
            self.assertFalse(any(x.endswith(".sqlite3") or x.endswith(".pdf")
                                 for x in names))

    def test_nie_kopiujemy_zwyklych_katalogow_prywatnych(self):
        self.assertFalse(binary._is_license_path(Path("data/rachunki.sqlite3")))
        self.assertFalse(binary._is_license_path(Path("assets/branding/baner.jpeg")))
        self.assertTrue(binary._is_license_path(Path("pypdfium2_raw/BUILD_LICENSES/pdfium.txt")))
        self.assertTrue(binary._is_license_path(Path("PySide6-6.10.dist-info/licenses/LICENSE.LGPL3")))
        

if __name__ == "__main__":
    unittest.main()
