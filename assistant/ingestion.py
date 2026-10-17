"""Indexing one uploaded document."""

import hashlib
from dataclasses import dataclass
from datetime import datetime

from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from assistant import config, repository
from assistant.models import Chunk, SourceDocument

REQUIRED_FIELDS = ("title", "department", "visibility", "version", "status", "effective", "updated")


@dataclass
class UploadResult:
    filename: str
    outcome: str
    title: str = ""
    version: int = 0
    chunks: int = 0
    detail: str = ""


class UploadError(ValueError):
    pass


def parse(text: str, filename: str) -> SourceDocument:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.lstrip().startswith("---"):
        raise UploadError("file must start with a header block between --- markers")

    _, header, body = text.split("---", 2)
    fields = {}
    for line in header.strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()

    missing = [f for f in REQUIRED_FIELDS if f not in fields]
    if missing:
        raise UploadError("header is missing: " + ", ".join(missing))

    return SourceDocument(
        source=filename,
        title=fields["title"],
        department=fields["department"],
        visibility=fields["visibility"],
        version=int(fields["version"]),
        status=fields["status"],
        effective_from=datetime.strptime(fields["effective"], "%Y-%m-%d").date(),
        updated_on=datetime.strptime(fields["updated"], "%Y-%m-%d").date(),
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        body=body.strip(),
    )


def split(document: SourceDocument) -> list[Chunk]:
    by_heading = MarkdownHeaderTextSplitter(headers_to_split_on=[("##", "section")])
    by_size = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
    )
    chunks = []
    for section in by_heading.split_text(document.body):
        name = section.metadata.get("section", document.title)
        for piece in by_size.split_text(section.page_content):
            chunks.append(Chunk(section=name, content=piece))
    return chunks


def store(connection, text: str, filename: str) -> UploadResult:
    document = parse(text, filename)

    existing = repository.find_by_hash(connection, document.content_hash)
    if existing:
        return UploadResult(filename=filename, outcome="duplicate",
                            detail=f"{existing['title']} v{existing['version']}")

    replacing = repository.find_by_version(connection, document.title, document.version)
    if replacing:
        repository.delete_document(connection, replacing["id"])

    chunks = split(document)
    if not chunks:
        raise UploadError("document has no content under its headings")

    vectors = OpenAIEmbeddings(model=config.EMBEDDING_MODEL).embed_documents(
        [c.content for c in chunks]
    )

    document_id = repository.insert_document(connection, document)
    repository.insert_chunks(
        connection, document_id,
        [c.section for c in chunks],
        [c.content for c in chunks],
        vectors,
    )
    connection.commit()

    return UploadResult(
        filename=filename,
        outcome="updated" if replacing else "added",
        title=document.title,
        version=document.version,
        chunks=len(chunks),
    )