"""Extracción de texto y chunking de PDFs."""
import os
import re
from typing import List, Tuple

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# Una página con menos caracteres que esto se considera sin texto (escaneada o solo imágenes)
MIN_PAGE_CHARS = 20

SCANNED_MESSAGE = (
    "El PDF no tiene texto seleccionable (parece escaneado o son imágenes). "
    "Pásalo por un OCR (por ejemplo, 'Guardar como PDF con texto' en Adobe Scan, "
    "Google Drive → Abrir con Documentos, u ocrmypdf) y vuelve a subirlo."
)


def _clean(text: str) -> str:
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # une palabras cortadas con guion al final de línea
    return re.sub(r"\s+", " ", text).strip()


class PDFProcessor:
    def extract_pages(self, pdf_path: str) -> List[Tuple[int, str]]:
        """Retorna [(numero_de_pagina, texto)] empezando en 1; páginas sin texto quedan con ''."""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"No existe el archivo: {pdf_path}")
        try:
            reader = PdfReader(pdf_path)
            pages = []
            for i, page in enumerate(reader.pages, start=1):
                text = _clean(page.extract_text() or "")
                pages.append((i, text if len(text) >= MIN_PAGE_CHARS else ""))
        except (PdfReadError, OSError, ValueError) as e:
            raise ValueError(f"PDF corrupto o ilegible: {e}") from e

        if not any(text for _, text in pages):
            raise ValueError(SCANNED_MESSAGE)
        return pages

    def extract_text(self, pdf_path: str) -> str:
        return " ".join(text for _, text in self.extract_pages(pdf_path) if text)

    def split_chunks(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Divide el texto en chunks de ~chunk_size caracteres respetando palabras."""
        return [c["text"] for c in self.split_pages([(1, text)], chunk_size, overlap)]

    def split_pages(self, pages: List[Tuple[int, str]], chunk_size: int = 500, overlap: int = 50) -> List[dict]:
        """Chunking que cruza páginas y recuerda en qué páginas cae cada chunk.

        Cada chunk nuevo comienza con las últimas palabras del anterior que
        suman ~overlap caracteres. Retorna [{text, page_start, page_end}].
        """
        if overlap >= chunk_size:
            raise ValueError("overlap debe ser menor que chunk_size")
        words = [(w, page) for page, text in pages for w in text.split()]
        if not words:
            return []

        chunks: List[dict] = []
        current: List[Tuple[str, int]] = []
        length = 0

        def emit():
            chunks.append(
                {"text": " ".join(w for w, _ in current), "page_start": current[0][1], "page_end": current[-1][1]}
            )

        for item in words:
            word = item[0]
            added = len(word) + (1 if current else 0)
            if current and length + added > chunk_size:
                emit()
                # Arrastrar palabras finales como solapamiento
                tail: List[Tuple[str, int]] = []
                tail_len = 0
                for prev in reversed(current):
                    extra = len(prev[0]) + (1 if tail else 0)
                    if tail_len + extra > overlap:
                        break
                    tail.insert(0, prev)
                    tail_len += extra
                current = tail
                length = tail_len
                added = len(word) + (1 if current else 0)
            current.append(item)
            length += added
        if current:
            emit()
        return chunks

    def validate_pdf(self, file_path: str) -> bool:
        try:
            if not os.path.isfile(file_path) or not file_path.lower().endswith(".pdf"):
                return False
            PdfReader(file_path)
            return True
        except Exception:
            return False
