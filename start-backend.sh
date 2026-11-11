#!/usr/bin/env bash
# Inicia el backend. La primera vez crea el venv, instala dependencias y copia .env.
set -euo pipefail
cd "$(dirname "$0")/backend"

PY=$(command -v python3 || command -v python || true)
[ -n "$PY" ] || { echo "Falta Python 3.10+ (https://www.python.org/downloads/)" >&2; exit 1; }

if [ -x venv/Scripts/python.exe ]; then VPY=venv/Scripts/python.exe   # Git Bash en Windows
else
  [ -x venv/bin/python ] || { echo "Creando entorno virtual..."; "$PY" -m venv venv; }
  VPY=venv/bin/python
fi

# Reinstala solo si requirements.txt cambió desde la última instalación
if [ ! -f venv/.installed ] || [ requirements.txt -nt venv/.installed ]; then
  echo "Instalando dependencias del backend..."
  "$VPY" -m pip install -q --disable-pip-version-check -r requirements.txt
  touch venv/.installed
fi

[ -f .env ] || cp .env.example .env
exec "$VPY" app.py
