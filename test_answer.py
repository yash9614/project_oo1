from datetime import date
from langchain_openai import OpenAIEmbeddings

from assistant import config
from assistant.generation import Generator
from assistant.repository import connection, find_user, hybrid_search

embeddings = OpenAIEmbeddings(model=config.EMBEDDING_MODEL)
generator = Generator()

question = "Who may push to production?"
vector = embeddings.embed_query(question)

with connection() as conn:
    alice = find_user(conn, "alice")
    hits = hybrid_search(conn, question, vector, alice)
    answer = generator.write(question, hits, today=date.today())

print(f"Answered: {answer.answered}")
print(f"Fully grounded: {answer.fully_grounded}")
print(f"\n{answer.text}\n")
for c in answer.citations:
    print(f"[{'OK' if c.grounded else 'FAIL'}] {c.label}")
    print(f"  quote: {c.quote}")
if answer.warnings:
    print("\nWarnings:", answer.warnings)