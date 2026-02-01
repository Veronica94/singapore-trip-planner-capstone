import json
import math
import os
from dataclasses import dataclass
from hashlib import md5
from typing import Iterable

from openai import OpenAI


DOCS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "docs",
)
INDEX_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "rag_index.json",
)


@dataclass
class Chunk:
    doc_id: str
    text: str
    embedding: list[float]


@dataclass
class RagResult:
    notes: list[str]
    citations: list[str]


def _iter_docs() -> Iterable[tuple[str, str]]:
    if not os.path.exists(DOCS_DIR):
        return []
    for name in sorted(os.listdir(DOCS_DIR)):
        path = os.path.join(DOCS_DIR, name)
        if os.path.isdir(path):
            continue
        if name.lower().endswith((".md", ".txt")):
            with open(path, "r", encoding="utf-8") as fh:
                yield name, fh.read()
        elif name.lower().endswith(".pdf"):
            yield name, _read_pdf(path)


def _read_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(path)
            return "\n\n".join(page.get_text("text") for page in doc)
        except Exception:
            return ""


def _split_chunks(
    text: str,
    *,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> list[str]:
    if not text.strip():
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 2 <= chunk_size:
            buf = f"{buf}\n\n{para}".strip()
            continue
        if buf:
            chunks.append(buf)
        if len(para) <= chunk_size:
            buf = para
        else:
            start = 0
            while start < len(para):
                end = min(start + chunk_size, len(para))
                chunks.append(para[start:end])
                start = max(end - chunk_overlap, end)
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def _embed_texts(texts: list[str]) -> list[list[float]]:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    model = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    client = OpenAI(api_key=api_key)
    resp = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in resp.data]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _docs_fingerprint() -> dict:
    files = []
    if not os.path.exists(DOCS_DIR):
        return {"files": []}
    for name in sorted(os.listdir(DOCS_DIR)):
        path = os.path.join(DOCS_DIR, name)
        if os.path.isdir(path):
            continue
        stat = os.stat(path)
        files.append(
            {
                "name": name,
                "mtime": int(stat.st_mtime),
                "size": stat.st_size,
            }
        )
    return {"files": files}


def _load_index() -> tuple[list[Chunk], dict] | None:
    if not os.path.exists(INDEX_PATH):
        return None
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        chunks = [
            Chunk(doc_id=c["doc_id"], text=c["text"], embedding=c["embedding"])
            for c in data.get("chunks", [])
        ]
        return chunks, data.get("fingerprint", {})
    except Exception:
        return None


def _save_index(chunks: list[Chunk], fingerprint: dict) -> None:
    payload = {
        "fingerprint": fingerprint,
        "chunks": [
            {"doc_id": c.doc_id, "text": c.text, "embedding": c.embedding}
            for c in chunks
        ],
    }
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


def build_index() -> list[Chunk]:
    fingerprint = _docs_fingerprint()
    cached = _load_index()
    if cached and cached[1] == fingerprint:
        return cached[0]

    chunks: list[Chunk] = []
    texts: list[str] = []
    metas: list[str] = []

    for doc_id, text in _iter_docs():
        for chunk_text in _split_chunks(text):
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue
            texts.append(chunk_text)
            metas.append(doc_id)

    if not texts:
        _save_index([], fingerprint)
        return []

    embeddings = _embed_texts(texts)
    for doc_id, text, emb in zip(metas, texts, embeddings):
        chunks.append(Chunk(doc_id=doc_id, text=text, embedding=emb))

    _save_index(chunks, fingerprint)
    return chunks


def retrieve(query: str, *, top_k: int = 3) -> list[Chunk]:
    chunks = build_index()
    if not chunks:
        return []
    query_emb = _embed_texts([query])[0]
    ranked = sorted(
        chunks,
        key=lambda c: _cosine(query_emb, c.embedding),
        reverse=True,
    )
    return ranked[:top_k]


def rag_query(query: str, *, top_k: int = 3) -> RagResult:
    hits = retrieve(query, top_k=top_k)
    notes = [hit.text for hit in hits]
    citations = [hit.doc_id for hit in hits]
    rules_path = os.path.join(DOCS_DIR, "00_planning_rules_and_templates.md")
    if os.path.exists(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as fh:
                rules_text = fh.read().strip()
            if rules_text:
                notes.insert(0, rules_text)
                citations.insert(0, "00_planning_rules_and_templates.md")
        except Exception:
            pass
    return RagResult(notes=notes, citations=citations)
