#!/usr/bin/env bash
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Instalacja wyłącznie w prywatnym katalogu aplikacji. Bez sudo.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")" && pwd -P)"
cd -- "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Świstak: brak python3. Zainstaluj Python 3.11+ i python3-venv." >&2
    exit 2
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "Świstak: wymagany Python 3.11 lub nowszy." >&2
    exit 2
fi

echo "Świstak Beta — konfiguracja lokalnego środowiska."
echo "Zależności Python zostaną pobrane z indeksu pakietów przez pip."
echo "Nie są pobierane modele AI ani dokumenty użytkownika."
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    python3 -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
echo "Gotowe. Uruchom: ./start.sh --test"
echo "Do rozpoznawania skanów zainstaluj systemowy Tesseract + pol/eng."
