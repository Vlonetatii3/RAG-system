"""Herramientas de estudio: resúmenes de documentos y preguntas de práctica.

Resúmenes: el modelo tiene una ventana de contexto chica (~4000 tokens en una
GPU de 6GB), así que no puede leer un PDF entero de una vez. Se toman notas de
cada sección y se incluyen completas en el resumen; el último paso solo redacta
la "idea general" a partir de los títulos de los temas. (Pedirle al modelo que
condense todas las notas en un resumen final hacía que omitiera unidades enteras.)
"""
import logging
import random
import re
from typing import Callable, List, Optional, Tuple

from models.database import Database
from services.embeddings import EmbeddingsService
from services.ollama_service import OllamaService
from services.rag import source_label

logger = logging.getLogger(__name__)

SECTION_CHARS = 4000  # ~1300 tokens de entrada + hasta 1400 de notas: entra en un contexto de 4096
SECTION_NOTES_TOKENS = 1400
MIN_SPLIT_CHARS = 1200  # por debajo de esto no se sigue partiendo una sección cuyas notas se cortan
MAX_QUESTIONS = 10
QUESTION_CHUNKS = 8

SECTION_PROMPT = """Eres un asistente que ayuda a un estudiante universitario a estudiar.
Abajo está el texto de las {pages} del documento "{name}". Las marcas [Página N] indican dónde empieza cada página.

Escribe notas de estudio en español, en Markdown, con este formato:
### Título del tema
- **término clave**: definición o explicación (pág. N)
- clasificaciones, diferencias entre conceptos, fórmulas (cópialas tal cual) y ejemplos importantes (pág. N)

Reglas:
- Crea un ### por cada tema o unidad que aparezca en el texto, y no omitas ninguno.
- Usa solo información del texto; no agregues nada.
- Sé conciso, pero no dejes afuera conceptos, condiciones ni fórmulas.

TEXTO:
{text}

NOTAS:"""

OVERVIEW_PROMPT = """Estos son los temas que cubre el documento "{name}":
{topics}

Escribe en español un párrafo breve (máximo 4 oraciones) que explique de qué trata el documento y cómo se relacionan
sus temas, para que un estudiante tenga el panorama general antes de leer el resumen. Responde solo con el párrafo."""

QUESTIONS_PROMPT = """Eres un profesor universitario preparando preguntas de examen para que un estudiante practique.
Usando solo el CONTEXTO, genera {count} preguntas en español. {distribution}
Varía el tipo: definiciones, diferencias entre conceptos, aplicación a un ejemplo y preguntas de "¿por qué...?".
Evita preguntas triviales o que se respondan con una sola palabra.
Para cada pregunta escribe una respuesta modelo correcta según el contexto (de 1 a 4 oraciones)
e indica en "fragment" el número del fragmento que respalda la respuesta.
Las respuestas deben salir solo del contexto: no agregues ejemplos, supuestos ni datos propios.

CONTEXTO:
{context}
"""

# Referencias que el modelo a veces deja en el texto: "(Fragmento 2)", "(Fragmento 4 y Fragmento 8)"
FRAGMENT_REF = re.compile(r"\s*\((?:según el )?fragmentos? [^)]*\)", re.IGNORECASE)

DISTRIBUTION_SPREAD = "Haz exactamente una pregunta por cada fragmento, en orden (la pregunta 1 sobre el Fragmento 1, etc.)."
DISTRIBUTION_TOPIC = (
    "Todas las preguntas deben ser sobre el tema \"{topic}\". "
    "Ignora los fragmentos que no tengan relación con ese tema."
)

QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                    "fragment": {"type": "integer"},
                },
                "required": ["question", "answer", "fragment"],
            },
        }
    },
    "required": ["questions"],
}


def make_sections(pages: List[Tuple[int, str]], max_chars: int = SECTION_CHARS) -> List[dict]:
    """Agrupa páginas consecutivas en secciones de hasta max_chars, partiendo páginas muy largas."""
    sections: List[dict] = []
    current: List[str] = []
    start = end = None
    size = 0
    for page, text in pages:
        if not text:
            continue
        pieces = [text]
        if len(text) > max_chars:  # página enorme: partir por palabras
            words, pieces, buf = text.split(), [], ""
            for w in words:
                if len(buf) + len(w) + 1 > max_chars:
                    pieces.append(buf)
                    buf = ""
                buf = f"{buf} {w}".strip()
            pieces.append(buf)
        for piece in pieces:
            if current and size + len(piece) > max_chars:
                sections.append({"text": "\n".join(current), "page_start": start, "page_end": end})
                current, size, start = [], 0, None
            if start is None:
                start = page
            if end != page or not current:
                piece = f"[Página {page}] {piece}"
            end = page
            current.append(piece)
            size += len(piece)
    if current:
        sections.append({"text": "\n".join(current), "page_start": start, "page_end": end})
    return sections


def split_section(section: dict) -> List[dict]:
    """Parte una sección en dos mitades por palabras, conservando las marcas [Página N]."""
    words = section["text"].split(" ")
    mid = len(words) // 2
    halves = [" ".join(words[:mid]), " ".join(words[mid:])]
    result = []
    page = section["page_start"]
    for text in halves:
        marks = [int(m) for m in re.findall(r"\[Página (\d+)\]", text)]
        start = page if not text.lstrip().startswith("[Página") else marks[0]
        end = marks[-1] if marks else start
        if not text.lstrip().startswith("[Página"):
            text = f"[Página {start}] {text}"
        result.append({"text": text, "page_start": start, "page_end": end})
        page = end
    return result


def _pages_label(section: dict) -> str:
    if section["page_start"] == section["page_end"]:
        return f"página {section['page_start']}"
    return f"páginas {section['page_start']} a {section['page_end']}"


def _normalize_headings(notes: str) -> str:
    """Los temas de cada sección van como ###, debajo de '## Contenido'."""
    return re.sub(r"^#{1,6}\s*", "### ", notes.strip(), flags=re.M)


class StudyService:
    def __init__(self, ollama: OllamaService, embeddings: EmbeddingsService, db: Database):
        self.ollama = ollama
        self.embeddings = embeddings
        self.db = db

    # --- Resúmenes ---------------------------------------------------------

    def summarize(
        self,
        name: str,
        pages: List[Tuple[int, str]],
        on_progress: Callable[[str], None] = lambda _: None,
    ) -> str:
        sections = make_sections(pages)
        if not sections:
            raise ValueError("El documento no tiene texto para resumir")

        notes: List[str] = []
        for i, section in enumerate(sections, 1):
            on_progress(f"Leyendo sección {i} de {len(sections)}")
            notes.extend(self._section_notes(name, section))

        on_progress("Redactando la idea general")
        topics = [t.strip() for n in notes for t in re.findall(r"^#{2,4}\s*(.+)$", n, flags=re.M)]
        overview = ""
        if topics:
            prompt = OVERVIEW_PROMPT.format(name=name, topics="\n".join(f"- {t}" for t in topics[:60]))
            overview, truncated = self.ollama.generate(prompt, temperature=0.3, max_tokens=400, timeout=300)
            if truncated and "." in overview:  # no dejar una oración por la mitad
                overview = overview[: overview.rfind(".") + 1]

        body = "\n\n".join(_normalize_headings(n) for n in notes)
        parts = [f"## Idea general\n{overview}" if overview else "", f"## Contenido\n\n{body}"]
        return "\n\n".join(p for p in parts if p).strip()

    def _section_notes(self, name: str, section: dict) -> List[str]:
        """Notas de una sección; si se cortan por longitud, parte la sección en dos y reintenta."""
        prompt = SECTION_PROMPT.format(pages=_pages_label(section), name=name, text=section["text"])
        notes, truncated = self.ollama.generate(
            prompt, temperature=0.2, max_tokens=SECTION_NOTES_TOKENS, timeout=300
        )
        if not truncated:
            return [notes]
        if len(section["text"]) < MIN_SPLIT_CHARS:
            logger.warning("Notas truncadas en una sección corta de '%s'", name)
            return [notes]
        logger.info("Notas truncadas en %s de '%s'; partiendo la sección", _pages_label(section), name)
        result: List[str] = []
        for half in split_section(section):
            result.extend(self._section_notes(name, half))
        return result

    # --- Preguntas de práctica --------------------------------------------

    def _pick_chunks(
        self, count: int, subject_id: Optional[int], document_id: Optional[int], topic: Optional[str]
    ) -> List[dict]:
        if topic:
            k = min(count + 2, QUESTION_CHUNKS)
            return self.embeddings.search(topic, k, subject_id=subject_id, document_id=document_id)

        sql = (
            "SELECT c.id, c.document_id, c.text, c.page_start, c.page_end, d.filename "
            "FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.status = 'completed'"
        )
        params: list = []
        if document_id is not None:
            sql += " AND c.document_id = ?"
            params.append(document_id)
        if subject_id is not None:
            sql += " AND d.subject_id = ?"
            params.append(subject_id)
        rows = self.db.fetchall(sql + " ORDER BY c.document_id, c.chunk_index", params)
        if len(rows) <= count:
            return rows
        # Un fragmento al azar de cada tramo del material, para cubrirlo de principio a fin
        step = len(rows) / count
        return [rows[int(i * step) + random.randrange(max(1, int(step)))] for i in range(count)]

    def generate_questions(
        self,
        count: int = 5,
        subject_id: Optional[int] = None,
        document_id: Optional[int] = None,
        topic: Optional[str] = None,
    ) -> List[dict]:
        chunks = self._pick_chunks(count, subject_id, document_id, topic)
        if not chunks:
            if topic:
                raise LookupError(f"No se encontró material sobre \"{topic}\"")
            raise LookupError("No hay documentos procesados para generar preguntas")

        context = "\n---\n".join(f"[Fragmento {i}]\n{c['text']}" for i, c in enumerate(chunks, 1))
        distribution = DISTRIBUTION_TOPIC.format(topic=topic) if topic else DISTRIBUTION_SPREAD
        prompt = QUESTIONS_PROMPT.format(count=count, distribution=distribution, context=context)
        data = self.ollama.generate_json(
            prompt, QUESTIONS_SCHEMA, temperature=0.5, max_tokens=250 * count + 200, timeout=300
        )

        questions = []
        for q in data.get("questions", [])[:count]:
            if not str(q.get("question", "")).strip() or not str(q.get("answer", "")).strip():
                continue
            idx = q.get("fragment")
            chunk = chunks[idx - 1] if isinstance(idx, int) and 1 <= idx <= len(chunks) else None
            questions.append(
                {
                    "question": q["question"].strip(),
                    "answer": FRAGMENT_REF.sub("", q["answer"]).strip(),
                    "source": source_label(chunk) if chunk else None,
                    "document_id": chunk["document_id"] if chunk else None,
                }
            )
        if not questions:
            raise ValueError("El modelo no generó preguntas válidas; intenta de nuevo")
        return questions
