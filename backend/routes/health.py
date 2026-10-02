"""Endpoint de salud del sistema."""
from flask import Blueprint, current_app, jsonify

from services.ollama_service import OllamaService
from utils.validators import now_iso

health_bp = Blueprint("health", __name__, url_prefix="/api")


@health_bp.get("/health")
def health():
    services = current_app.extensions["rag"]
    config = services["config"]

    db_ok = services["db"].check()
    try:
        models = services["ollama"].list_models()  # una sola llamada a Ollama
        ollama_ok = True
    except Exception:
        models, ollama_ok = [], False

    return jsonify(
        {
            "status": "healthy" if db_ok and ollama_ok else "unhealthy",
            "database": "connected" if db_ok else "error",
            "ollama": "connected" if ollama_ok else "disconnected",
            "model": config.OLLAMA_MODEL,
            "model_available": OllamaService.model_in(config.OLLAMA_MODEL, models),
            "embeddings_model": config.EMBEDDINGS_MODEL,
            "embeddings_model_available": OllamaService.model_in(config.EMBEDDINGS_MODEL, models),
            "timestamp": now_iso(),
        }
    )
