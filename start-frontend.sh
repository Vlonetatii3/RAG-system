#!/usr/bin/env bash
# Inicia el frontend. La primera vez instala dependencias y copia .env.
set -euo pipefail
cd "$(dirname "$0")/frontend"

command -v npm >/dev/null || { echo "Falta Node.js 18+ (https://nodejs.org)" >&2; exit 1; }
if [ ! -d node_modules ] || [ package-lock.json -nt node_modules ]; then
  echo "Instalando dependencias del frontend..."
  npm install --no-fund --no-audit
  touch node_modules
fi

[ -f .env ] || cp .env.example .env
exec npm run dev
