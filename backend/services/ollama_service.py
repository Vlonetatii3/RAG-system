"""Cliente HTTP para Ollama."""
import json
import logging
from typing import List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 16


class OllamaError(Exception):
    """Error de comunicación con Ollama."""


class OllamaService:
    def __init__(
        self, base_url: str, model: str, timeout: int = 30, keep_alive: str = "30m", num_ctx: int = 8192
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.keep_alive = keep_alive  # cuánto tiempo Ollama mantiene el modelo cargado en memoria
        # Ventana de contexto (prompt + respuesta). Si el prompt no entra, Ollama descarta el
        # principio sin avisar, y ahí están las instrucciones.
        self.num_ctx = num_ctx

    def list_models(self) -> List[str]:
        resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
        resp.raise_for_status()
        return [m.get("name", "") for m in resp.json().get("models", [])]

    @staticmethod
    def model_in(model_name: str, names: List[str]) -> bool:
        """Acepta 'mistral' o 'mistral:latest'."""
        wanted = model_name if ":" in model_name else f"{model_name}:latest"
        return any(n == model_name or n == wanted for n in names)

    def check_connection(self) -> bool:
        try:
            self.list_models()
            return True
        except Exception:
            return False

    def is_model_available(self, model_name: str) -> bool:
        """True si el modelo está descargado."""
        try:
            return self.model_in(model_name, self.list_models())
        except Exception:
            return False

    def _post(self, path: str, payload: dict, timeout: int, what: str) -> dict:
        try:
            resp = requests.post(f"{self.base_url}{path}", json=payload, timeout=timeout)
        except requests.Timeout as e:
            raise OllamaError(f"Ollama no respondió en {timeout}s ({what})") from e
        except requests.ConnectionError as e:
            raise OllamaError(f"No se pudo conectar a Ollama en {self.base_url}") from e
        if resp.status_code != 200:
            raise OllamaError(f"Ollama respondió {resp.status_code} ({what}): {resp.text[:200]}")
        return resp.json()

    def generate_answer(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
        json_schema: Optional[dict] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """Genera texto. Con json_schema, Ollama restringe la salida a ese esquema JSON."""
        return self.generate(prompt, temperature, max_tokens, json_schema, timeout)[0]

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
        json_schema: Optional[dict] = None,
        timeout: Optional[int] = None,
    ) -> Tuple[str, bool]:
        """Como generate_answer, pero también indica si la salida se cortó por max_tokens."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": self.num_ctx},
        }
        if json_schema:
            payload["format"] = json_schema
        data = self._post("/api/generate", payload, timeout or self.timeout, "generación")
        return data.get("response", "").strip(), data.get("done_reason") == "length"

    def generate_json(self, prompt: str, schema: dict, **kwargs) -> dict:
        raw = self.generate_answer(prompt, json_schema=schema, **kwargs)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise OllamaError("El modelo devolvió una respuesta que no es JSON válido; intenta de nuevo") from e

    def embed(self, text: str, model: str) -> List[float]:
        return self.embed_batch([text], model)[0]

    def embed_batch(self, texts: List[str], model: str) -> List[List[float]]:
        """Embeddings en lotes vía /api/embed (~3x más rápido que uno por uno)."""
        vectors: List[List[float]] = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            payload = {"model": model, "input": batch, "keep_alive": self.keep_alive}
            what = f"embeddings con '{model}'"
            try:
                data = self._post("/api/embed", payload, self.timeout, what)
            except OllamaError as e:
                if not isinstance(e.__cause__, requests.Timeout):
                    raise
                # La primera llamada puede tardar mientras Ollama carga el modelo en memoria
                logger.info("Timeout generando embeddings; reintentando (¿modelo cargándose?)")
                data = self._post("/api/embed", payload, self.timeout * 3, what)
            embeddings = data.get("embeddings") or []
            if len(embeddings) != len(batch):
                raise OllamaError(f"Ollama devolvió {len(embeddings)} embeddings para {len(batch)} textos")
            vectors.extend(embeddings)
        return vectors
