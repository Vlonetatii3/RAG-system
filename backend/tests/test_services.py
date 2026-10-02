import pytest

from models.database import Database
from services.embeddings import EmbeddingsService
from services.pdf_processor import PDFProcessor
from services.rag import ConversationNotFound, RAGService


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "svc.db"))
    database.init_db()
    return database


# --- Database ---------------------------------------------------------------

def test_init_db_is_idempotent_and_creates_tables(db):
    db.init_db()
    tables = {r["name"] for r in db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"documents", "chunks", "conversations", "messages"} <= tables


def test_cascade_delete_removes_chunks(db):
    doc_id = db.execute(
        "INSERT INTO documents (subject_id, filename, file_path) VALUES (?, 'a.pdf', 'x')", (db.default_subject_id(),)
    )
    db.execute("INSERT INTO chunks (document_id, chunk_index, text, embedding) VALUES (?, 0, 't', x'00')", (doc_id,))
    db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    assert db.fetchone("SELECT COUNT(*) AS n FROM chunks")["n"] == 0


# --- PDFProcessor -----------------------------------------------------------

def test_extract_text(sample_pdf):
    text = PDFProcessor().extract_text(sample_pdf)
    assert "Jupiter" in text
    assert "  " not in text


def test_extract_text_missing_file():
    with pytest.raises(FileNotFoundError):
        PDFProcessor().extract_text("no_existe.pdf")


def test_extract_text_corrupt(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 basura")
    with pytest.raises(ValueError):
        PDFProcessor().extract_text(str(bad))


def test_split_chunks_size_and_overlap():
    words = [f"palabra{i}" for i in range(400)]
    chunks = PDFProcessor().split_chunks(" ".join(words), 500, 50)
    assert len(chunks) > 1
    for c in chunks[:-1]:
        assert 400 <= len(c) <= 600
    for prev, nxt in zip(chunks, chunks[1:]):
        assert prev.split()[-1] in nxt.split()[:10]  # solapamiento
    # No se pierden palabras
    assert set(" ".join(chunks).split()) == set(words)


def test_split_chunks_short_text():
    assert PDFProcessor().split_chunks("hola mundo") == ["hola mundo"]
    assert PDFProcessor().split_chunks("   ") == []


def test_validate_pdf(sample_pdf, tmp_path):
    p = PDFProcessor()
    assert p.validate_pdf(sample_pdf) is True
    txt = tmp_path / "a.txt"
    txt.write_text("x")
    assert p.validate_pdf(str(txt)) is False
    assert p.validate_pdf("no_existe.pdf") is False


# --- Embeddings -------------------------------------------------------------

def test_cosine_similarity():
    cs = EmbeddingsService.cosine_similarity
    assert cs([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cs([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cs([1, 0], [-1, 0]) == 0.0  # recortado a [0, 1]
    assert cs([0, 0], [1, 0]) == 0.0


def _store(db, fake_ollama, texts, filename="doc.pdf", status="completed", subject_id=None):
    svc = EmbeddingsService(fake_ollama, db)
    subject_id = subject_id or db.default_subject_id()
    doc_id = db.execute(
        "INSERT INTO documents (subject_id, filename, file_path, status) VALUES (?, ?, 'x', ?)",
        (subject_id, filename, status),
    )
    svc.save_chunks(doc_id, texts, [svc.generate_embedding(t) for t in texts])
    return svc, doc_id


def test_search_similar_ranks_and_filters(db, fake_ollama):
    svc, doc_id = _store(db, fake_ollama, ["planetas del sistema solar", "recetas de cocina italiana"])
    results = svc.search_similar(svc.generate_embedding("sistema solar planetas"), top_k=5)
    assert results[0]["text"] == "planetas del sistema solar"
    assert all(r["similarity"] > 0.5 for r in results)
    assert set(results[0]) >= {"id", "document_id", "chunk_index", "text", "similarity"}


def test_search_similar_top_k_and_document_filter(db, fake_ollama):
    svc, doc1 = _store(db, fake_ollama, ["sol luna"] * 5, "a.pdf")
    _, doc2 = _store(db, fake_ollama, ["sol luna"] * 5, "b.pdf")
    q = svc.generate_embedding("sol luna")
    assert len(svc.search_similar(q, top_k=3)) == 3
    assert {r["document_id"] for r in svc.search_similar(q, top_k=10, document_id=doc2)} == {doc2}


def test_search_ignores_unfinished_documents(db, fake_ollama):
    svc, _ = _store(db, fake_ollama, ["sol luna"], status="processing")
    assert svc.search_similar(svc.generate_embedding("sol luna")) == []


# --- RAG --------------------------------------------------------------------

def test_build_context_and_prompt(db, fake_ollama):
    rag = RAGService(EmbeddingsService(fake_ollama, db), fake_ollama, db)
    ctx = rag.build_context([{"document_id": 1, "filename": "a.pdf", "text": "uno"},
                             {"document_id": 1, "filename": "a.pdf", "text": "dos"}])
    assert "---" in ctx and "uno" in ctx and "dos" in ctx
    prompt = rag.create_rag_prompt(ctx, "¿qué?")
    assert "CONTEXTO:" in prompt and "PREGUNTA: ¿qué?" in prompt and prompt.endswith("Respuesta:")


def test_process_query_saves_messages_and_history(db, fake_ollama):
    svc, _ = _store(db, fake_ollama, ["planetas del sistema solar"])
    rag = RAGService(svc, fake_ollama, db)
    r1 = rag.process_query("sistema solar")
    assert r1["reply"] == "Respuesta simulada"
    assert r1["sources"] and r1["sources"][0]["chunk_id"]
    r2 = rag.process_query("planetas", conversation_id=r1["conversation_id"])
    assert r2["conversation_id"] == r1["conversation_id"]
    assert "HISTORIAL" in fake_ollama.prompts[-1]
    assert db.fetchone("SELECT COUNT(*) AS n FROM messages")["n"] == 4


def test_process_query_unknown_conversation(db, fake_ollama):
    rag = RAGService(EmbeddingsService(fake_ollama, db), fake_ollama, db)
    with pytest.raises(ConversationNotFound):
        rag.process_query("hola", conversation_id=999)


def test_merge_overlap():
    from services.rag import merge_overlap

    assert merge_overlap("uno dos tres cuatro cinco", "tres cuatro cinco seis") == "uno dos tres cuatro cinco seis"
    assert merge_overlap("sin solapamiento acá", "otra cosa") == "sin solapamiento acá otra cosa"


def test_expand_with_neighbors_completes_split_definitions(db, fake_ollama):
    from services.pdf_processor import PDFProcessor

    # Una definición que queda partida entre dos chunks
    text = ("relleno " * 50) + "El impuesto pigouviano grava la actividad contaminante por un monto igual al costo externo. " + (
        "final " * 50
    )
    chunks = PDFProcessor().split_pages([(1, text)], 120, 20)
    svc = EmbeddingsService(fake_ollama, db)
    doc_id = db.execute(
        "INSERT INTO documents (subject_id, filename, file_path, status) VALUES (?, 'a.pdf', 'x', 'completed')",
        (db.default_subject_id(),),
    )
    svc.index_document(doc_id, chunks)
    rag = RAGService(svc, fake_ollama, db)

    hit = next(i for i, c in enumerate(chunks) if "pigouviano" in c["text"])
    rows = db.fetchall("SELECT id, document_id, chunk_index, text FROM chunks WHERE chunk_index IN (?, ?)", (hit, hit + 2))
    found = [dict(r, filename="a.pdf") for r in rows]
    passages = rag.expand_with_neighbors(found)

    assert "pigouviano grava la actividad contaminante por un monto igual al costo externo." in passages[0]["text"]
    assert len(passages) == 1  # chunks vecinos del mismo documento se fusionan en un solo pasaje
    assert passages[0]["text"].count("El impuesto pigouviano") == 1  # sin texto duplicado por el solapamiento
