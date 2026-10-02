"""Endpoints de documentos: subir, listar, eliminar y resumir PDFs."""
import logging
import os
import sqlite3

from flask import Blueprint, current_app, jsonify, request

from utils.validators import (
    error_response,
    is_pdf_content,
    is_pdf_filename,
    parse_id,
    safe_pdf_filename,
    to_iso,
)

logger = logging.getLogger(__name__)
documents_bp = Blueprint("documents", __name__, url_prefix="/api/documents")

DOCUMENT_COLUMNS = (
    "d.id, d.subject_id, d.filename, d.file_path, d.upload_date, d.status, d.error, d.page_count, "
    "d.pages_without_text, d.summary_status, d.summary_progress, d.summary_error, "
    "(SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunks_count"
)


def serialize_document(r: dict) -> dict:
    return {
        "id": r["id"],
        "subject_id": r["subject_id"],
        "filename": r["filename"],
        "upload_date": to_iso(r["upload_date"]),
        "status": r["status"],
        "chunks_count": r["chunks_count"] if r["status"] == "completed" else None,
        "error": r["error"],
        "page_count": r["page_count"],
        "pages_without_text": r["pages_without_text"] or 0,
        "summary_status": r["summary_status"],
        "summary_progress": r["summary_progress"],
        "summary_error": r["summary_error"],
    }


def process_document(services: dict, document_id: int, file_path: str) -> None:
    """Pipeline de procesamiento (corre en un hilo de fondo)."""
    db = services["db"]
    pdf = services["pdf_processor"]
    embeddings = services["embeddings"]
    config = services["config"]
    try:
        pages = pdf.extract_pages(file_path)
        empty = sum(1 for _, text in pages if not text)
        db.execute(
            "UPDATE documents SET page_count = ?, pages_without_text = ? WHERE id = ?",
            (len(pages), empty, document_id),
        )
        chunks = pdf.split_pages(pages, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        embeddings.index_document(document_id, chunks)
        db.execute("UPDATE documents SET status = 'completed', error = NULL WHERE id = ?", (document_id,))
        logger.info("Documento %s procesado: %d páginas, %d chunks", document_id, len(pages), len(chunks))
    except Exception as e:
        logger.exception("Falló el procesamiento del documento %s", document_id)
        try:
            db.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            db.execute(
                "UPDATE documents SET status = 'failed', error = ? WHERE id = ?", (str(e)[:500], document_id)
            )
        except sqlite3.Error:
            logger.exception("No se pudo marcar el documento %s como fallido", document_id)


def summarize_document(services: dict, document_id: int) -> None:
    """Genera el resumen de un documento (hilo de fondo; puede tardar varios minutos)."""
    db = services["db"]
    doc = db.fetchone("SELECT filename, file_path FROM documents WHERE id = ?", (document_id,))
    if not doc:
        return

    def progress(message: str) -> None:
        db.execute("UPDATE documents SET summary_progress = ? WHERE id = ?", (message, document_id))

    try:
        pages = services["pdf_processor"].extract_pages(doc["file_path"])
        summary = services["study"].summarize(doc["filename"], pages, on_progress=progress)
        db.execute(
            "UPDATE documents SET summary = ?, summary_status = 'completed', summary_progress = NULL, "
            "summary_error = NULL WHERE id = ?",
            (summary, document_id),
        )
        logger.info("Resumen del documento %s listo", document_id)
    except Exception as e:
        logger.exception("Falló el resumen del documento %s", document_id)
        db.execute(
            "UPDATE documents SET summary_status = 'failed', summary_progress = NULL, summary_error = ? "
            "WHERE id = ?",
            (str(e)[:500], document_id),
        )


@documents_bp.post("/upload")
def upload_document():
    services = current_app.extensions["rag"]
    config = services["config"]
    db = services["db"]

    file = request.files.get("file")
    if file is None or not file.filename:
        return error_response("No se proporcionó archivo", 400)

    filename = safe_pdf_filename(file.filename)
    if not is_pdf_filename(filename) or not is_pdf_content(file.stream.read(5)):
        return error_response("Solo se aceptan PDFs", 400)
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > config.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        return error_response("Archivo demasiado grande", 413)

    raw_subject = request.form.get("subject_id")
    if raw_subject:
        subject_id = parse_id(raw_subject)
        if subject_id is None or not db.fetchone("SELECT id FROM subjects WHERE id = ?", (subject_id,)):
            return error_response("Materia no encontrada", 404)
    else:
        subject_id = db.default_subject_id()

    if db.fetchone("SELECT id FROM documents WHERE subject_id = ? AND filename = ?", (subject_id, filename)):
        return error_response("Archivo ya existe", 409)

    folder = os.path.join(config.UPLOADS_PATH, str(subject_id))
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, filename)
    try:
        document_id = db.execute(
            "INSERT INTO documents (subject_id, filename, file_path, status) VALUES (?, ?, ?, 'processing')",
            (subject_id, filename, file_path),
        )
    except sqlite3.IntegrityError:
        return error_response("Archivo ya existe", 409)

    try:
        file.save(file_path)
    except OSError:
        db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        raise

    services["executor"].submit(process_document, services, document_id, file_path)

    return (
        jsonify(
            {
                "success": True,
                "document_id": document_id,
                "subject_id": subject_id,
                "filename": filename,
                "status": "processing",
                "message": "Documento en procesamiento",
            }
        ),
        202,
    )


@documents_bp.get("")
def list_documents():
    db = current_app.extensions["rag"]["db"]
    sql = f"SELECT {DOCUMENT_COLUMNS} FROM documents d"
    params: tuple = ()
    raw_subject = request.args.get("subject_id")
    if raw_subject:
        subject_id = parse_id(raw_subject)
        if subject_id is None:
            return error_response("subject_id inválido", 400)
        sql += " WHERE d.subject_id = ?"
        params = (subject_id,)
    rows = db.fetchall(sql + " ORDER BY d.upload_date DESC, d.id DESC", params)
    documents = [serialize_document(r) for r in rows]
    return jsonify({"success": True, "documents": documents, "total": len(documents)})


@documents_bp.delete("/<doc_id>")
def delete_document(doc_id: str):
    db = current_app.extensions["rag"]["db"]
    document_id = parse_id(doc_id)
    if document_id is None:
        return error_response("ID inválido", 400)

    doc = db.fetchone("SELECT id, file_path FROM documents WHERE id = ?", (document_id,))
    if not doc:
        return error_response("Documento no encontrado", 404)

    db.execute("DELETE FROM documents WHERE id = ?", (document_id,))  # cascade borra chunks
    try:
        if os.path.exists(doc["file_path"]):
            os.remove(doc["file_path"])
    except OSError:
        logger.warning("No se pudo borrar el archivo %s", doc["file_path"])

    return jsonify({"success": True, "message": "Documento eliminado"})


@documents_bp.post("/<doc_id>/summary")
def start_summary(doc_id: str):
    services = current_app.extensions["rag"]
    db = services["db"]
    document_id = parse_id(doc_id)
    if document_id is None:
        return error_response("ID inválido", 400)
    doc = db.fetchone("SELECT status, summary_status FROM documents WHERE id = ?", (document_id,))
    if not doc:
        return error_response("Documento no encontrado", 404)
    if doc["status"] != "completed":
        return error_response("El documento todavía no terminó de procesarse", 409)
    if doc["summary_status"] == "processing":
        return error_response("El resumen ya se está generando", 409)

    db.execute(
        "UPDATE documents SET summary_status = 'processing', summary_progress = 'En cola', "
        "summary_error = NULL WHERE id = ?",
        (document_id,),
    )
    services["summary_executor"].submit(summarize_document, services, document_id)
    return jsonify({"success": True, "document_id": document_id, "summary_status": "processing"}), 202


@documents_bp.get("/<doc_id>/summary")
def get_summary(doc_id: str):
    db = current_app.extensions["rag"]["db"]
    document_id = parse_id(doc_id)
    if document_id is None:
        return error_response("ID inválido", 400)
    doc = db.fetchone(
        "SELECT id, filename, summary, summary_status, summary_progress, summary_error FROM documents WHERE id = ?",
        (document_id,),
    )
    if not doc:
        return error_response("Documento no encontrado", 404)
    return jsonify(
        {
            "success": True,
            "document_id": doc["id"],
            "filename": doc["filename"],
            "summary_status": doc["summary_status"],
            "summary_progress": doc["summary_progress"],
            "summary_error": doc["summary_error"],
            "summary": doc["summary"],
        }
    )
