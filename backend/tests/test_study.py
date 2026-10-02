"""Materias, páginas, PDFs escaneados, migración, resúmenes y preguntas."""
import os
import sqlite3
import time

import pytest

from models.database import Database
from services.pdf_processor import PDFProcessor
from services.study import FRAGMENT_REF, make_sections, split_section
from tests.conftest import make_pdf
from tests.test_api import upload, wait_processed


def make_multipage_pdf(path, pages):
    """PDF con una página por elemento de `pages` (lista de listas de líneas)."""
    from pypdf import PdfWriter, PdfReader

    writer = PdfWriter()
    for i, lines in enumerate(pages):
        tmp = f"{path}.{i}.pdf"
        make_pdf(tmp, lines)
        writer.add_page(PdfReader(tmp).pages[0])
    with open(path, "wb") as f:
        writer.write(f)
    return path


# --- PDF: páginas y escaneados ----------------------------------------------

def test_split_pages_tracks_page_numbers(tmp_path):
    pdf = PDFProcessor()
    path = make_multipage_pdf(str(tmp_path / "m.pdf"), [["uno " * 150], ["dos " * 150], ["tres " * 150]])
    pages = pdf.extract_pages(path)
    assert [p for p, _ in pages] == [1, 2, 3]
    chunks = pdf.split_pages(pages, 500, 50)
    assert chunks[0]["page_start"] == 1
    assert chunks[-1]["page_end"] == 3
    assert any(c["page_start"] != c["page_end"] for c in chunks)  # hay chunks que cruzan páginas
    for c in chunks:
        assert c["page_start"] <= c["page_end"]


def test_scanned_pdf_gives_ocr_hint(tmp_path):
    path = make_pdf(str(tmp_path / "scan.pdf"), [])
    with pytest.raises(ValueError, match="OCR"):
        PDFProcessor().extract_pages(path)


def test_pages_without_text_are_counted(client, tmp_path):
    path = make_multipage_pdf(str(tmp_path / "mixto.pdf"), [["texto real de la pagina uno con contenido"], []])
    upload(client, path)
    doc = wait_processed(client)[0]
    assert doc["status"] == "completed"
    assert doc["page_count"] == 2 and doc["pages_without_text"] == 1


# --- Migración ---------------------------------------------------------------

def test_migrates_v1_database_without_losing_data(tmp_path):
    path = str(tmp_path / "v1.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE documents (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL UNIQUE,
            file_path TEXT NOT NULL, upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'processing', error TEXT);
        CREATE TABLE chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL, text TEXT NOT NULL, embedding BLOB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE);
        CREATE TABLE conversations (id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO documents (filename, file_path, status) VALUES ('viejo.pdf', 'x', 'completed');
        INSERT INTO chunks (document_id, chunk_index, text, embedding) VALUES (1, 0, 'hola', x'00');
        """
    )
    conn.commit()
    conn.close()

    db = Database(path)
    db.init_db()
    db.init_db()  # idempotente

    doc = db.fetchone("SELECT * FROM documents WHERE id = 1")
    assert doc["filename"] == "viejo.pdf" and doc["subject_id"] == db.default_subject_id()
    assert db.fetchone("SELECT COUNT(*) AS n FROM chunks")["n"] == 1  # no se borraron en cascada
    # La FK de chunks sigue apuntando a "documents": el cascade funciona
    db.execute("DELETE FROM documents WHERE id = 1")
    assert db.fetchone("SELECT COUNT(*) AS n FROM chunks")["n"] == 0


# --- Materias ----------------------------------------------------------------

def create_subject(client, name):
    r = client.post("/api/subjects", json={"name": name})
    assert r.status_code == 201
    return r.get_json()["subject"]["id"]


def test_subjects_crud(client):
    subjects = client.get("/api/subjects").get_json()["subjects"]
    assert [s["name"] for s in subjects] == ["General"]

    sid = create_subject(client, "  Microeconomía  ")
    assert client.post("/api/subjects", json={"name": "microeconomía"}).status_code == 409
    assert client.post("/api/subjects", json={"name": " "}).status_code == 400

    r = client.patch(f"/api/subjects/{sid}", json={"name": "Micro I"})
    assert r.get_json()["subject"]["name"] == "Micro I"
    assert client.patch("/api/subjects/999", json={"name": "x"}).status_code == 404
    assert client.delete("/api/subjects/abc").status_code == 400


def test_same_filename_in_two_subjects_and_scoped_chat(client, sample_pdf, fake_ollama, tmp_path):
    a = create_subject(client, "Astronomía")
    b = create_subject(client, "Biología")
    other = make_pdf(str(tmp_path / "otro.pdf"), ["Las celulas son la unidad basica de la vida."] * 10)

    with open(sample_pdf, "rb") as f1, open(other, "rb") as f2:
        r1 = client.post("/api/documents/upload", data={"file": (f1, "apunte.pdf"), "subject_id": str(a)})
        r2 = client.post("/api/documents/upload", data={"file": (f2, "apunte.pdf"), "subject_id": str(b)})
    assert r1.status_code == 202 and r2.status_code == 202
    wait_processed(client)

    assert client.get(f"/api/documents?subject_id={a}").get_json()["total"] == 1
    r = client.post("/api/chat", json={"message": "celulas unidad basica vida", "subject_id": a})
    assert r.status_code == 200
    assert all(s["document_id"] == r1.get_json()["document_id"] for s in r.get_json()["sources"])
    r = client.post("/api/chat", json={"message": "celulas unidad basica vida", "subject_id": b})
    assert r.get_json()["sources"] and r.get_json()["sources"][0]["page_start"] == 1

    # Borrar la materia borra sus documentos y archivos
    assert client.delete(f"/api/subjects/{a}").status_code == 200
    assert client.get(f"/api/documents?subject_id={a}").get_json()["total"] == 0
    assert client.get(f"/api/documents?subject_id={b}").get_json()["total"] == 1


def test_upload_to_missing_subject(client, sample_pdf):
    with open(sample_pdf, "rb") as f:
        r = client.post("/api/documents/upload", data={"file": (f, "x.pdf"), "subject_id": "999"})
    assert r.status_code == 404


def test_chat_with_subject_without_documents(client, sample_pdf):
    upload(client, sample_pdf)
    wait_processed(client)
    sid = create_subject(client, "Vacía")
    r = client.post("/api/chat", json={"message": "hola", "subject_id": sid})
    assert r.status_code == 400


# --- Resúmenes ---------------------------------------------------------------

def test_make_sections_and_split_keep_pages():
    sections = make_sections([(1, "a " * 600), (2, "b " * 600), (3, ""), (4, "c " * 600)])
    assert [(s["page_start"], s["page_end"]) for s in sections] == [(1, 4)]
    assert "[Página 4]" in sections[0]["text"]
    first, second = split_section(sections[0])
    assert (first["page_start"], second["page_end"]) == (1, 4)
    assert second["text"].startswith("[Página")


def test_summary_flow(client, sample_pdf, fake_ollama):
    doc_id = upload(client, sample_pdf).get_json()["document_id"]
    wait_processed(client)

    assert client.get(f"/api/documents/{doc_id}/summary").get_json()["summary_status"] is None
    assert client.post(f"/api/documents/{doc_id}/summary").status_code == 202

    deadline = time.time() + 10
    while time.time() < deadline:
        body = client.get(f"/api/documents/{doc_id}/summary").get_json()
        if body["summary_status"] != "processing":
            break
        time.sleep(0.05)
    assert body["summary_status"] == "completed", body
    assert "## Contenido" in body["summary"] and "### Tema simulado" in body["summary"]
    assert "## Idea general" in body["summary"]

    assert client.post("/api/documents/999/summary").status_code == 404


def test_summary_requires_processed_document(client, tmp_path):
    doc_id = upload(client, make_pdf(str(tmp_path / "vacio.pdf"), [])).get_json()["document_id"]
    wait_processed(client)  # queda "failed" (sin texto)
    assert client.post(f"/api/documents/{doc_id}/summary").status_code == 409


# --- Preguntas ---------------------------------------------------------------

def test_questions_endpoint(client, sample_pdf):
    r = client.post("/api/study/questions", json={"count": 3})
    assert r.status_code == 400  # sin documentos

    upload(client, sample_pdf)
    wait_processed(client)
    r = client.post("/api/study/questions", json={"count": 3})
    assert r.status_code == 200
    questions = r.get_json()["questions"]
    assert len(questions) == 2  # la pregunta vacía se descarta
    assert questions[0]["answer"] == "X es Y."  # se quita "(Fragmento 1)"
    assert questions[0]["source"].startswith("sample.pdf, pág")
    assert questions[1]["source"] is None  # fragmento inexistente

    assert client.post("/api/study/questions", json={"count": 0}).status_code == 400
    assert client.post("/api/study/questions", json={"count": 3, "topic": "tema inexistente xyz"}).status_code in (
        200,
        400,
    )


def test_fragment_reference_cleanup():
    assert FRAGMENT_REF.sub("", "Mide X (Fragmento 1).") == "Mide X."
    assert FRAGMENT_REF.sub("", "Y (fragmentos 2 y 3)") == "Y"
    assert FRAGMENT_REF.sub("", "Ver (pág. 3)") == "Ver (pág. 3)"
