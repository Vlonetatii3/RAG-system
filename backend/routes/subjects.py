"""Endpoints de materias (agrupan documentos y acotan las búsquedas)."""
import logging
import os
import shutil
import sqlite3

from flask import Blueprint, current_app, jsonify, request

from utils.validators import error_response, parse_id, to_iso

logger = logging.getLogger(__name__)
subjects_bp = Blueprint("subjects", __name__, url_prefix="/api/subjects")

MAX_NAME = 80


def _serialize(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "created_at": to_iso(row["created_at"]),
        "documents_count": row["documents_count"],
    }


def _get(db, subject_id: int):
    return db.fetchone(
        "SELECT s.*, (SELECT COUNT(*) FROM documents d WHERE d.subject_id = s.id) AS documents_count "
        "FROM subjects s WHERE s.id = ?",
        (subject_id,),
    )


def _clean_name(data) -> str | None:
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str) or not name.strip():
        return None
    return " ".join(name.split())[:MAX_NAME]


@subjects_bp.get("")
def list_subjects():
    db = current_app.extensions["rag"]["db"]
    db.default_subject_id()  # siempre existe al menos "General"
    rows = db.fetchall(
        "SELECT s.*, (SELECT COUNT(*) FROM documents d WHERE d.subject_id = s.id) AS documents_count "
        "FROM subjects s ORDER BY s.name COLLATE NOCASE"
    )
    return jsonify({"success": True, "subjects": [_serialize(r) for r in rows]})


@subjects_bp.post("")
def create_subject():
    db = current_app.extensions["rag"]["db"]
    name = _clean_name(request.get_json(silent=True))
    if not name:
        return error_response("El nombre de la materia no puede estar vacío", 400)
    try:
        subject_id = db.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
    except sqlite3.IntegrityError:
        return error_response("Ya existe una materia con ese nombre", 409)
    return jsonify({"success": True, "subject": _serialize(_get(db, subject_id))}), 201


@subjects_bp.patch("/<subject_id>")
def rename_subject(subject_id: str):
    db = current_app.extensions["rag"]["db"]
    sid = parse_id(subject_id)
    if sid is None:
        return error_response("ID inválido", 400)
    if not _get(db, sid):
        return error_response("Materia no encontrada", 404)
    name = _clean_name(request.get_json(silent=True))
    if not name:
        return error_response("El nombre de la materia no puede estar vacío", 400)
    try:
        db.execute("UPDATE subjects SET name = ? WHERE id = ?", (name, sid))
    except sqlite3.IntegrityError:
        return error_response("Ya existe una materia con ese nombre", 409)
    return jsonify({"success": True, "subject": _serialize(_get(db, sid))})


@subjects_bp.delete("/<subject_id>")
def delete_subject(subject_id: str):
    services = current_app.extensions["rag"]
    db = services["db"]
    sid = parse_id(subject_id)
    if sid is None:
        return error_response("ID inválido", 400)
    if not _get(db, sid):
        return error_response("Materia no encontrada", 404)

    db.execute("DELETE FROM subjects WHERE id = ?", (sid,))  # cascade: documentos y chunks
    folder = os.path.join(services["config"].UPLOADS_PATH, str(sid))
    shutil.rmtree(folder, ignore_errors=True)
    return jsonify({"success": True, "message": "Materia eliminada"})
