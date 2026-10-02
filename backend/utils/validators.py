"""Validaciones de entrada y helpers de respuesta."""
import re
from datetime import datetime, timezone
from typing import Optional

from flask import jsonify

PDF_MIMETYPES = {"application/pdf", "application/x-pdf", "application/octet-stream", ""}


def error_response(message: str, status: int):
    return jsonify({"success": False, "error": message}), status


def is_pdf_filename(filename: str) -> bool:
    return bool(filename) and filename.lower().endswith(".pdf")


def is_pdf_content(head: bytes) -> bool:
    """Los PDF empiezan con la firma %PDF-."""
    return head.startswith(b"%PDF-")


def safe_pdf_filename(filename: str) -> str:
    """Quita rutas y caracteres peligrosos, conservando acentos y espacios."""
    name = filename.replace("\\", "/").split("/")[-1]
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")
    return name


def to_iso(value: Optional[str]) -> Optional[str]:
    """Convierte un TIMESTAMP de SQLite (UTC, 'YYYY-MM-DD HH:MM:SS') a ISO 8601."""
    if not value:
        return value
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return value


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_id(value) -> Optional[int]:
    """Convierte un id de URL/JSON/form a int positivo; None si no es válido."""
    if isinstance(value, bool):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None
