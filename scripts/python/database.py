import sqlite3
import os
import time
import threading


# In production, sqlite-vec will be loaded from python_libs, which is
# added to sys.path via the Houdini-LLM.json package file.

try:
    import sqlite_vec

    HAS_SQLITE_VEC = True
except ImportError:
    HAS_SQLITE_VEC = False


class _ConnectionPool:
    """
    Thread-safe SQLite connection pool.
    Caches one connection per (db_path, thread) pair to eliminate
    repeated sqlite3.connect() overhead. Connections are reused
    across function calls within the same thread.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # Key: (db_path, thread_id) -> sqlite3.Connection
        self._connections = {}

    def get(self, db_path):
        """Return a cached connection for this db_path + current thread."""
        key = (db_path, threading.get_ident())
        with self._lock:
            conn = self._connections.get(key)
            if conn is not None:
                return conn
        # Create outside the lock to avoid holding it during I/O
        conn = sqlite3.connect(db_path, check_same_thread=False)
        if HAS_SQLITE_VEC:
            try:
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
            except AttributeError:
                # Some python environments might have load_extension disabled at compilation
                pass

        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -2000")  # 2 MB cache
        with self._lock:
            # Double-check: another thread may have raced us (unlikely but safe)
            existing = self._connections.get(key)
            if existing is not None:
                conn.close()
                return existing
            self._connections[key] = conn
        return conn

    def close_all(self):
        """Close every cached connection. Call on app shutdown."""
        with self._lock:
            for conn in self._connections.values():
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections.clear()


# Module-level singleton
_pool = _ConnectionPool()


def get_connection(db_path):
    """Returns a pooled, thread-safe connection to the SQLite database."""
    return _pool.get(db_path)


def close_all_connections():
    """Cleanly shuts down all cached connections. Call on app exit."""
    _pool.close_all()


def init_db(memory_dir):
    """Initializes the SQLite database and creates tables if they don't exist."""
    db_path = os.path.join(memory_dir, "houdini_ai_agent.db")
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Create Sessions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            summary TEXT,
            token_limit INTEGER,
            created_at REAL,
            updated_at REAL
        )
    """)

    # Create Messages Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            timestamp REAL,
            FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
        )
    """)

    # Indexes for fast lookups
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_session_ts ON messages(session_id, timestamp ASC, id ASC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC)"
    )

    if HAS_SQLITE_VEC:
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS learned_skills USING vec0(
                id INTEGER PRIMARY KEY,
                embedding float[1536]
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learned_skills_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT,
                code TEXT,
                created_at REAL
            )
        """)
        from rag.vector_db import create_docs_table

        create_docs_table(db_path)

    conn.commit()
    return db_path


def save_learned_skill(db_path, description, code, embedding):
    if not HAS_SQLITE_VEC:
        return False
    conn = get_connection(db_path)
    now = time.time()

    # Insert metadata
    cursor = conn.execute(
        "INSERT INTO learned_skills_meta (description, code, created_at) VALUES (?, ?, ?)",
        (description, code, now),
    )
    skill_id = cursor.lastrowid

    # Insert vector
    import struct

    # Serialize the float list into bytes
    embedding_bytes = struct.pack(f"{len(embedding)}f", *embedding)
    conn.execute(
        "INSERT INTO learned_skills (id, embedding) VALUES (?, ?)",
        (skill_id, embedding_bytes),
    )
    conn.commit()
    return skill_id


def delete_learned_skill(db_path, skill_id):
    if not HAS_SQLITE_VEC:
        return False
    conn = get_connection(db_path)
    conn.execute("DELETE FROM learned_skills_meta WHERE id = ?", (skill_id,))
    conn.execute("DELETE FROM learned_skills WHERE id = ?", (skill_id,))
    conn.commit()
    return True


def get_all_learned_skills(db_path):
    if not HAS_SQLITE_VEC:
        return []
    conn = get_connection(db_path)
    cursor = conn.execute("SELECT * FROM learned_skills_meta ORDER BY created_at DESC")
    return [dict(row) for row in cursor.fetchall()]


def search_learned_skills(db_path, query_embedding, limit=3):
    if not HAS_SQLITE_VEC:
        return []
    conn = get_connection(db_path)
    import struct

    query_bytes = struct.pack(f"{len(query_embedding)}f", *query_embedding)

    # vec_distance_L2 search
    cursor = conn.execute(
        """
        SELECT m.id, m.description, m.code, vec_distance_L2(v.embedding, ?) as distance
        FROM learned_skills v
        JOIN learned_skills_meta m ON v.id = m.id
        ORDER BY distance ASC
        LIMIT ?
        """,
        (query_bytes, limit),
    )
    return [dict(row) for row in cursor.fetchall()]


def create_session(db_path, session_id, title="New Chat", token_limit=50000):
    conn = get_connection(db_path)
    now = time.time()
    conn.execute(
        """
        INSERT INTO sessions (id, title, summary, token_limit, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (session_id, title, "", token_limit, now, now),
    )
    conn.commit()


def get_all_sessions(db_path):
    """Returns a list of dicts: [{'id': 'abc', 'title': 'My Chat', 'mtime': 123}]"""
    conn = get_connection(db_path)
    cursor = conn.execute(
        "SELECT id, title, updated_at as mtime FROM sessions ORDER BY updated_at DESC"
    )
    return [
        {"id": row["id"], "title": row["title"], "mtime": row["mtime"]}
        for row in cursor.fetchall()
    ]


def delete_session(db_path, session_id):
    conn = get_connection(db_path)
    cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    rows_deleted = cursor.rowcount
    conn.commit()
    return rows_deleted > 0


def rename_session(db_path, session_id, new_title):
    conn = get_connection(db_path)
    conn.execute(
        """
        UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?
    """,
        (new_title, time.time(), session_id),
    )
    conn.commit()


def update_session_timestamp(db_path, session_id):
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?", (time.time(), session_id)
    )
    conn.commit()


def get_session_details(db_path, session_id):
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def update_session_summary(db_path, session_id, new_summary):
    conn = get_connection(db_path)
    conn.execute(
        """
        UPDATE sessions SET summary = ?, updated_at = ? WHERE id = ?
    """,
        (new_summary, time.time(), session_id),
    )
    conn.commit()


def set_session_token_limit(db_path, session_id, limit):
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE sessions SET token_limit = ? WHERE id = ?", (limit, session_id)
    )
    conn.commit()


def add_message(db_path, session_id, role, content):
    conn = get_connection(db_path)
    now = time.time()
    conn.execute(
        """
        INSERT INTO messages (session_id, role, content, timestamp)
        VALUES (?, ?, ?, ?)
    """,
        (session_id, role, content, now),
    )
    conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    conn.commit()


def get_messages(db_path, session_id):
    """Returns a list of all messages for the session, ordered chronologically."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        "SELECT id, role, content FROM messages WHERE session_id = ? ORDER BY timestamp ASC, id ASC",
        (session_id,),
    )
    return [
        {"id": row["id"], "role": row["role"], "content": row["content"]}
        for row in cursor.fetchall()
    ]


def delete_oldest_messages(db_path, session_id, keep_last_n):
    """Deletes all messages except the last N messages for a session."""
    conn = get_connection(db_path)

    # Find the IDs of the messages we want to KEEP
    cursor = conn.execute(
        """
        SELECT id FROM messages
        WHERE session_id = ?
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
    """,
        (session_id, keep_last_n),
    )

    keep_ids = [row["id"] for row in cursor.fetchall()]
    if not keep_ids:
        return

    placeholders = ",".join(["?"] * len(keep_ids))
    conn.execute(
        f"""
        DELETE FROM messages
        WHERE session_id = ? AND id NOT IN ({placeholders})
    """,
        [session_id] + keep_ids,
    )

    conn.commit()
