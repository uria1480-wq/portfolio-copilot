"""RAG: מאגר ידע מקומי (Chroma) ממסמכי עמלות, תקנונים וכללי מס."""
import hashlib
import os
import uuid
import zlib
from pathlib import Path
from typing import Callable


# --- חיתוך טקסט לקטעים ---
def chunk_text(text: str, max_chars: int = 800, overlap: int = 120) -> list[str]:
    """חותך לקטעים לפי פסקאות. פסקה ארוכה מדי נחתכת בחפיפה קלה."""
    paragraphs = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]
    step = max(1, max_chars - overlap)
    chunks, current = [], ""
    for p in paragraphs:
        pieces = [p[i:i + max_chars] for i in range(0, len(p), step)] if len(p) > max_chars else [p]
        for piece in pieces:
            if current and len(current) + len(piece) + 2 > max_chars:
                chunks.append(current)
                current = piece
            else:
                current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


# --- וקטורים (embeddings) ---
def openai_embed(texts: list[str]) -> list[list[float]]:
    """וקטורים דרך אותו ממשק תואם-OpenAI של הסוכן. תומך בעברית.
    שם המודל נקבע במשתנה EMBEDDING_MODEL בקובץ .env (ברירת מחדל: gemini-embedding-001)."""
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
    model = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    vectors = []
    for i in range(0, len(texts), 50):
        response = client.embeddings.create(model=model, input=texts[i:i + 50])
        vectors.extend(d.embedding for d in response.data)
    return vectors


# --- מאגר הידע ---
class KnowledgeBase:
    def __init__(self, path: str | Path = "data/chroma", embed: Callable[[list[str]], list[list[float]]] | None = None,
                 name: str = "knowledge"):
        import chromadb

        self.embed = embed or openai_embed
        if str(path) == ":memory:":
            self.client = chromadb.EphemeralClient()
            name = f"{name}_{uuid.uuid4().hex[:8]}"
        else:
            Path(path).mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(path=str(path))
        self.col = self.client.get_or_create_collection(
            name, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    def add_document(self, source: str, text: str) -> int:
        """מוסיף מסמך. אם לא השתנה מאז ההטמעה הקודמת, מדלג. מחזיר כמה קטעים נוספו."""
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing = self.col.get(where={"source": source}, include=["metadatas"])
        if existing["ids"] and all(m.get("hash") == digest for m in existing["metadatas"]):
            return 0
        if existing["ids"]:
            self.col.delete(where={"source": source})
        chunks = chunk_text(text)
        if not chunks:
            return 0
        self.col.add(
            ids=[f"{source}::{i}" for i in range(len(chunks))],
            documents=chunks,
            embeddings=self.embed(chunks),
            metadatas=[{"source": source, "hash": digest, "chunk": i} for i in range(len(chunks))],
        )
        return len(chunks)

    def search(self, query: str, k: int = 4) -> list[dict]:
        total = self.col.count()
        if total == 0:
            return []
        result = self.col.query(
            query_embeddings=[self.embed([query])[0]],
            n_results=min(k, total),
            include=["documents", "metadatas", "distances"],
        )
        return [
            {"source": meta["source"], "text": doc, "score": round(1 - dist, 3)}
            for doc, meta, dist in zip(result["documents"][0], result["metadatas"][0], result["distances"][0])
        ]

    def sources(self) -> list[str]:
        metas = self.col.get(include=["metadatas"])["metadatas"]
        return sorted({m["source"] for m in metas})


def load_folder(kb: KnowledgeBase, folder: str | Path = "knowledge") -> dict[str, int]:
    """טוען לקובץ הידע את כל קבצי ה-.txt וה-.md בתיקייה. מחזיר כמה קטעים נוספו לכל קובץ."""
    folder = Path(folder)
    if not folder.exists():
        return {}
    added = {}
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in (".txt", ".md"):
            added[path.name] = kb.add_document(path.name, path.read_text(encoding="utf-8-sig"))
    return added