"""Acceso a SQLite.

Cada operación abre su propia conexión: SQLite no permite compartir una
conexión entre hilos y el procesamiento de PDFs corre en hilos de fondo.
"""
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Optional

DEFAULT_SUBJECT = "General"

SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'processing', -- processing, completed, failed
    error TEXT,
    page_count INTEGER,
    pages_without_text INTEGER DEFAULT 0,
    summary TEXT,
    summary_status TEXT, -- NULL, processing, completed, failed
    summary_progress TEXT, -- p. ej. "3/8"
    summary_error TEXT,
    UNIQUE (subject_id, filename),
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL, -- 'user' o 'assistant'
    content TEXT NOT NULL,
    context_chunks TEXT, -- JSON con IDs de chunks usados
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_documents_subject_id ON documents(subject_id);
"""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self):
        """Conexión con commit/rollback automático y cierre garantizado."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Crea las tablas si no existen y migra bases de la versión anterior (idempotente)."""
        self._migrate_v1()
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)

    def _migrate_v1(self) -> None:
        """v1 no tenía materias ni páginas, y filename era único global.

        SQLite no permite quitar un UNIQUE con ALTER TABLE, así que la tabla
        documents se reconstruye. Las FK se desactivan para que DROP TABLE no
        borre en cascada los chunks.
        """
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)  # transacción manual
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "documents" not in tables or "subject_id" in _columns(conn, "documents"):
                return
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("BEGIN")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS subjects (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name TEXT NOT NULL UNIQUE COLLATE NOCASE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute("INSERT OR IGNORE INTO subjects (name) VALUES (?)", (DEFAULT_SUBJECT,))
            subject_id = conn.execute("SELECT id FROM subjects WHERE name = ?", (DEFAULT_SUBJECT,)).fetchone()[0]
            # Procedimiento oficial de SQLite: crear nueva → copiar → borrar vieja → renombrar nueva.
            # (Renombrar la vieja reescribiría las FK de chunks hacia el nombre viejo.)
            documents_ddl = SCHEMA.split("CREATE TABLE IF NOT EXISTS documents")[1].split(";")[0]
            conn.execute("CREATE TABLE documents_new" + documents_ddl)
            has_error = "error" in _columns(conn, "documents")
            conn.execute(
                "INSERT INTO documents_new (id, subject_id, filename, file_path, upload_date, status, error) "
                f"SELECT id, ?, filename, file_path, upload_date, status, {'error' if has_error else 'NULL'} "
                "FROM documents",
                (subject_id,),
            )
            conn.execute("DROP TABLE documents")
            conn.execute("ALTER TABLE documents_new RENAME TO documents")
            if "chunks" in tables:
                cols = _columns(conn, "chunks")
                for col in ("page_start", "page_end"):
                    if col not in cols:
                        conn.execute(f"ALTER TABLE chunks ADD COLUMN {col} INTEGER")
            if "conversations" in tables and "subject_id" not in _columns(conn, "conversations"):
                conn.execute("ALTER TABLE conversations ADD COLUMN subject_id INTEGER")
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def default_subject_id(self) -> int:
        self.execute("INSERT OR IGNORE INTO subjects (name) VALUES (?)", (DEFAULT_SUBJECT,))
        return self.fetchone("SELECT id FROM subjects WHERE name = ?", (DEFAULT_SUBJECT,))["id"]

    def execute(self, query: str, params: Iterable[Any] = ()) -> int:
        """Ejecuta una sentencia de escritura y retorna lastrowid."""
        with self.connection() as conn:
            cur = conn.execute(query, tuple(params))
            return cur.lastrowid

    def executemany(self, query: str, rows: Iterable[Iterable[Any]]) -> None:
        with self.connection() as conn:
            conn.executemany(query, rows)

    def fetchone(self, query: str, params: Iterable[Any] = ()) -> Optional[dict]:
        with self.connection() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
            return dict(row) if row else None

    def fetchall(self, query: str, params: Iterable[Any] = ()) -> list[dict]:
        with self.connection() as conn:
            return [dict(r) for r in conn.execute(query, tuple(params)).fetchall()]

    def check(self) -> bool:
        try:
            self.fetchone("SELECT COUNT(*) AS n FROM documents")
            return True
        except sqlite3.Error:
            return False

    def close(self) -> None:
        """Las conexiones se cierran tras cada operación; se mantiene por compatibilidad."""
        return None
