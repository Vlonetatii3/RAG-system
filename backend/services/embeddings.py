"""Generación de embeddings y búsqueda por similaridad coseno sobre SQLite."""
from typing import List, Optional

import numpy as np

from models.database import Database
from services.ollama_service import OllamaService


def embedding_to_blob(embedding: List[float]) -> bytes:
    return np.asarray(embedding, dtype=np.float32).tobytes()


def blob_to_embedding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


class EmbeddingsService:
    def __init__(
        self,
        ollama_service: OllamaService,
        db: Database,
        model: str = "nomic-embed-text",
        threshold: float = 0.5,
    ):
        self.ollama = ollama_service
        self.db = db
        self.model = model
        self.threshold = threshold

    def _prefix(self, texts: List[str], task: str) -> List[str]:
        """nomic-embed-text fue entrenado con prefijos de tarea; usarlos mejora la búsqueda."""
        if "nomic" in self.model:
            return [f"search_{task}: {t}" for t in texts]
        return texts

    def generate_embedding(self, text: str, task: str = "query") -> List[float]:
        """task='query' para preguntas, 'document' para chunks."""
        return self.generate_embeddings([text], task)[0]

    def generate_embeddings(self, texts: List[str], task: str = "document") -> List[List[float]]:
        return self.ollama.embed_batch(self._prefix(texts, task), self.model)

    def save_embedding(self, document_id: int, chunk_id: int, embedding: List[float]) -> None:
        """Actualiza el embedding de un chunk existente."""
        self.db.execute(
            "UPDATE chunks SET embedding = ? WHERE id = ? AND document_id = ?",
            (embedding_to_blob(embedding), chunk_id, document_id),
        )

    def save_chunks(self, document_id: int, chunks: List, embeddings: List[List[float]]) -> None:
        """Inserta los chunks de un documento en una transacción.

        chunks puede ser una lista de strings o de dicts {text, page_start, page_end}.
        """
        rows = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            c = chunk if isinstance(chunk, dict) else {"text": chunk}
            rows.append((document_id, i, c["text"], embedding_to_blob(emb), c.get("page_start"), c.get("page_end")))
        self.db.executemany(
            "INSERT INTO chunks (document_id, chunk_index, text, embedding, page_start, page_end) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )

    def index_document(self, document_id: int, chunks: List[dict]) -> int:
        """Genera embeddings para los chunks y los guarda. Retorna la cantidad."""
        vectors = self.generate_embeddings([c["text"] for c in chunks], task="document")
        self.save_chunks(document_id, chunks, vectors)
        return len(chunks)

    @staticmethod
    def cosine_similarity(vec1, vec2) -> float:
        a = np.asarray(vec1, dtype=np.float32)
        b = np.asarray(vec2, dtype=np.float32)
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.clip(np.dot(a, b) / denom, 0.0, 1.0))

    def search(
        self,
        query: str,
        top_k: int = 5,
        subject_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> List[dict]:
        return self.search_similar(self.generate_embedding(query), top_k, document_id, subject_id)

    def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        document_id: Optional[int] = None,
        subject_id: Optional[int] = None,
    ) -> List[dict]:
        sql = (
            "SELECT c.id, c.document_id, c.chunk_index, c.text, c.embedding, c.page_start, c.page_end, d.filename "
            "FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE d.status = 'completed'"
        )
        params: list = []
        if document_id is not None:
            sql += " AND c.document_id = ?"
            params.append(document_id)
        if subject_id is not None:
            sql += " AND d.subject_id = ?"
            params.append(subject_id)
        rows = self.db.fetchall(sql, params)
        if not rows:
            return []

        query = np.asarray(query_embedding, dtype=np.float32)
        dim = query.shape[0]
        rows = [r for r in rows if len(r["embedding"]) == dim * 4]  # descarta dimensiones distintas
        if not rows:
            return []

        matrix = np.vstack([blob_to_embedding(r["embedding"]) for r in rows])
        norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
        norms[norms == 0] = 1e-12
        scores = np.clip(matrix @ query / norms, 0.0, 1.0)

        order = np.argsort(-scores)
        results = []
        for idx in order:
            score = float(scores[idx])
            if score <= self.threshold or len(results) >= top_k:
                break
            r = rows[idx]
            results.append(
                {
                    "id": r["id"],
                    "document_id": r["document_id"],
                    "filename": r["filename"],
                    "chunk_index": r["chunk_index"],
                    "text": r["text"],
                    "page_start": r["page_start"],
                    "page_end": r["page_end"],
                    "similarity": round(score, 4),
                }
            )
        return results


def format_pages(page_start: Optional[int], page_end: Optional[int]) -> str:
    if not page_start:
        return ""
    if page_end and page_end != page_start:
        return f"págs. {page_start}-{page_end}"
    return f"pág. {page_start}"
