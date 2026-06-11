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
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            timestamp REAL,
            FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
        )
    """)

    # Migration: add token columns to existing messages tables
    for col_sql in [
        "ALTER TABLE messages ADD COLUMN prompt_tokens INTEGER DEFAULT 0",
        "ALTER TABLE messages ADD COLUMN completion_tokens INTEGER DEFAULT 0",
    ]:
        try:
            cursor.execute(col_sql)
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Usage Log Table — global billing tracker across all sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            call_type TEXT NOT NULL,
            model TEXT,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            cost REAL DEFAULT 0.0,
            timestamp REAL
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
        import memory_db

        memory_db.create_memory_tables(db_path)

        from rag.vector_db import create_docs_table

        create_docs_table(db_path)

    conn.commit()
    return db_path


def create_session(db_path, session_id, title="New Chat", token_limit=128000):
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


def add_message(
    db_path, session_id, role, content, prompt_tokens=0, completion_tokens=0
):
    conn = get_connection(db_path)
    now = time.time()
    conn.execute(
        """
        INSERT INTO messages (session_id, role, content, prompt_tokens, completion_tokens, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (session_id, role, content, prompt_tokens, completion_tokens, now),
    )
    conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    conn.commit()


def get_messages(db_path, session_id):
    """Returns a list of all messages for the session, ordered chronologically."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        "SELECT id, role, content, prompt_tokens, completion_tokens FROM messages WHERE session_id = ? ORDER BY timestamp ASC, id ASC",
        (session_id,),
    )
    return [
        {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "prompt_tokens": row["prompt_tokens"] or 0,
            "completion_tokens": row["completion_tokens"] or 0,
        }
        for row in cursor.fetchall()
    ]


def log_usage(
    db_path,
    session_id,
    call_type,
    model,
    prompt_tokens,
    completion_tokens,
    total_tokens,
    cost,
):
    """Logs a single API call to the global usage tracker for billing."""
    conn = get_connection(db_path)
    now = time.time()
    conn.execute(
        """
        INSERT INTO usage_log (session_id, call_type, model, prompt_tokens, completion_tokens, total_tokens, cost, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            session_id,
            call_type,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cost,
            now,
        ),
    )
    conn.commit()


def get_global_usage(db_path):
    """Returns cumulative token usage and cost across ALL sessions."""
    conn = get_connection(db_path)
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(prompt_tokens), 0) as total_prompt,
            COALESCE(SUM(completion_tokens), 0) as total_completion,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(cost), 0.0) as total_cost,
            COUNT(*) as total_calls
        FROM usage_log
    """
    ).fetchone()
    return (
        dict(row)
        if row
        else {
            "total_prompt": 0,
            "total_completion": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "total_calls": 0,
        }
    )


def delete_oldest_messages(db_path, session_id, keep_last_n):
    """Deletes old messages while preserving the last N and the first user message.

    The first user message is the session's 'anchor' — it captures the original
    intent/goal and must never be deleted during compaction.
    """
    conn = get_connection(db_path)

    # 1. Find the very first user message (the session anchor)
    anchor_row = conn.execute(
        """
        SELECT id FROM messages
        WHERE session_id = ? AND role = 'user'
        ORDER BY timestamp ASC, id ASC
        LIMIT 1
    """,
        (session_id,),
    ).fetchone()

    anchor_id = anchor_row["id"] if anchor_row else None

    # 2. Find the IDs of the most recent N messages to KEEP
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

    # 3. Always protect the anchor
    if anchor_id is not None and anchor_id not in keep_ids:
        keep_ids.append(anchor_id)

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
