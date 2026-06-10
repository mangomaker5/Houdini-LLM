import time
import struct
from database import get_connection, HAS_SQLITE_VEC


def create_memory_tables(db_path):
    conn = get_connection(db_path)
    cursor = conn.cursor()

    if HAS_SQLITE_VEC:
        # Learned Skills Tables
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
        # FTS5 Table for keyword search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS learned_skills_fts USING fts5(
                description, 
                code
            )
        """)

        # Anti-Patterns Tables
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS anti_patterns USING vec0(
                id INTEGER PRIMARY KEY,
                embedding float[1536]
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS anti_patterns_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_type TEXT,
                traceback_str TEXT,
                failed_code TEXT,
                fix_description TEXT,
                created_at REAL
            )
        """)
        # FTS5 Table for anti-patterns
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS anti_patterns_fts USING fts5(
                error_type,
                traceback_str,
                failed_code,
                fix_description
            )
        """)
    conn.commit()


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
    embedding_bytes = struct.pack(f"{len(embedding)}f", *embedding)
    conn.execute(
        "INSERT INTO learned_skills (id, embedding) VALUES (?, ?)",
        (skill_id, embedding_bytes),
    )

    # Insert FTS5
    conn.execute(
        "INSERT INTO learned_skills_fts (rowid, description, code) VALUES (?, ?, ?)",
        (skill_id, description, code),
    )
    conn.commit()
    return skill_id


def check_skill_duplicate(db_path, embedding, threshold=0.15):
    """Checks if a nearly identical skill exists (distance < threshold)"""
    if not HAS_SQLITE_VEC:
        return None
    conn = get_connection(db_path)
    embedding_bytes = struct.pack(f"{len(embedding)}f", *embedding)

    row = conn.execute(
        """
        SELECT id, vec_distance_L2(embedding, ?) as distance
        FROM learned_skills
        WHERE distance < ?
        ORDER BY distance ASC
        LIMIT 1
        """,
        (embedding_bytes, threshold),
    ).fetchone()

    return dict(row) if row else None


def update_learned_skill(db_path, skill_id, description, code, embedding):
    if not HAS_SQLITE_VEC:
        return False
    conn = get_connection(db_path)
    now = time.time()

    conn.execute(
        "UPDATE learned_skills_meta SET description=?, code=?, created_at=? WHERE id=?",
        (description, code, now, skill_id),
    )

    embedding_bytes = struct.pack(f"{len(embedding)}f", *embedding)
    conn.execute(
        "UPDATE learned_skills SET embedding=? WHERE id=?", (embedding_bytes, skill_id)
    )

    conn.execute("DELETE FROM learned_skills_fts WHERE rowid=?", (skill_id,))
    conn.execute(
        "INSERT INTO learned_skills_fts (rowid, description, code) VALUES (?, ?, ?)",
        (skill_id, description, code),
    )
    conn.commit()
    return True


def delete_learned_skill(db_path, skill_id):
    if not HAS_SQLITE_VEC:
        return False
    conn = get_connection(db_path)
    conn.execute("DELETE FROM learned_skills_meta WHERE id = ?", (skill_id,))
    conn.execute("DELETE FROM learned_skills WHERE id = ?", (skill_id,))
    conn.execute("DELETE FROM learned_skills_fts WHERE rowid = ?", (skill_id,))
    conn.commit()
    return True


def get_all_learned_skills(db_path):
    if not HAS_SQLITE_VEC:
        return []
    conn = get_connection(db_path)
    cursor = conn.execute("SELECT * FROM learned_skills_meta ORDER BY created_at DESC")
    return [dict(row) for row in cursor.fetchall()]


def _sanitize_fts_query(raw_text):
    """Strips all FTS5 reserved characters and builds a safe OR-prefixed query.

    Houdini help files contain: [Hom:hou.Node#geometry], ::method::,
    @parameters, {{{ code }}}, etc. All of these contain FTS5 special
    characters that would crash a MATCH clause.
    """
    import re

    # Strip every character that FTS5 treats as syntax
    cleaned = re.sub(r'["\':;(){}\[\]@#^~*+\-/\\<>!.,]', " ", raw_text)
    # Collapse whitespace
    words = [w for w in cleaned.split() if len(w) > 2]
    if not words:
        return None
    # Build prefix-match query: each word becomes a prefix term joined by OR
    return " OR ".join(f"{w}*" for w in words[:12])


def _reciprocal_rank_fusion(vec_results, fts_results, k=60):
    scores = {}

    for rank, row in enumerate(vec_results):
        doc_id = row["id"]
        if doc_id not in scores:
            scores[doc_id] = {"score": 0.0, "data": row}
        scores[doc_id]["score"] += 1.0 / (k + rank)

    for rank, row in enumerate(fts_results):
        doc_id = row["id"]
        if doc_id not in scores:
            scores[doc_id] = {"score": 0.0, "data": row}
        scores[doc_id]["score"] += 1.0 / (k + rank)

    ranked = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return [item["data"] for item in ranked]


def search_learned_skills(db_path, query_embedding, query_text, limit=3, threshold=1.0):
    """Hybrid search: Vector L2 + FTS5 blended via RRF."""
    if not HAS_SQLITE_VEC:
        return []
    conn = get_connection(db_path)
    query_bytes = struct.pack(f"{len(query_embedding)}f", *query_embedding)

    # 1. Vector Search (with threshold)
    vec_cursor = conn.execute(
        """
        SELECT m.id, m.description, m.code, vec_distance_L2(v.embedding, ?) as distance
        FROM learned_skills v
        JOIN learned_skills_meta m ON v.id = m.id
        WHERE distance <= ?
        ORDER BY distance ASC
        LIMIT ?
        """,
        (query_bytes, threshold, limit * 2),
    )
    vec_results = [dict(row) for row in vec_cursor.fetchall()]

    # 2. FTS5 Search
    fts_results = []
    fts_query = _sanitize_fts_query(query_text)
    if fts_query:
        try:
            fts_cursor = conn.execute(
                """
                SELECT m.id, m.description, m.code, 0.0 as distance
                FROM learned_skills_fts f
                JOIN learned_skills_meta m ON f.rowid = m.id
                WHERE learned_skills_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit * 2),
            )
            fts_results = [dict(row) for row in fts_cursor.fetchall()]
        except Exception as e:
            print(f"FTS Search warning: {e}")

    # 3. Blend via RRF
    fused_results = _reciprocal_rank_fusion(vec_results, fts_results)

    return fused_results[:limit]


def save_anti_pattern(
    db_path, error_type, traceback_str, failed_code, fix_description, embedding
):
    if not HAS_SQLITE_VEC:
        return False
    conn = get_connection(db_path)
    now = time.time()

    cursor = conn.execute(
        "INSERT INTO anti_patterns_meta (error_type, traceback_str, failed_code, fix_description, created_at) VALUES (?, ?, ?, ?, ?)",
        (error_type, traceback_str, failed_code, fix_description, now),
    )
    ap_id = cursor.lastrowid

    embedding_bytes = struct.pack(f"{len(embedding)}f", *embedding)
    conn.execute(
        "INSERT INTO anti_patterns (id, embedding) VALUES (?, ?)",
        (ap_id, embedding_bytes),
    )

    conn.execute(
        "INSERT INTO anti_patterns_fts (rowid, error_type, traceback_str, failed_code, fix_description) VALUES (?, ?, ?, ?, ?)",
        (ap_id, error_type, traceback_str, failed_code, fix_description),
    )
    conn.commit()
    return ap_id


def search_anti_patterns(db_path, query_embedding, query_text, limit=3, threshold=1.0):
    if not HAS_SQLITE_VEC:
        return []
    conn = get_connection(db_path)
    query_bytes = struct.pack(f"{len(query_embedding)}f", *query_embedding)

    vec_cursor = conn.execute(
        """
        SELECT m.id, m.error_type, m.traceback_str, m.failed_code, m.fix_description, vec_distance_L2(v.embedding, ?) as distance
        FROM anti_patterns v
        JOIN anti_patterns_meta m ON v.id = m.id
        WHERE distance <= ?
        ORDER BY distance ASC
        LIMIT ?
        """,
        (query_bytes, threshold, limit * 2),
    )
    vec_results = [dict(row) for row in vec_cursor.fetchall()]

    fts_results = []
    fts_query = _sanitize_fts_query(query_text)
    if fts_query:
        try:
            fts_cursor = conn.execute(
                """
                SELECT m.id, m.error_type, m.traceback_str, m.failed_code, m.fix_description, 0.0 as distance
                FROM anti_patterns_fts f
                JOIN anti_patterns_meta m ON f.rowid = m.id
                WHERE anti_patterns_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit * 2),
            )
            fts_results = [dict(row) for row in fts_cursor.fetchall()]
        except Exception:
            pass

    fused_results = _reciprocal_rank_fusion(vec_results, fts_results)
    return fused_results[:limit]
