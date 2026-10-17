from dataclasses import dataclass, field
from datetime import date


@dataclass
class User:
    username: str
    display_name: str
    department: str
    is_employee: bool

    def describe_access(self) -> str:
        if not self.is_employee:
            return "public documents only"
        return f"public + internal + restricted ({self.department})"


@dataclass
class Hit:
    chunk_id: int
    content: str
    section: str
    source: str
    title: str
    version: int
    status: str
    updated_on: date
    score: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.title} v{self.version} > {self.section}"


@dataclass
class Citation:
    label: str
    quote: str
    updated_on: date
    status: str
    grounded: bool


@dataclass
class Answer:
    question: str
    text: str
    answered: bool
    citations: list[Citation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)

    @property
    def fully_grounded(self) -> bool:
        return self.answered and all(c.grounded for c in self.citations)

@dataclass
class SourceDocument:
    source: str
    title: str
    department: str
    visibility: str
    version: int
    status: str
    effective_from: date
    updated_on: date
    content_hash: str
    body: str
@dataclass
class Chunk:
    section: str
    content: str