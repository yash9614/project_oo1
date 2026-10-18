# Important Concepts & Interview Q&A

This document covers the key ideas behind the Secure Enterprise RAG Assistant and common interview questions you should be able to answer.

## Core Concepts

### 1. Access Control in SQL (not after retrieval)

The `readable` CTE filters documents **before** any vector or keyword ranking:

```sql
WITH readable AS (
    SELECT id FROM documents
    WHERE (
        visibility = 'public'
        OR (visibility = 'internal'   AND %(is_employee)s)
        OR (visibility = 'restricted' AND department = %(department)s)
    )
    AND (status = 'active' OR %(include_history)s)
)
```

A forbidden document is never a candidate, never reranked, and never sent to the LLM. This is "secure by construction."

### 2. Hybrid Search + Reciprocal Rank Fusion (RRF)

- Semantic ranking uses pgvector cosine distance (`embedding <=> query_vector`).
- Keyword ranking uses Postgres full-text search (`ts_rank` + `plainto_tsquery`).
- RRF merges the two rankings: `1 / (k + rank)` where `k = 60`.

This is more robust than pure vector search for enterprise documents that mix precise terms and semantic meaning.

### 3. Corrective RAG

The pipeline does not generate on the first retrieval if the results are weak:

1. Intent detection (current vs historical policy).
2. Hybrid search under the user's permissions.
3. Grade whether the chunks contain the answer.
4. If not, rewrite the query and retry once.
5. If still insufficient, escalate honestly instead of guessing.

### 4. Grounding by String Match

The model must copy an exact sentence from a retrieved chunk. Python then verifies:

```python
def _flatten(text: str) -> str:
    return " ".join(text.split()).lower()

grounded = _flatten(quote) in _flatten(chunk_content)
```

Asking the model "did you tell the truth?" is weak. Comparing the quoted string against the source is not.

### 5. Content Hash for Deduplication

Documents are identified by a SHA-256 hash of their normalized text, not by filename. Uploading `policy.md`, `policy-final.md`, or `policy(2).md` with the same content is a no-op.

---

## Interview-Style Q&A

**Q: Why enforce access control in SQL instead of filtering after retrieval?**

A: Filtering after retrieval means the forbidden document was already ranked, scored, and potentially sent to the model. A bug in the filter logic can leak data. Doing it in the `readable` CTE means the document never enters the candidate set.

**Q: What is Reciprocal Rank Fusion and why use it?**

A: RRF combines rankings from different retrievers (vector and keyword) without requiring a tuned weight. Each result gets a score of `1 / (k + rank)`. It is simple, effective, and commonly used in production hybrid search systems.

**Q: How do you prevent the model from hallucinating in a RAG system?**

A: Force structured output with exact quotes, then verify those quotes exist in the source chunks using string matching. If a quote fails the check, retry once with a reminder or refuse to answer. Never trust the model to self-report accuracy.

**Q: What happens when the first retrieval is not good enough?**

A: The system grades the chunks. If they are insufficient, it rewrites the query (corrective RAG) and tries once more. After `MAX_ATTEMPTS` it escalates to a human instead of inventing an answer.

**Q: How would you extend this to multi-tenant isolation?**

A: Add a `tenant_id` column and include `AND tenant_id = %(tenant_id)s` in the `readable` CTE (and every other query). The same pattern already used for department and visibility scales to full multi-tenant isolation.

**Q: Why store both a vector and a tsvector on the same chunk row?**

A: It allows a single SQL query to do hybrid search without maintaining a separate search index or merging results in Python. Postgres keeps the `tsvector` automatically in sync via a generated column.

**Q: What are the risks of putting the OpenAI API key in the container?**

A: The key is passed via environment variable at runtime (`OPENAI_API_KEY: ${OPENAI_API_KEY}`), not baked into the image. Still, prefer secrets managers (AWS Secrets Manager, Doppler, etc.) for production, and never commit `.env`.

---

## Portfolio Talking Points

- "Access control is enforced at the database layer before any ranking occurs."
- "We use Reciprocal Rank Fusion to combine dense and sparse retrieval without tuning a weight."
- "Grounding is verified by exact string match on the quoted sentence, not by asking the model."
- "The system escalates honestly after one corrective rewrite instead of hallucinating."
- "Documents are identified by content hash so duplicate uploads are free."
