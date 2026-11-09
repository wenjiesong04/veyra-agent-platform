"""Deterministic, local-only paragraph chunks and lexical retrieval."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from veyra_agent_platform.contracts.canonical import (
    normalized_source_bytes,
    sha256_digest,
)

MAX_CHUNK_CHARS: Literal[2000] = 2_000
MAX_QUERY_CHARS = 4_096
MAX_QUERY_TERMS = 256
DEFAULT_TOP_K = 6
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]+")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_ref: str
    source_file_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunk_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=MAX_CHUNK_CHARS)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def _chunk_id(reference: str, source_hash: str, index: int, content_hash: str) -> str:
    return sha256_digest([reference, source_hash, index, content_hash])


class KnowledgeIndex(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    chunker_version: Literal["paragraph-lines-v1"] = "paragraph-lines-v1"
    max_chunk_chars: Literal[2000] = MAX_CHUNK_CHARS
    overlap: Literal[0] = 0
    knowledge_ref: str
    source_file_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunks: tuple[Chunk, ...]
    chunk_count: int = Field(ge=0)
    built_at: datetime

    @model_validator(mode="after")
    def validate_chunks(self) -> Self:
        if self.chunk_count != len(self.chunks):
            raise ValueError("chunk count mismatch")
        previous_end = 1
        for position, chunk in enumerate(self.chunks):
            content_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
            if (
                chunk.knowledge_ref != self.knowledge_ref
                or chunk.source_file_hash != self.source_file_hash
                or chunk.chunk_index != position
                or chunk.content_hash != content_hash
                or normalized_source_bytes(chunk.text) != chunk.text.encode("utf-8")
                or chunk.line_start < previous_end
                or chunk.line_end != chunk.line_start + chunk.text.count("\n")
                or chunk.chunk_id
                != _chunk_id(
                    self.knowledge_ref, self.source_file_hash, position, content_hash
                )
            ):
                raise ValueError("invalid chunk identity or locator")
            previous_end = chunk.line_end
        return self


class RetrievalHit(Chunk):
    rank: int = Field(ge=1)
    score: int = Field(gt=0)


def build_index(
    knowledge_ref: str, text: str, source_file_hash: str | None = None
) -> KnowledgeIndex:
    canonical = normalized_source_bytes(text)
    digest = hashlib.sha256(canonical).hexdigest()
    if source_file_hash is not None and source_file_hash != digest:
        raise ValueError("source_file_hash does not match canonical document")
    chunks: list[Chunk] = []
    pending = ""
    start = 1

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        content_hash = hashlib.sha256(pending.encode("utf-8")).hexdigest()
        position = len(chunks)
        chunks.append(
            Chunk(
                knowledge_ref=knowledge_ref,
                source_file_hash=digest,
                chunk_id=_chunk_id(knowledge_ref, digest, position, content_hash),
                chunk_index=position,
                text=pending,
                line_start=start,
                line_end=start + pending.count("\n"),
                content_hash=content_hash,
            )
        )
        pending = ""

    for line_number, line in enumerate(canonical.decode("utf-8").split("\n"), 1):
        if not line.strip():
            flush()
            continue
        if pending and len(pending) + 1 + len(line) <= MAX_CHUNK_CHARS:
            pending += "\n" + line
            continue
        flush()
        start = line_number
        for offset in range(0, len(line), MAX_CHUNK_CHARS):
            flush()
            pending = line[offset : offset + MAX_CHUNK_CHARS]
    flush()
    return KnowledgeIndex(
        knowledge_ref=knowledge_ref,
        source_file_hash=digest,
        chunks=tuple(chunks),
        chunk_count=len(chunks),
        built_at=datetime.now(UTC),
    )


def _terms(text: str) -> set[str]:
    terms = set(_WORD.findall(_CJK.sub(" ", text)))
    for match in _CJK.finditer(text):
        run = match.group()
        terms.update(run)
        terms.update(run[i : i + 2] for i in range(len(run) - 1))
    return terms


def retrieve(
    indexes: list[KnowledgeIndex], query: str, *, top_k: int = DEFAULT_TOP_K
) -> list[RetrievalHit]:
    query = (
        normalized_source_bytes(query[:MAX_QUERY_CHARS])
        .decode("utf-8")
        .casefold()
        .strip()
    )
    terms = set(sorted(_terms(query))[:MAX_QUERY_TERMS])
    if not terms or top_k <= 0:
        return []
    scored: list[tuple[int, Chunk]] = []
    for index in indexes:
        for chunk in index.chunks:
            text = chunk.text.casefold()
            overlap = len(terms & _terms(text))
            if overlap:
                scored.append((overlap + (4 if query in text else 0), chunk))
    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].knowledge_ref,
            item[1].chunk_index,
            item[1].chunk_id,
        )
    )
    return [
        RetrievalHit(**chunk.model_dump(), score=score, rank=rank)
        for rank, (score, chunk) in enumerate(scored[:top_k], 1)
    ]
