"""Orquestación RAG: embedding de la pregunta → búsqueda → generación."""
import json
import time
from typing import List, Optional

from models.database import Database
from services.embeddings import EmbeddingsService, format_pages
from services.ollama_service import OllamaService

HISTORY_MESSAGES = 6  # mensajes previos de la conversación incluidos en el prompt
NOT_FOUND = "No encontré esa información en el material de esta materia."


MAX_CONTEXT_CHARS = 7000  # ~2000 tokens de contexto: deja lugar a instrucciones, historial y respuesta


class ConversationNotFound(LookupError):
    pass


def merge_overlap(a: str, b: str) -> str:
    """Une dos chunks consecutivos quitando el texto solapado entre ambos."""
    for k in range(min(len(a), len(b), 300), 10, -1):
        if a.endswith(b[:k]):
            return a + b[k:]
    return f"{a} {b}"


def source_label(chunk: dict) -> str:
    name = chunk.get("filename") or f"documento {chunk['document_id']}"
    pages = format_pages(chunk.get("page_start"), chunk.get("page_end"))
    return f"{name}, {pages}" if pages else name


class RAGService:
    def __init__(self, embeddings_service: EmbeddingsService, ollama_service: OllamaService, db: Database):
        self.embeddings = embeddings_service
        self.ollama = ollama_service
        self.db = db

    def expand_with_neighbors(self, chunks: List[dict]) -> List[dict]:
        """Convierte cada chunk encontrado en un pasaje con el chunk anterior y el siguiente.

        Se busca con chunks chicos (más precisos), pero una definición puede quedar
        partida entre dos chunks; el modelo recibe el pasaje completo. Pasajes del mismo
        documento que se tocan se fusionan. Se respeta el orden de relevancia.
        """
        windows: List[dict] = []
        for c in chunks:
            lo, hi = c["chunk_index"] - 1, c["chunk_index"] + 1
            for w in windows:
                if w["document_id"] == c["document_id"] and lo <= w["hi"] + 1 and hi >= w["lo"] - 1:
                    w["lo"], w["hi"] = min(w["lo"], lo), max(w["hi"], hi)
                    break
            else:
                windows.append({"document_id": c["document_id"], "filename": c.get("filename"), "lo": lo, "hi": hi})

        passages: List[dict] = []
        total = 0
        for w in windows:
            rows = self.db.fetchall(
                "SELECT text, page_start, page_end FROM chunks "
                "WHERE document_id = ? AND chunk_index BETWEEN ? AND ? ORDER BY chunk_index",
                (w["document_id"], w["lo"], w["hi"]),
            )
            if not rows:
                continue
            text = rows[0]["text"]
            for r in rows[1:]:
                text = merge_overlap(text, r["text"])
            if passages and total + len(text) > MAX_CONTEXT_CHARS:
                break
            total += len(text)
            pages = [p for r in rows for p in (r["page_start"], r["page_end"]) if p]
            passages.append(
                {
                    "document_id": w["document_id"],
                    "filename": w["filename"],
                    "text": text,
                    "page_start": min(pages) if pages else None,
                    "page_end": max(pages) if pages else None,
                }
            )
        return passages

    def build_context(self, chunks: List[dict]) -> str:
        return "\n---\n".join(f"[Fuente: {source_label(c)}]\n{c['text']}" for c in chunks)

    def create_rag_prompt(self, context: str, query: str, history: str = "") -> str:
        history_block = f"\nHISTORIAL DE LA CONVERSACIÓN:\n{history}\n" if history else ""
        return (
            "Eres un asistente útil que responde preguntas basadas en documentos.\n"
            "Ayudas a un estudiante universitario a estudiar con el material de su materia.\n"
            "Reglas:\n"
            "- Responde en el mismo idioma de la pregunta usando ÚNICAMENTE la información del CONTEXTO.\n"
            "- Si el CONTEXTO responde la pregunta total o parcialmente (aunque no sea con una definición textual), "
            "responde con esa información.\n"
            f"- Solo si el CONTEXTO no tiene nada relevante, responde únicamente: \"{NOT_FOUND}\"\n"
            "- No agregues definiciones, ejemplos, supuestos ni números que no estén en el CONTEXTO: "
            "el estudiante podría estudiar algo incorrecto. Si para un cálculo falta un dato, dilo.\n"
            "- Explica con claridad; usa viñetas o pasos si ayudan, e incluye definiciones y fórmulas tal como aparecen.\n"
            "- Al final cita las fuentes que usaste copiando la etiqueta [Fuente: ...] del fragmento correspondiente, "
            "por ejemplo: (Fuente: Apunte.pdf, pág. 3). No inventes páginas.\n"
            f"\nCONTEXTO:\n{context or '(No se encontraron fragmentos relevantes)'}\n"
            f"{history_block}"
            f"\nPREGUNTA: {query}\n"
            "\nRespuesta:"
        )

    def _ensure_conversation(self, conversation_id: Optional[int], subject_id: Optional[int]) -> int:
        if conversation_id is None:
            return self.db.execute("INSERT INTO conversations (subject_id) VALUES (?)", (subject_id,))
        if not self.db.fetchone("SELECT id FROM conversations WHERE id = ?", (conversation_id,)):
            raise ConversationNotFound(f"Conversación {conversation_id} no encontrada")
        return conversation_id

    def _history(self, conversation_id: int) -> List[dict]:
        rows = self.db.fetchall(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (conversation_id, HISTORY_MESSAGES),
        )
        return list(reversed(rows))

    def process_query(
        self,
        query: str,
        conversation_id: Optional[int] = None,
        top_k: int = 5,
        subject_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> dict:
        start = time.perf_counter()
        conversation_id = self._ensure_conversation(conversation_id, subject_id)
        history = self._history(conversation_id)
        labels = {"user": "Estudiante", "assistant": "Asistente"}
        history_text = "\n".join(f"{labels.get(m['role'], m['role'])}: {m['content']}" for m in history)

        # Las repreguntas ("¿y en el largo plazo?") no tienen sentido solas:
        # se busca con la pregunta anterior del estudiante como contexto.
        previous_questions = [m["content"] for m in history if m["role"] == "user"]
        search_text = f"{previous_questions[-1]} {query}" if previous_questions else query

        chunks = self.embeddings.search(search_text, top_k=top_k, subject_id=subject_id, document_id=document_id)
        context = self.build_context(self.expand_with_neighbors(chunks))
        prompt = self.create_rag_prompt(context, query, history_text)
        reply = self.ollama.generate_answer(prompt, temperature=0.3, max_tokens=1000)

        chunk_ids = json.dumps([c["id"] for c in chunks])
        self.db.execute(
            "INSERT INTO messages (conversation_id, role, content, context_chunks) VALUES (?, 'user', ?, NULL)",
            (conversation_id, query),
        )
        self.db.execute(
            "INSERT INTO messages (conversation_id, role, content, context_chunks) VALUES (?, 'assistant', ?, ?)",
            (conversation_id, reply, chunk_ids),
        )
        self.db.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (conversation_id,)
        )

        return {
            "conversation_id": conversation_id,
            "reply": reply,
            "sources": [
                {
                    "document_id": c["document_id"],
                    "chunk_id": c["id"],
                    "filename": c["filename"],
                    "page_start": c["page_start"],
                    "page_end": c["page_end"],
                    "text": c["text"],
                    "similarity": c["similarity"],
                }
                for c in chunks
            ],
            "processing_time_ms": int((time.perf_counter() - start) * 1000),
        }
