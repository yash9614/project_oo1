-- The whole database. Four tables.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    username     TEXT PRIMARY KEY,
    display_name TEXT    NOT NULL,
    department   TEXT    NOT NULL,
    is_employee  BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id             BIGSERIAL PRIMARY KEY,
    source         TEXT        NOT NULL,
    title          TEXT        NOT NULL,
    department     TEXT        NOT NULL,
    visibility     TEXT        NOT NULL,
    version        INT         NOT NULL DEFAULT 1,
    status         TEXT        NOT NULL DEFAULT 'active',
    effective_from DATE        NOT NULL,
    updated_on     DATE        NOT NULL,
    content_hash   TEXT        NOT NULL UNIQUE,
    indexed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (title, version)
);

CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id BIGINT       NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    section     TEXT         NOT NULL,
    content     TEXT         NOT NULL,
    embedding   VECTOR(1536) NOT NULL,
    search_text TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

CREATE TABLE IF NOT EXISTS audit_events (
    id        BIGSERIAL PRIMARY KEY,
    at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    username  TEXT        NOT NULL,
    question  TEXT        NOT NULL,
    answered  BOOLEAN     NOT NULL,
    grounded  BOOLEAN     NOT NULL,
    sources   TEXT        NOT NULL
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS chunks_search_idx
    ON chunks USING gin (search_text);

CREATE INDEX IF NOT EXISTS chunks_document_idx
    ON chunks (document_id);

CREATE INDEX IF NOT EXISTS audit_events_at_idx
    ON audit_events (at DESC);

-- Demo users. Alice (engineering) cannot see HR docs; Bob can.
INSERT INTO users (username, display_name, department, is_employee) VALUES
    ('alice', 'Alice',  'engineering', true),
    ('bob',   'Bob',    'hr',          true),
    ('carol', 'Carol',  'finance',     true),
    ('guest', 'Guest',  'none',        false)
ON CONFLICT (username) DO NOTHING;