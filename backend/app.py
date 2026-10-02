"""Aplicación Flask del sistema RAG."""
import logging
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from config import Config
from models.database import Database
from routes.chat import chat_bp
from routes.documents import documents_bp
from routes.health import health_bp
from routes.study import study_bp
from routes.subjects import subjects_bp
from services.embeddings import EmbeddingsService
from services.ollama_service import OllamaService
from services.pdf_processor import PDFProcessor
from services.rag import RAGService
from services.study import StudyService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("rag")


def create_app(config=Config, ollama_service=None) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    # Margen de 1MB sobre el límite para el overhead de multipart; el límite exacto se valida en la ruta
    app.config["MAX_CONTENT_LENGTH"] = (config.MAX_UPLOAD_SIZE_MB + 1) * 1024 * 1024
    CORS(app, resources={r"/api/*": {"origins": config.CORS_ORIGINS}})

    db = Database(config.DATABASE_PATH)
    db.init_db()
    # Documentos que quedaron a medias por un reinicio no se van a terminar de procesar
    db.execute(
        "UPDATE documents SET status = 'failed', error = 'Procesamiento interrumpido por reinicio del servidor' "
        "WHERE status = 'processing'"
    )
    db.execute(
        "UPDATE documents SET summary_status = 'failed', summary_progress = NULL, "
        "summary_error = 'Resumen interrumpido por reinicio del servidor' WHERE summary_status = 'processing'"
    )

    ollama = ollama_service or OllamaService(
        config.OLLAMA_BASE_URL,
        config.OLLAMA_MODEL,
        config.OLLAMA_TIMEOUT,
        config.OLLAMA_KEEP_ALIVE,
        config.OLLAMA_NUM_CTX,
    )
    embeddings = EmbeddingsService(ollama, db, config.EMBEDDINGS_MODEL, config.SIMILARITY_THRESHOLD)
    app.extensions["rag"] = {
        "config": config,
        "db": db,
        "ollama": ollama,
        "pdf_processor": PDFProcessor(),
        "embeddings": embeddings,
        "rag_service": RAGService(embeddings, ollama, db),
        "study": StudyService(ollama, embeddings, db),
        "executor": ThreadPoolExecutor(max_workers=2, thread_name_prefix="pdf"),
        # Los resúmenes ocupan la GPU varios minutos: de a uno para no frenar el chat
        "summary_executor": ThreadPoolExecutor(max_workers=1, thread_name_prefix="summary"),
    }

    app.register_blueprint(health_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(subjects_bp)
    app.register_blueprint(study_bp)

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_e):
        return jsonify({"success": False, "error": "Archivo demasiado grande"}), 413

    @app.errorhandler(HTTPException)
    def http_error(e: HTTPException):
        return jsonify({"success": False, "error": e.description or e.name}), e.code

    @app.errorhandler(Exception)
    def unhandled(e: Exception):
        logger.exception("Error no controlado")
        return jsonify({"success": False, "error": "Error interno del servidor"}), 500

    if ollama.check_connection():
        for model in (config.OLLAMA_MODEL, config.EMBEDDINGS_MODEL):
            if not ollama.is_model_available(model):
                logger.warning("Modelo '%s' no descargado. Ejecuta: ollama pull %s", model, model)
    else:
        logger.warning("Ollama no responde en %s. Ejecuta 'ollama serve'.", config.OLLAMA_BASE_URL)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.FLASK_PORT, debug=Config.FLASK_ENV == "development", use_reloader=False)
