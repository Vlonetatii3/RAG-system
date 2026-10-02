"""Endpoint de chat RAG."""
from flask import Blueprint, current_app, jsonify, request

from services.ollama_service import OllamaError
from services.rag import ConversationNotFound
from utils.validators import error_response, parse_id

chat_bp = Blueprint("chat", __name__, url_prefix="/api")

MAX_TOP_K = 20


@chat_bp.post("/chat")
def chat():
    services = current_app.extensions["rag"]
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("El cuerpo debe ser JSON válido (UTF-8)", 400)

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return error_response("Mensaje no puede estar vacío", 400)

    conversation_id = data.get("conversation_id")
    if conversation_id is not None and (not isinstance(conversation_id, int) or isinstance(conversation_id, bool)):
        return error_response("conversation_id inválido", 400)

    top_k = data.get("top_k", 5)
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= MAX_TOP_K:
        return error_response(f"top_k debe ser un entero entre 1 y {MAX_TOP_K}", 400)

    scope = {}
    for key in ("subject_id", "document_id"):
        if data.get(key) is not None:
            scope[key] = parse_id(data[key])
            if scope[key] is None:
                return error_response(f"{key} inválido", 400)

    sql = "SELECT id FROM documents WHERE status = 'completed'"
    params = []
    if "subject_id" in scope:
        sql += " AND subject_id = ?"
        params.append(scope["subject_id"])
    if "document_id" in scope:
        sql += " AND id = ?"
        params.append(scope["document_id"])
    if not services["db"].fetchone(sql + " LIMIT 1", params):
        return error_response("No hay documentos procesados", 400)

    try:
        result = services["rag_service"].process_query(message.strip(), conversation_id, top_k, **scope)
    except ConversationNotFound as e:
        return error_response(str(e), 404)
    except OllamaError as e:
        return error_response(str(e), 503)

    return jsonify({"success": True, **result})
