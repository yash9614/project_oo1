"""
Every line of SQL in this project lives here.
"""

import atexit
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from assistant import config
from assistant.models import User
from assistant.models import SourceDocument

from pgvector import Vector
from assistant.models import Hit, User

_pool: ConnectionPool | None = None


def _prepare(connection: psycopg.Connection) -> None:
    """Register the vector type on every new connection."""
    register_vector(connection)


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            config.DATABASE_URL,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
            configure=_prepare,
            check=ConnectionPool.check_connection,
            open=True,
        )
        atexit.register(close_pool)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection():
    """Borrow a connection for one unit of work."""
    with pool().connection() as borrowed:
        yield borrowed


def find_user(connection: psycopg.Connection, username: str) -> User:
    """Who is asking. Unknown users get the least access."""
    row = connection.execute(
        "SELECT username, display_name, department, is_employee FROM users WHERE username = %s",
        (username,),
    ).fetchone()

    if row is None:
        return User(
            username=username,
            display_name=username,
            department="none",
            is_employee=False,
        )
    return User(**row)


# ------------------------------------------------------------------- search

HYBRID_SEARCH = """
WITH readable AS (
    SELECT id FROM documents
    WHERE (
        visibility = 'public'
        OR (visibility = 'internal'   AND %(is_employee)s)
        OR (visibility = 'restricted' AND department = %(department)s)
    )
    AND (status = 'active' OR %(include_history)s)
),
semantic AS (
    SELECT c.id,
           ROW_NUMBER() OVER (ORDER BY c.embedding <=> %(query_vector)s) AS rank
    FROM chunks c
    JOIN readable r ON r.id = c.document_id
    ORDER BY c.embedding <=> %(query_vector)s
    LIMIT %(candidates)s
),
keyword AS (
    SELECT c.id,
           ROW_NUMBER() OVER (ORDER BY ts_rank(c.search_text, query) DESC) AS rank
    FROM chunks c
    JOIN readable r ON r.id = c.document_id,
         plainto_tsquery('english', %(question)s) AS query
    WHERE c.search_text @@ query
    ORDER BY ts_rank(c.search_text, query) DESC
    LIMIT %(candidates)s
),
fused AS (
    SELECT id, SUM(1.0 / (%(rrf_constant)s + rank)) AS score
    FROM (SELECT * FROM semantic UNION ALL SELECT * FROM keyword) AS ranked
    GROUP BY id
    ORDER BY score DESC
    LIMIT %(candidates)s
)
SELECT c.id AS chunk_id, c.content, c.section,
       d.source, d.title, d.version, d.status, d.updated_on,
       f.score
FROM fused f
JOIN chunks c    ON c.id = f.id
JOIN documents d ON d.id = c.document_id
ORDER BY f.score DESC
"""


def hybrid_search(
    connection: psycopg.Connection,
    question: str,
    query_vector: list[float],
    user: User,
    include_history: bool = False,
) -> list[Hit]:
    """Meaning and keywords, merged by rank, inside this person's permissions."""
    rows = connection.execute(
        HYBRID_SEARCH,
        {
            "question": question,
            "query_vector": Vector(query_vector),
            "is_employee": user.is_employee,
            "department": user.department,
            "include_history": include_history,
            "candidates": config.CANDIDATES,
            "rrf_constant": config.RRF_CONSTANT,
        },
    ).fetchall()

    return [
        Hit(
            chunk_id=row["chunk_id"],
            content=row["content"],
            section=row["section"],
            source=row["source"],
            title=row["title"],
            version=row["version"],
            status=row["status"],
            updated_on=row["updated_on"],
            score=float(row["score"]),
        )
        for row in rows
    ]


def searchable_chunks(
    connection: psycopg.Connection, user: User, include_history: bool = False
) -> dict:
    """How much of the library this person could search at all."""
    row = connection.execute(
        """
        SELECT count(*) FILTER (
            WHERE (
                d.visibility = 'public'
                OR (d.visibility = 'internal'   AND %(is_employee)s)
                OR (d.visibility = 'restricted' AND d.department = %(department)s)
            )
            AND (d.status = 'active' OR %(include_history)s)
        ) AS allowed,
        count(*) AS total
        FROM chunks c JOIN documents d ON d.id = c.document_id
        """,
        {
            "is_employee": user.is_employee,
            "department": user.department,
            "include_history": include_history,
        },
    ).fetchone()
    return dict(row)



def find_by_hash(connection, content_hash: str) -> dict | None:
    row = connection.execute(
        "SELECT id, source, title, version FROM documents WHERE content_hash = %s",
        (content_hash,),
    ).fetchone()
    return dict(row) if row else None


def find_by_version(connection, title: str, version: int) -> dict | None:
    row = connection.execute(
        "SELECT id, source, content_hash FROM documents WHERE title = %s AND version = %s",
        (title, version),
    ).fetchone()
    return dict(row) if row else None


def delete_document(connection, document_id: int) -> None:
    connection.execute("DELETE FROM documents WHERE id = %s", (document_id,))


def insert_document(connection, document: SourceDocument) -> int:
    row = connection.execute(
        """
        INSERT INTO documents
            (source, title, department, visibility, version, status,
             effective_from, updated_on, content_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            document.source, document.title, document.department, document.visibility,
            document.version, document.status, document.effective_from,
            document.updated_on, document.content_hash,
        ),
    ).fetchone()
    return row["id"]


def insert_chunks(connection, document_id: int, sections, contents, embeddings) -> None:
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO chunks (document_id, section, content, embedding)
            VALUES (%s, %s, %s, %s)
            """,
            list(zip([document_id] * len(contents), sections, contents, embeddings)),
        )


def record_event(connection, username: str, question: str, answered: bool, grounded: bool, sources: str) -> None:
    connection.execute(
        """
        INSERT INTO audit_events (username, question, answered, grounded, sources)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (username, question, answered, grounded, sources),
    )
    connection.commit()

def list_documents(connection) -> list[dict]:
    rows = connection.execute(
        """
        SELECT d.title, d.version, d.status, d.department, d.visibility,
               d.source, d.updated_on, count(c.id) AS chunks
        FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
        GROUP BY d.id
        ORDER BY d.title, d.version
        """
    ).fetchall()
    return [dict(row) for row in rows]


def counts(connection) -> dict:
    row = connection.execute(
        """
        SELECT (SELECT count(*) FROM documents) AS documents,
               (SELECT count(*) FROM documents WHERE status = 'active') AS active_documents,
               (SELECT count(*) FROM chunks) AS chunks,
               (SELECT max(indexed_at) FROM documents) AS last_indexed
        """
    ).fetchone()
    return dict(row)

def create_schema(connection: psycopg.Connection) -> None:
    """Run schema.sql. Safe to call every time (everything is IF NOT EXISTS)."""
    connection.execute(config.SCHEMA_FILE.read_text(encoding="utf-8"))
    connection.commit()