import io
import os
import time

from tests.conftest import make_pdf


def upload(client, path, name=None):
    with open(path, "rb") as f:
        return client.post(
            "/api/documents/upload",
            data={"file": (io.BytesIO(f.read()), name or os.path.basename(path))},
            content_type="multipart/form-data",
        )


def wait_processed(client, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        docs = client.get("/api/documents").get_json()["documents"]
        if docs and all(d["status"] != "processing" for d in docs):
            return docs
        time.sleep(0.05)
    raise AssertionError("El documento no terminó de procesarse")


def test_health(client, fake_ollama, test_config):
    body = client.get("/api/health").get_json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected" and body["ollama"] == "connected"
    assert body["model"] == test_config.OLLAMA_MODEL and body["timestamp"].endswith("Z")
    assert body["model_available"] and body["embeddings_model_available"]

    fake_ollama.connected = False
    body = client.get("/api/health").get_json()
    assert body["status"] == "unhealthy" and body["ollama"] == "disconnected"


def test_list_empty(client):
    r = client.get("/api/documents")
    assert r.status_code == 200
    assert r.get_json() == {"success": True, "documents": [], "total": 0}


def test_upload_without_file(client):
    r = client.post("/api/documents/upload")
    assert r.status_code == 400
    assert r.get_json()["error"] == "No se proporcionó archivo"


def test_upload_non_pdf(client):
    r = client.post(
        "/api/documents/upload",
        data={"file": (io.BytesIO(b"hola"), "doc.txt")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "Solo se aceptan PDFs"


def test_upload_fake_pdf_extension(client):
    r = client.post(
        "/api/documents/upload",
        data={"file": (io.BytesIO(b"no soy un pdf"), "doc.pdf")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400


def test_upload_too_large(client):
    big = b"%PDF-" + b"0" * (51 * 1024 * 1024)
    r = client.post(
        "/api/documents/upload",
        data={"file": (io.BytesIO(big), "big.pdf")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 413
    assert r.get_json()["error"] == "Archivo demasiado grande"


def test_full_flow(client, sample_pdf, test_config):
    r = upload(client, sample_pdf, "documento.pdf")
    assert r.status_code == 202
    body = r.get_json()
    assert body["success"] and body["status"] == "processing" and body["document_id"] > 0
    doc_id = body["document_id"]

    assert upload(client, sample_pdf, "documento.pdf").status_code == 409

    docs = wait_processed(client)
    assert docs[0]["status"] == "completed" and docs[0]["chunks_count"] >= 1
    assert docs[0]["upload_date"].endswith("Z")

    r = client.post("/api/chat", json={"message": "planeta mas grande del sistema solar", "top_k": 2})
    assert r.status_code == 200
    chat = r.get_json()
    assert chat["reply"] and chat["conversation_id"] > 0
    assert 1 <= len(chat["sources"]) <= 2
    assert all(s["similarity"] > 0.5 for s in chat["sources"])
    assert isinstance(chat["processing_time_ms"], int)

    r2 = client.post("/api/chat", json={"message": "y la fotosintesis?", "conversation_id": chat["conversation_id"]})
    assert r2.get_json()["conversation_id"] == chat["conversation_id"]

    path = os.path.join(test_config.UPLOADS_PATH, str(body["subject_id"]), "documento.pdf")
    assert os.path.exists(path)
    r = client.delete(f"/api/documents/{doc_id}")
    assert r.status_code == 200 and r.get_json()["message"] == "Documento eliminado"
    assert not os.path.exists(path)
    assert client.get("/api/documents").get_json()["total"] == 0


def test_failed_processing_marks_failed(client, tmp_path):
    empty = make_pdf(str(tmp_path / "vacio.pdf"), [])
    assert upload(client, empty).status_code == 202
    docs = wait_processed(client)
    assert docs[0]["status"] == "failed" and docs[0]["error"]


def test_documents_ordered_desc(client, tmp_path):
    for name in ("uno.pdf", "dos.pdf"):
        upload(client, make_pdf(str(tmp_path / name), ["texto de prueba"]))
    docs = wait_processed(client)
    assert [d["filename"] for d in docs] == ["dos.pdf", "uno.pdf"]


def test_delete_errors(client):
    assert client.delete("/api/documents/9999").status_code == 404
    r = client.delete("/api/documents/abc")
    assert r.status_code == 400 and r.get_json()["error"] == "ID inválido"


def test_chat_validation(client):
    r = client.post("/api/chat", json={"message": ""})
    assert r.status_code == 400 and r.get_json()["error"] == "Mensaje no puede estar vacío"
    r = client.post("/api/chat", json={"message": "hola"})
    assert r.status_code == 400 and r.get_json()["error"] == "No hay documentos procesados"
    assert client.post("/api/chat", json={"message": "hola", "top_k": 0}).status_code == 400
    assert client.post("/api/chat", data="x").status_code == 400


def test_chat_unknown_conversation(client, sample_pdf):
    upload(client, sample_pdf)
    wait_processed(client)
    r = client.post("/api/chat", json={"message": "hola", "conversation_id": 12345})
    assert r.status_code == 404
