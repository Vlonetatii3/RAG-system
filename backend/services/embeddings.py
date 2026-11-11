"""Generación de embeddings y búsqueda por similaridad coseno sobre SQLite."""
import threading
from collections import OrderedDict
from typing import List, Optional, Tuple

import numpy as np

from models.database import Database
from services.ollama_service import OllamaService


def embedding_to_blob(embedding: List[float]) -> bytes:
    return np.asarray(embedding, dtype=np.float32).tobytes()


def blob_to_embedding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


CACHE_SCOPES = 32  # alcances (materia/documento) que se mantienen en memoria


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
        # Matrices de embeddings ya normalizadas por alcance (materia/documento/dimensión).
        # Evita leer y decodificar todos los BLOBs de SQLite en cada pregunta.
        self._cache: "OrderedDict[tuple, Tuple[tuple, np.ndarray, np.ndarray]]" = OrderedDict()
        self._cache_lock = threading.Lock()

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
        self.clear_cache()  # cambia un vector sin cambiar los ids: la firma no lo detectaría

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

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

    @staticmethod
    def _scope_sql(document_id: Optional[int], subject_id: Optional[int]) -> Tuple[str, list]:
        sql = "FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.status = 'completed'"
        params: list = []
        if document_id is not None:
            sql += " AND c.document_id = ?"
            params.append(document_id)
        if subject_id is not None:
            sql += " AND d.subject_id = ?"
            params.append(subject_id)
        return sql, params

    def _matrix(self, dim: int, document_id: Optional[int], subject_id: Optional[int]):
        """(ids, matriz normalizada) de los chunks del alcance, cacheada.

        La firma (cantidad, id máximo, suma de ids) cambia cuando se agregan o borran
        chunks o cuando un documento pasa a 'completed', así que el caché nunca queda viejo
        y no hace falta invalidarlo desde las rutas.
        """
        where, params = self._scope_sql(document_id, subject_id)
        where += " AND length(c.embedding) = ?"  # descarta vectores de otra dimensión (otro modelo)
        params.append(dim * 4)
        sig_row = self.db.fetchone(
            f"SELECT COUNT(*) AS n, COALESCE(MAX(c.id), 0) AS mx, COALESCE(SUM(c.id), 0) AS sm {where}", params
        )
        signature = (sig_row["n"], sig_row["mx"], sig_row["sm"])
        key = (dim, document_id, subject_id)
        with self._cache_lock:
            hit = self._cache.get(key)
            if hit and hit[0] == signature:
                self._cache.move_to_end(key)
                return hit[1], hit[2]

        rows = self.db.fetchall(f"SELECT c.id, c.embedding {where} ORDER BY c.id", params)
        ids = np.fromiter((r["id"] for r in rows), dtype=np.int64, count=len(rows))
        if rows:
            matrix = np.frombuffer(b"".join(r["embedding"] for r in rows), dtype=np.float32).reshape(len(rows), dim)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            matrix = matrix / norms
        else:
            matrix = np.empty((0, dim), dtype=np.float32)

        with self._cache_lock:
            self._cache[key] = (signature, ids, matrix)
            self._cache.move_to_end(key)
            while len(self._cache) > CACHE_SCOPES:
                self._cache.popitem(last=False)
        return ids, matrix

    def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        document_id: Optional[int] = None,
        subject_id: Optional[int] = None,
    ) -> List[dict]:
        query = np.asarray(query_embedding, dtype=np.float32)
        ids, matrix = self._matrix(query.shape[0], document_id, subject_id)
        if not len(ids):
            return []
        qnorm = float(np.linalg.norm(query)) or 1e-12
        scores = np.clip(matrix @ (query / qnorm), 0.0, 1.0)

        k = min(top_k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]  # O(n) en vez de ordenar todo
        top = top[np.argsort(-scores[top])]
        top = [i for i in top if scores[i] > self.threshold]
        if not top:
            return []

        wanted = [int(ids[i]) for i in top]
        rows = self.db.fetchall(
            "SELECT c.id, c.document_id, c.chunk_index, c.text, c.page_start, c.page_end, d.filename "
            f"FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id IN ({','.join('?' * len(wanted))})",
            wanted,
        )
        by_id = {r["id"]: r for r in rows}
        results = []
        for i, chunk_id in zip(top, wanted):
            r = by_id.get(chunk_id)
            if r is None:  # borrado entre la lectura del caché y esta consulta
                continue
            results.append(
                {
                    "id": r["id"],
                    "document_id": r["document_id"],
                    "filename": r["filename"],
                    "chunk_index": r["chunk_index"],
                    "text": r["text"],
                    "page_start": r["page_start"],
                    "page_end": r["page_end"],
                    "similarity": round(float(scores[i]), 4),
                }
            )
        return results


def format_pages(page_start: Optional[int], page_end: Optional[int]) -> str:
    if not page_start:
        return ""
    if page_end and page_end != page_start:
        return f"págs. {page_start}-{page_end}"
    return f"pág. {page_start}"
