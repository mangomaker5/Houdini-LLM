import time
from database import get_connection, HAS_SQLITE_VEC


def create_docs_table(db_path):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS houdini_docs USING vec0(
            id INTEGER PRIMARY KEY,
            embedding float[1536]
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS houdini_docs_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT,
            url TEXT,
            created_at REAL
        )
    """)
    conn.commit()


def insert_houdini_doc(db_path, title, content, url, embedding):
    if not HAS_SQLITE_VEC:
        return False
    conn = get_connection(db_path)
    now = time.time()

    # Insert metadata
    cursor = conn.execute(
        "INSERT INTO houdini_docs_meta (title, content, url, created_at) VALUES (?, ?, ?, ?)",
        (title, content, url, now),
    )
    doc_id = cursor.lastrowid

    import struct

    # Serialize the float list into bytes
    embedding_bytes = struct.pack(f"{len(embedding)}f", *embedding)
    conn.execute(
        "INSERT INTO houdini_docs (id, embedding) VALUES (?, ?)",
        (doc_id, embedding_bytes),
    )
    conn.commit()
    return doc_id


def search_houdini_docs(db_path, query_embedding, limit=5):
    if not HAS_SQLITE_VEC:
        return []
    conn = get_connection(db_path)
    import struct

    query_bytes = struct.pack(f"{len(query_embedding)}f", *query_embedding)

    # vec_distance_L2 search
    cursor = conn.execute(
        """
        SELECT m.id, m.title, m.content, m.url, vec_distance_L2(v.embedding, ?) as distance
        FROM houdini_docs v
        JOIN houdini_docs_meta m ON v.id = m.id
        ORDER BY distance ASC
        LIMIT ?
        """,
        (query_bytes, limit),
    )
    return [dict(row) for row in cursor.fetchall()]
