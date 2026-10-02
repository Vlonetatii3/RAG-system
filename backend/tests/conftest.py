import os
import sys
import tempfile

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

# Evitar que importar app.py cree la BD real
_TMP = tempfile.mkdtemp(prefix="rag_test_")
os.environ["DATABASE_PATH"] = os.path.join(_TMP, "import.db")
os.environ["UPLOADS_PATH"] = os.path.join(_TMP, "uploads")
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"  # puerto cerrado: nunca hablar con Ollama real


def make_pdf(path: str, lines: list[str]) -> str:
    """Genera un PDF mínimo válido con una línea de texto por renglón."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    ops = ["BT", "/F1 11 Tf", "14 TL", "50 780 Td"]
    for line in lines:
        ops.append(f"({esc(line)}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    with open(path, "wb") as f:
        f.write(out)
    return path


class FakeOllama:
    """Ollama simulado: embeddings por bolsa de palabras (determinísticos)."""

    DIM = 64

    def __init__(self, connected: bool = True):
        self.connected = connected
        self.model = "mistral"
        self.prompts: list[str] = []

    def check_connection(self) -> bool:
        return self.connected

    def list_models(self) -> list[str]:
        if not self.connected:
            raise ConnectionError("Ollama desconectado")
        return ["mistral:latest", "qwen2.5:7b", "nomic-embed-text:latest"]

    def is_model_available(self, name: str) -> bool:
        return self.connected and name in ("mistral", "nomic-embed-text")

    def embed(self, text: str, model: str) -> list[float]:
        vec = [0.0] * self.DIM
        for word in text.lower().split():
            if word.startswith("search_"):  # ignorar el prefijo de tarea de nomic
                continue
            vec[sum(map(ord, word.strip(".,¿?"))) % self.DIM] += 1.0
        vec[0] += 0.01
        return vec

    def embed_batch(self, texts: list[str], model: str) -> list[list[float]]:
        return [self.embed(t, model) for t in texts]

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 512, json_schema=None, timeout=None):
        self.prompts.append(prompt)
        if "NOTAS:" in prompt:
            return "### Tema simulado\n- **concepto**: definición (pág. 1)", False
        return "Respuesta simulada", False

    def generate_answer(self, prompt: str, temperature: float = 0.7, **kwargs) -> str:
        return self.generate(prompt, temperature)[0]

    def generate_json(self, prompt: str, schema: dict, **kwargs) -> dict:
        self.prompts.append(prompt)
        return {
            "questions": [
                {"question": "¿Qué es X? ", "answer": "X es Y (Fragmento 1).", "fragment": 1},
                {"question": "", "answer": "descartada", "fragment": 1},
                {"question": "¿Por qué Z?", "answer": "Porque W.", "fragment": 99},
            ]
        }


@pytest.fixture
def fake_ollama():
    return FakeOllama()


@pytest.fixture
def test_config(tmp_path):
    from config import Config

    class TestConfig(Config):
        DATABASE_PATH = str(tmp_path / "test.db")
        UPLOADS_PATH = str(tmp_path / "uploads")

    return TestConfig


@pytest.fixture
def app(test_config, fake_ollama):
    from app import create_app

    application = create_app(test_config, ollama_service=fake_ollama)
    yield application
    application.extensions["rag"]["executor"].shutdown(wait=True)
    application.extensions["rag"]["summary_executor"].shutdown(wait=True)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sample_pdf(tmp_path):
    lines = [
        "El sistema solar tiene ocho planetas que orbitan alrededor del sol.",
        "Jupiter es el planeta mas grande del sistema solar.",
        "La fotosintesis es el proceso por el cual las plantas producen energia.",
    ] * 10
    return make_pdf(str(tmp_path / "sample.pdf"), lines)
