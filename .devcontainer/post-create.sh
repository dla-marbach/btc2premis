#!/usr/bin/env bash
# Einrichtung des Dev-Containers: btc2premis samt Entwicklungs- und
# Validierungs-Extras editierbar installieren. Läuft im Image
# mcr.microsoft.com/devcontainers/python:3 (Python ist dort bereits vorhanden).
set -euo pipefail

python3 - <<'PY'
import sys

if sys.version_info < (3, 11):
    sys.exit(
        f"btc2premis benoetigt Python >= 3.11, gefunden: {sys.version.split()[0]}"
    )
PY

python3 -m pip install --upgrade pip
python3 -m pip install -e '.[dev,validate]'

echo "Fertig. Naechste Schritte: 'ruff check .' und 'pytest -q'"
