# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Odkrywanie modeli: tylko fikcyjne lokalne manifesty i symulowane API."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from uslugi.modele_lokalne import (
    BladOllama, modele_na_dysku, modele_ollama, znane_lokalizacje,
)


class TestWykrywanieModeli(unittest.TestCase):
    def test_lista_modeli_z_lokalnej_ollamy(self):
        payload = json.dumps({"models": [
            {"name": "gemma3:4b", "details": {"family": "gemma3"}},
            {"name": "qwen3:8b", "details": {"family": "qwen3"}},
            {"name": "nomic-embed-text:latest", "details": {"family": "nomic-bert"}},
            {"name": "gemma3:4b", "details": {"family": "gemma3"}},
        ]}).encode()
        with patch("uslugi.modele_lokalne.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = payload
            names = modele_ollama()
            self.assertEqual(names, ["gemma3:4b", "qwen3:8b"])
            address = opener.return_value.open.call_args.args[0]
            self.assertEqual(address.full_url, "http://127.0.0.1:11434/api/tags")
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 4)

    def test_odmowa_uszkodzonego_api(self):
        with patch("uslugi.modele_lokalne.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b"{nonsense"
            with self.assertRaises(BladOllama):
                modele_ollama()

    def test_magazyn_ollama_i_gguf_na_dysku(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = root / "ollama-models"
            manifest = store / "manifests" / "registry.ollama.ai" / "library" / "gemma3" / "4b"
            manifest.parent.mkdir(parents=True)
            blob = store / "blobs" / ("sha256-" + "a" * 64)
            blob.parent.mkdir()
            blob.write_bytes(b"GGUF" + bytes(10))
            manifest.write_text(json.dumps({"layers": [
                {"mediaType": "application/vnd.ollama.image.model",
                 "digest": "sha256:" + "a" * 64, "size": 100}
            ]}), encoding="utf-8")
            lmstudio = root / "lmstudio"
            (lmstudio / "provider").mkdir(parents=True)
            (lmstudio / "provider" / "local-demo.gguf").write_bytes(b"GGUF" + bytes(10))
            (lmstudio / "provider" / "not-a-model.gguf").write_bytes(b"BAD!")
            disk = modele_na_dysku(lokalizacje=[
                ("Ollama", store), ("LM Studio", lmstudio)
            ])
            self.assertEqual([(x.program, x.nazwa) for x in disk], [
                ("LM Studio", "local-demo"), ("Ollama", "gemma3:4b"),
            ])
            blob.unlink()  # manifest bez wag nie jest lokalnie pobranym modelem
            self.assertEqual(
                [(x.program, x.nazwa) for x in modele_na_dysku(
                    lokalizacje=[("Ollama", store)])], [],
            )

    def test_znane_katalogi_wedlug_srodowiska(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath(".ollama", "models").mkdir(parents=True)
            custom = root / "niestandardowy-ollama"
            custom.mkdir()
            locs = znane_lokalizacje(
                home=root, env={"OLLAMA_MODELS": str(custom)},
                platform="linux",
            )
            self.assertIn(("Ollama", custom), locs)
            self.assertIn(("Ollama", root / ".ollama" / "models"), locs)


if __name__ == "__main__":
    unittest.main()
