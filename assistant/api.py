"""The HTTP layer. Four endpoints, no business logic."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from assistant import config, ingestion, repository
from assistant.pipeline import Assistant

state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    with repository.connection() as connection:
        repository.create_schema(connection)
    state["assistant"] = Assistant()
    state["started_at"] = datetime.now(timezone.utc)
    yield
    repository.pool().close()


app = FastAPI(title="Secure Enterprise RAG Assistant", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(min_length=3)
    username: str = "guest"


@app.get("/health")
def health() -> dict:
    with repository.connection() as connection:
        return {
            "status": "ok",
            "started_at": state["started_at"].isoformat(timespec="seconds"),
            **repository.counts(connection),
        }


@app.get("/documents")
def documents() -> dict:
    with repository.connection() as connection:
        return {"documents": repository.list_documents(connection)}


@app.post("/documents")
async def upload(file: UploadFile) -> dict:
    text = (await file.read()).decode("utf-8", errors="replace")
    with repository.connection() as connection:
        try:
            result = ingestion.store(connection, text, file.filename or "uploaded.md")
        except ingestion.UploadError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "outcome": result.outcome,
            "message": result.line(),
            **repository.counts(connection),
        }


@app.post("/ask")
def ask(request: AskRequest) -> dict:
    answer = state["assistant"].ask(request.question, username=request.username)
    return {
        "question": answer.question,
        "answer": answer.text,
        "answered": answer.answered,
        "grounded": answer.fully_grounded,
        "citations": [
            {
                "source": c.label,
                "quote": c.quote,
                "updated_on": str(c.updated_on),
                "status": c.status,
                "grounded": c.grounded,
            }
            for c in answer.citations
        ],
        "warnings": answer.warnings,
        "trace": answer.trace,
    }


@app.get("/")
def home() -> FileResponse:
    return FileResponse(config.ROOT / "web" / "index.html")