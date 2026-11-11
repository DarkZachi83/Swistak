# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Kontrola podstawowych odnośników i parametrów README.md."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


class TestReadme(unittest.TestCase):
    def test_banner_jpeg_w_repo(self):
        content = README.read_text(encoding="utf-8")
        match = re.search(r'<img src="([^"]+)"', content)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "assets/branding/swistak-banner.jpeg")
        image = ROOT / match.group(1)
        self.assertTrue(image.is_file())
        self.assertGreater(image.stat().st_size, 100_000)

    def test_lokalne_odnosniki_w_markdown(self):
        content = README.read_text(encoding="utf-8")
        for path in re.findall(r'\]\(([^)]+)\)', content):
            if path.startswith(("https://", "http://", "#")):
                continue
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), path)

    def test_bez_starej_galezi_i_webp(self):
        content = README.read_text(encoding="utf-8")
        self.assertNotIn("git switch experiment/pdfium-ocr", content)
        self.assertNotIn(".webp", content)
        self.assertIn("./uruchom.sh --test", content)
        self.assertIn("PolyForm Noncommercial", content)


if __name__ == "__main__":
    unittest.main()
