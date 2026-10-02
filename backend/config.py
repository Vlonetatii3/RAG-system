"""Configuración de la aplicación, cargada desde variables de entorno (.env)."""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _path(value: str) -> str:
    """Resuelve rutas relativas respecto a la carpeta backend/."""
    return value if os.path.isabs(value) else os.path.normpath(os.path.join(BASE_DIR, value))


class Config:
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))

    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL", "nomic-embed-text")
    # La spec pide 30s, pero en CPU/GPU modestas mistral tarda más (sobre todo al cargarse en frío)
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
    OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
    OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

    DATABASE_PATH = _path(os.getenv("DATABASE_PATH", "./data/rag.db"))
    UPLOADS_PATH = _path(os.getenv("UPLOADS_PATH", "./data/uploads"))

    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
    MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
    SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.5"))

    CORS_ORIGINS = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
        if o.strip()
    ]


# Alias a nivel de módulo (la spec pide que config.py exponga estas variables)
FLASK_PORT = Config.FLASK_PORT
OLLAMA_BASE_URL = Config.OLLAMA_BASE_URL
OLLAMA_MODEL = Config.OLLAMA_MODEL
EMBEDDINGS_MODEL = Config.EMBEDDINGS_MODEL
DATABASE_PATH = Config.DATABASE_PATH
UPLOADS_PATH = Config.UPLOADS_PATH
CHUNK_SIZE = Config.CHUNK_SIZE
CHUNK_OVERLAP = Config.CHUNK_OVERLAP
MAX_UPLOAD_SIZE_MB = Config.MAX_UPLOAD_SIZE_MB
