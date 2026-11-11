#!/usr/bin/env bash
# Inicia Ollama (si hace falta), backend y frontend. Ctrl+C detiene todo.
set -uo pipefail
cd "$(dirname "$0")"

OLLAMA_URL=${OLLAMA_URL:-http://127.0.0.1:11434}
ollama_up() { curl -sf "$OLLAMA_URL/api/tags" >/dev/null 2>&1; }

if ! command -v ollama >/dev/null; then
  echo "Aviso: Ollama no está instalado (https://ollama.com). La app abrirá, pero no podrá responder." >&2
elif ! ollama_up; then
  echo "Iniciando Ollama..."
  ollama serve >/dev/null 2>&1 &
  for _ in $(seq 20); do ollama_up && break; sleep 0.5; done
fi

if ollama_up; then
  model=$(grep -s '^OLLAMA_MODEL=' backend/.env | cut -d= -f2-); model=${model:-qwen2.5:7b}
  embed=$(grep -s '^EMBEDDINGS_MODEL=' backend/.env | cut -d= -f2-); embed=${embed:-nomic-embed-text}
  tags=$(curl -s "$OLLAMA_URL/api/tags")
  for m in "$model" "$embed"; do
    [[ $m == *:* ]] || m="$m:latest"
    grep -q "\"name\":\"$m\"" <<<"$tags" || echo "Aviso: falta el modelo $m. Ejecuta: ollama pull $m" >&2
  done
fi

trap 'kill 0' EXIT
./start-backend.sh &
./start-frontend.sh &
echo "Backend: http://localhost:5000/api  |  Frontend: http://localhost:5173"
wait
