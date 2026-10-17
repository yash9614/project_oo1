from datetime import date

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from assistant import config, repository
from assistant.generation import Generator
from assistant.models import Answer, User
from assistant.retrieval import Retriever


class _Intent(BaseModel):
    wants_history: bool = Field(description="True when asking about an older version")


class _Grade(BaseModel):
    sufficient: bool = Field(description="True only if these chunks contain the answer")
    missing: str = Field(description="What is missing, or 'nothing'")


class Assistant:
    def __init__(self):
        self.retriever = Retriever()
        self.generator = Generator()
        self.helper = ChatOpenAI(model=config.HELPER_MODEL, temperature=0)
        self.grader = self.helper.with_structured_output(_Grade)
        self.intent = self.helper.with_structured_output(_Intent)

    def ask(self, question: str, username: str = "guest", today: date | None = None) -> Answer:
        with repository.connection() as connection:
            return self._ask(connection, question, username, today)

    def _ask(self, connection, question: str, username: str, today: date | None) -> Answer:
        user = repository.find_user(connection, username)
        wants_history = self.intent.invoke(
            config.prompt("intent") + "\n\nQuestion: " + question
        ).wants_history

        reach = repository.searchable_chunks(connection, user, wants_history)
        trace = [
            f"user {user.display_name} ({user.department}), can read {user.describe_access()}",
            f"searchable for this user: {reach['allowed']} of {reach['total']} chunks",
            f"history requested: {wants_history}",
        ]

        answer = self._attempt(connection, question, user, wants_history, trace, today)
        self._record(connection, user, question, answer)
        return answer

    def _attempt(self, connection, question, user, wants_history, trace, today) -> Answer:
        query = question
        for attempt in range(1, config.MAX_ATTEMPTS + 1):
            hits = self.retriever.search(connection, query, user, wants_history)
            trace.append(f"attempt {attempt}: searched '{query}', kept {len(hits)} chunks")

            if hits and hits[0].score >= config.HIGH_CONFIDENCE_SCORE:
                trace.append(f"attempt {attempt}: top chunk scored {hits[0].score}/10, answering")
                return self._answer(question, hits, trace, today)

            if hits:
                grade = self.grader.invoke(
                    config.prompt("grade").format(
                        question=question,
                        context="\n\n".join(f"[{hit.label}] {hit.content}" for hit in hits),
                    )
                )
                trace.append(f"attempt {attempt}: sufficient={grade.sufficient}")
                if grade.sufficient:
                    return self._answer(question, hits, trace, today)
            else:
                grade = _Grade(sufficient=False, missing="nothing relevant was found")

            if attempt < config.MAX_ATTEMPTS:
                rewritten = self.helper.invoke(
                    config.prompt("rewrite").format(question=question, missing=grade.missing)
                ).content.strip()
                query = rewritten
                trace.append(f"corrective retrieval: rewrote the query to '{query}'")

        trace.append("gave up and escalated")
        return Answer(
            question=question,
            text=(
                "I could not find a reliable answer in the documents you are allowed to read. "
                "I have not guessed. Please raise a ticket and a person will pick this up."
            ),
            answered=False,
            warnings=["Escalated to a human after two attempts."],
            trace=trace,
        )

    def _answer(self, question, hits, trace, today) -> Answer:
        answer = self.generator.write(question, hits, today)
        answer.trace = trace
        return answer

    def _record(self, connection, user: User, question: str, answer: Answer) -> None:
        sources = ", ".join(c.label for c in answer.citations) or "none"
        repository.record_event(
            connection, user.username, question,
            answer.answered, answer.fully_grounded, sources,
        )