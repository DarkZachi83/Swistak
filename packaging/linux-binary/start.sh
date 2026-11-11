#!/usr/bin/env bash
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Start samodzielnego pakietu PyInstaller (bez Pythona / pip).
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")" && pwd -P)"
if [[ ! -x "$ROOT/Swistak" ]]; then
    echo "Świstak: brakuje pliku wykonywalnego Swistak obok start.sh." >&2
    exit 2
fi
if [[ "$#" -gt 0 && "$1" == "--test" ]]; then
    VERSION="$(head -n 1 "$ROOT/VERSION")"
    DATA_HOME="$(printenv XDG_DATA_HOME || true)"
    if [[ -z "$DATA_HOME" ]]; then DATA_HOME="$HOME/.local/share"; fi
    export SWISTAK_DATA_DIR="$DATA_HOME/Swistak-Test-Binary-$VERSION"
    echo "Świstak — osobna baza testowa: $SWISTAK_DATA_DIR"
    shift
fi
exec "$ROOT/Swistak" "$@"
