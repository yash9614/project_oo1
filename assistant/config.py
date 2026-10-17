"""
Every setting in one place.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = ROOT / "documents"
PROMPTS_DIR = ROOT / "prompts"
SCHEMA_FILE = ROOT / "schema.sql"

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://rag:ragsecret@localhost:5433/ragdb"
)

# Models. Changing the embedding model means re-indexing everything.
EMBEDDING_MODEL = "text-embedding-3-small"
ANSWER_MODEL = "gpt-4o-mini"
HELPER_MODEL = "gpt-4o-mini"

# Chunking
CHUNK_SIZE = 600
CHUNK_OVERLAP = 120

# Retrieval
CANDIDATES = 12
TOP_K = 4
MIN_RERANK_SCORE = 4
HIGH_CONFIDENCE_SCORE = 8
RRF_CONSTANT = 60

# Self-correction
MAX_ATTEMPTS = 2

# Freshness
STALE_AFTER_DAYS = 180

def prompt(name: str) -> str:
    """Read a prompt template from the prompts folder."""
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")