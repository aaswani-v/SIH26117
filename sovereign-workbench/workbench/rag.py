"""
RAG: ingestion + retrieval, both running on CPU so the GPU stays free for the
LLM. Uses a small sentence-transformers model (bge-small, ~130MB) rather than
full bge-m3 (~2GB) — noticeably lighter on RAM and fast enough on CPU for a
document set in the hundreds, not thousands, of pages.
"""

import os
import chromadb
from sentence_transformers import SentenceTransformer


class RAGStore:
    def __init__(self, persist_dir: str = "./chroma_db",
                 embedding_model: str = "BAAI/bge-small-en-v1.5",
                 device: str = "cpu"):
        self.embedder = SentenceTransformer(embedding_model, device=device)
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection("workbench_docs")

    def ingest_directory(self, dir_path: str, chunk_size: int = 800, overlap: int = 100):
        """Chunk every .txt file in dir_path and add to the store. Simple
        fixed-size chunking — swap for a structure-aware splitter if your
        documents have headings/sections worth respecting."""
        added = 0
        for fname in sorted(os.listdir(dir_path)):
            if not fname.endswith(".txt"):
                continue
            fpath = os.path.join(dir_path, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()

            chunks = self._chunk(text, chunk_size, overlap)
            embeddings = self.embedder.encode(chunks).tolist()
            ids = [f"{fname}::{i}" for i in range(len(chunks))]
            metadatas = [{"source": fname, "chunk": i} for i in range(len(chunks))]

            self.collection.upsert(
                ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas
            )
            added += len(chunks)
        return added

    def retrieve(self, query: str, top_k: int = 3) -> list[dict]:
        query_embedding = self.embedder.encode([query]).tolist()
        results = self.collection.query(query_embeddings=query_embedding, n_results=top_k)

        hits = []
        for doc, meta, dist in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            hits.append({"text": doc, "source": meta["source"], "score": 1 - dist})
        return hits

    @staticmethod
    def _chunk(text: str, chunk_size: int, overlap: int) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - overlap
        return [c.strip() for c in chunks if c.strip()]
