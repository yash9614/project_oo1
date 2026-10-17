from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field

from assistant import config, repository
from assistant.models import Hit, User


class _Rating(BaseModel):
    chunk_number: int
    score: int = Field(description="Relevance 0-10")


class _Ratings(BaseModel):
    ratings: list[_Rating]


class Retriever:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(model=config.EMBEDDING_MODEL)
        self.reranker = ChatOpenAI(
            model=config.HELPER_MODEL, temperature=0
        ).with_structured_output(_Ratings)

    def search(self, connection, question: str, user: User, include_history: bool = False) -> list[Hit]:
        vector = self.embeddings.embed_query(question)
        candidates = repository.hybrid_search(
            connection, question, vector, user, include_history
        )
        if not candidates:
            return []
        return self._rerank(question, candidates)

    def _rerank(self, question: str, candidates: list[Hit]) -> list[Hit]:
        numbered = "\n\n".join(
            f"[{i}] {hit.label}\n{hit.content}" for i, hit in enumerate(candidates, 1)
        )
        prompt = config.prompt("rerank").format(question=question, context=numbered)
        ratings = self.reranker.invoke(prompt)
        score_by_number = {r.chunk_number: r.score for r in ratings.ratings}
        for i, hit in enumerate(candidates, 1):
            hit.score = score_by_number.get(i, 0)
        ranked = sorted(candidates, key=lambda h: h.score, reverse=True)
        return [h for h in ranked if h.score >= config.MIN_RERANK_SCORE][: config.TOP_K]