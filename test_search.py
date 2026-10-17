from assistant.repository import connection, find_user, hybrid_search


from langchain_openai import OpenAIEmbeddings

from assistant import config
from assistant.repository import connection, find_user, hybrid_search, searchable_chunks

with connection() as conn:
    alice = find_user(conn, "alice")
    # dummy vector of the right dimension
    dummy = [0.0] * 1536
    hits = hybrid_search(conn, "refund policy", dummy, alice)
    print(f"Alice sees {len(hits)} hits (expected 0 until we ingest)")
    print(alice.describe_access())



embeddings = OpenAIEmbeddings(model=config.EMBEDDING_MODEL)

question = "How do I deploy to production?"
vector = embeddings.embed_query(question)

with connection() as conn:
    for username in ("alice", "bob", "guest"):
        user = find_user(conn, username)
        stats = searchable_chunks(conn, user)
        hits = hybrid_search(conn, question, vector, user)

        print(f"\n=== {user.username} ({user.describe_access()}) ===")
        print(f"Searchable chunks: {stats['allowed']} of {stats['total']}")
        print(f"Hits returned: {len(hits)}")
        for hit in hits:
            print(f"  - {hit.label} (score {hit.score:.3f})")
            print(f"    {hit.content[:120]}...")