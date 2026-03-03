# backend/app/services/rag/vector_engine.py
import os
import re
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader

class VectorEngine:
    """
    Singleton Vector Engine for IFRS 17 RAG.
    Handles PDF ingestion, semantic chunking, embedding, and vector search.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(VectorEngine, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = "./chroma_db", collection_name: str = "ifrs17_docs"):
        # Ensure initialization only happens once for the singleton
        if hasattr(self, 'initialized') and self.initialized:
            return

        os.makedirs(db_path, exist_ok=True)
        self._model = None  # Lazy load
        self.db_path = db_path
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        self.initialized = True

    @property
    def model(self):
        """Lazy loader for the embedding model."""
        if self._model is None:
            print("Loading SentenceTransformer model (first time)...")
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._model

    def _clean_text(self, text: str) -> str:
        """Basic text cleaning for actuarial documents."""
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        return text.strip()

    def _semantic_chunking(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """
        Splits text into chunks while attempting to respect sentence boundaries.
        """
        # Split by common sentence endings (., !, ?) followed by space
        sentences = re.split(r'(?<=[.!?])\s+', text)

        chunks = []
        current_chunk = ""

        for sentence in sentences:
            # If adding this sentence exceeds chunk_size, save current and start new
            if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                # Keep overlap from the end of the current chunk
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + " " + sentence
            else:
                current_chunk += (" " if current_chunk else "") + sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def ingest_document(self, file_path: str) -> List[str]:
        """
        逐页读取并标注页码，解决引用丢失问题。
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at: {file_path}")

        print(f"📖 正在入库文档: {file_path}")
        ext = os.path.splitext(file_path)[1].lower()

        all_chunks = []
        all_metadata = []
        doc_name = os.path.basename(file_path)

        if ext == ".pdf":
            reader = PdfReader(file_path)
            # 关键修改：逐页循环
            for page_idx, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if not page_text:
                    continue

                # 清洗这一页的文字
                clean_page_text = self._clean_text(page_text)
                # 这一页切成多个小块
                page_chunks = self._semantic_chunking(clean_page_text)

                for i, chunk in enumerate(page_chunks):
                    all_chunks.append(chunk)
                    # 为每一块注入具体的页码 (page_idx + 1)
                    all_metadata.append({
                        "source": doc_name,
                        "page": page_idx + 1,
                        "chunk_index": i
                    })
            print(f"✅ PDF 解析完成，共处理 {len(reader.pages)} 页")

        elif ext == ".txt":
            # TXT 没有页码概念，默认给 1
            with open(file_path, 'r', encoding='utf-8') as f:
                full_text = f.read()
            all_chunks = self._semantic_chunking(self._clean_text(full_text))
            all_metadata = [{"source": doc_name, "page": 1, "chunk_index": i} for i in range(len(all_chunks))]

        # 存入数据库
        if all_chunks:
            self.add_to_store(all_chunks, all_metadata)
            print(f"✨ 成功将 {len(all_chunks)} 个带页码的片段存入 ChromaDB")

        return all_chunks

    def add_to_store(self, chunks: List[str], metadata: List[Dict[str, Any]]):
        """
        Generates embeddings and upserts to ChromaDB.
        """
        if not chunks:
            return

        print(f"Embedding and storing {len(chunks)} chunks...")
        embeddings = self.model.encode(chunks).tolist()
        ids = [f"id_{os.urandom(4).hex()}_{i}" for i in range(len(chunks))]

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadata
        )

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Semantic search for relevant IFRS 17 context.
        """
        query_embedding = self.model.encode([query]).tolist()

        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=k
        )

        formatted_results = []
        for i in range(len(results['documents'][0])):
            formatted_results.append({
                "content": results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "distance": results['distances'][0][i]
            })

        return formatted_results

if __name__ == "__main__":
    # Test Block
    engine = VectorEngine(db_path="./test_chroma_db")

    test_text = (
        "IFRS 17 establishes principles for the recognition, measurement, presentation and disclosure of insurance contracts. "
        "The objective of IFRS 17 is to ensure that an entity provides relevant information that faithfully represents those contracts. "
        "This information gives a basis for users of financial statements to assess the effect that insurance contracts have on the entity's financial position. "
        "The General Measurement Model is the default approach for all insurance contracts. "
        "The Contractual Service Margin (CSM) represents the unearned profit of the group of insurance contracts that the entity will recognise as it provides services in the future."
    )

    print("Running test ingestion...")
    chunks = engine._semantic_chunking(test_text)
    metadata = [{"source": "test_dummy", "chunk_index": i} for i in range(len(chunks))]
    engine.add_to_store(chunks, metadata)

    query = "What is the Contractual Service Margin?"
    print(f"Searching for: '{query}'")
    search_results = engine.search(query, k=2)

    for idx, res in enumerate(search_results):
        print(f"\nResult {idx+1} (Distance: {res['distance']:.4f}):")
        print(f"Content: {res['content']}")
