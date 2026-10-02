"""Endpoints de práctica para el examen."""
from flask import Blueprint, current_app, jsonify, request

from services.ollama_service import OllamaError
from services.study import MAX_QUESTIONS
from utils.validators import error_response, parse_id

study_bp = Blueprint("study", __name__, url_prefix="/api/study")


@study_bp.post("/questions")
def generate_questions():
    services = current_app.extensions["rag"]
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("El cuerpo debe ser JSON válido (UTF-8)", 400)

    count = data.get("count", 5)
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_QUESTIONS:
        return error_response(f"count debe ser un entero entre 1 y {MAX_QUESTIONS}", 400)

    ids = {}
    for key in ("subject_id", "document_id"):
        if data.get(key) is not None:
            ids[key] = parse_id(data[key])
            if ids[key] is None:
                return error_response(f"{key} inválido", 400)

    topic = data.get("topic")
    if topic is not None and not isinstance(topic, str):
        return error_response("topic debe ser texto", 400)
    topic = (topic or "").strip() or None

    try:
        questions = services["study"].generate_questions(count, topic=topic, **ids)
    except LookupError as e:
        return error_response(str(e), 400)
    except (OllamaError, ValueError) as e:
        return error_response(str(e), 503)

    return jsonify({"success": True, "questions": questions})
