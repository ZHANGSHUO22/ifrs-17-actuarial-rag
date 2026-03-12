# Vector Engine 核心实现
import os
import re
from typing import List, Dict, Any
import chromadb
from sentence_transformers import SentenceTransformer
import fitz  # PyMuPDF

# ==========================================
# 🔧 工具类 1：IFRS 专用切分器 (纯文本版 - 无星号)
# ==========================================
class UniversalIFRSSplitter:
    def __init__(self):
        self.pattern = re.compile(r'(?:^|\n)((?:\d+\.|[A-Z]{1,2}\d+\.|Appendix\s+[A-Z])\s+)')

    def split(self, text: str) -> List[Dict[str, Any]]:
        parts = self.pattern.split(text)
        chunks = []

        if parts[0].strip():
            chunks.append({
                "para_id": "Header/Intro",
                "content": parts[0].strip(),
                "type": "header"
            })

        for i in range(1, len(parts), 2):
            para_id_raw = parts[i].strip()
            content_text = parts[i+1].strip()
            para_id = para_id_raw.rstrip('.')

            # ✅ 修复：不再加 **，使用纯文本
            full_text = f"{para_id_raw} {content_text}"

            chunks.append({
                "para_id": para_id,
                "content": full_text,
                "type": "clause"
            })

        return chunks

# ==========================================
# 🔧 工具类 2：通用递归切分器
# ==========================================
class RecursiveSplitter:
    def __init__(self, chunk_size=800, overlap=100):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text: str) -> List[str]:
        chunks = []
        start = 0
        text_len = len(text)
        while start < text_len:
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start += (self.chunk_size - self.overlap)
        return chunks

# ==========================================
# 🚀 核心引擎 (Vector Engine)
# ==========================================
class VectorEngine:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(VectorEngine, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = "./chroma_db", collection_name: str = "ifrs17_docs"):
        if hasattr(self, 'initialized') and self.initialized:
            return
        os.makedirs(db_path, exist_ok=True)
        self._model = None
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
        if self._model is None:
            print("Loading 🌍 Multilingual-MiniLM model (First time download may take a minute)...")
            # 🌟 核心修改：换成支持 50+ 语言的轻量级模型
            self._model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        return self._model

    def _clean_text(self, text: str) -> str:
        if not text: return ""
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'[ \t\f\v]+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()

    def _detect_document_type(self, sample_text: str) -> str:
        sample = sample_text.lower()
        scores = {"IFRS": 0, "EU_LAW": 0, "CZ_LAW": 0}
        if "international financial reporting standard" in sample: scores["IFRS"] += 5
        if "international accounting standards board" in sample: scores["IFRS"] += 5
        scores["IFRS"] += sample.count("ifrs ") * 1
        best_category = max(scores, key=scores.get)
        if scores[best_category] >= 4:
            return best_category
        return "GENERIC"

    # ✅ 核心辅助函数：根据索引找页码
    def _get_page_number(self, pos: int, offsets: List[tuple]) -> int:
        found_page = 1
        for start_pos, page_num in offsets:
            if pos >= start_pos:
                found_page = page_num
            else:
                break
        return found_page

    def ingest_document(self, file_path: str) -> List[str]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at: {file_path}")

        doc_name = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        print(f"📖 正在扫描文档: {doc_name}")

        full_cleaned_text = ""
        sample_text = ""
        page_offsets = []

        # --- 1. 读取并逐页构建坐标系 ---
        if ext == ".pdf":
            try:
                doc = fitz.open(file_path)
                for i in range(min(3, len(doc))):
                    sample_text += doc[i].get_text() + "\n"

                for page in doc:
                    raw_text = page.get_text()
                    # 必须在这里清洗，保证 offsets 记录的是清洗后文本的位置
                    cleaned_page = self._clean_text(raw_text) + "\n\n"
                    current_start_index = len(full_cleaned_text)
                    page_offsets.append((current_start_index, page.number + 1))
                    full_cleaned_text += cleaned_page
                doc.close()
            except Exception as e:
                print(f"❌ PyMuPDF 读取失败: {e}")
                return []

        elif ext == ".txt":
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_content = f.read()
                full_cleaned_text = self._clean_text(raw_content)
                sample_text = full_cleaned_text[:2000]
                page_offsets.append((0, 1))

        # --- 2. 识别类型 ---
        doc_type = self._detect_document_type(sample_text)
        print(f"🔍 [识别结果] 类型: 【{doc_type}】")

        chunks_to_add = []
        metadatas = []

        # --- 3. 路由分发 ---
        if doc_type == "IFRS":
            print("🔧 启用 IFRS 结构化切分 (纯文本模式 + 页码计算)...")
            splitter = UniversalIFRSSplitter()
            structured_chunks = splitter.split(full_cleaned_text)

            last_found_pos = 0

            for item in structured_chunks:
                content = item["content"] # "47. An entity..."
                if len(content) < 5: continue

                # === 🚀 核心逻辑：在全文中找位置 ===
                # 1. 构造头部字符串 "47."
                header_part = f"{item['para_id']}."

                # 2. 移除头部，只拿正文去搜 " An entity..."
                body_only = content.replace(header_part, "", 1).strip()
                search_anchor = body_only[:50]
                if not search_anchor: search_anchor = item['para_id']

                # 3. 查找
                pos = full_cleaned_text.find(search_anchor, last_found_pos)

                if pos == -1:
                    # 备用方案：搜 ID
                    alt_anchor = item["para_id"] + "."
                    pos = full_cleaned_text.find(alt_anchor, last_found_pos)
                    if pos != -1: last_found_pos = pos
                else:
                    last_found_pos = pos

                # 4. 计算页码
                determined_page = self._get_page_number(last_found_pos, page_offsets)

                chunks_to_add.append(content)
                metadatas.append({
                    "source": doc_name,
                    "para_id": item["para_id"],
                    "page": determined_page, # ✅ 必须有这个字段！
                    "doc_type": "IFRS",
                    "parent_context": "true"
                })

        else:
            # Generic 模式
            print("🔧 启用通用切分...")
            splitter = RecursiveSplitter()
            raw_chunks = splitter.split(full_cleaned_text)
            current_scan_pos = 0
            for chunk in raw_chunks:
                page_num = self._get_page_number(current_scan_pos, page_offsets)
                chunks_to_add.append(chunk)
                metadatas.append({
                    "source": doc_name,
                    "page": page_num, # ✅ 通用模式也要有
                    "doc_type": doc_type
                })
                current_scan_pos += len(chunk)

        # --- 4. 存库 ---
        if chunks_to_add:
            self.add_to_store(chunks_to_add, metadatas)
            print(f"✨ 成功存入 {len(chunks_to_add)} 个语义块")

        return chunks_to_add

    def add_to_store(self, chunks: List[str], metadata: List[Dict[str, Any]]):
        if not chunks: return
        print(f"🚀 Embedding {len(chunks)} chunks...")
        embeddings = self.model.encode(chunks).tolist()

        ids = []
        for i, meta in enumerate(metadata):
            source = meta.get("source", "unknown")
            p_id = meta.get("paragraph_id", "chunk")
            # 移除随机数，避免重复数据堆积 (可选，但在开发阶段好用)
            clean_id = f"{source}_{p_id}_{i}".replace(" ", "_")
            ids.append(clean_id)

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadata
        )

    def search(self, query: str, k: int = 5, filters: Dict = None) -> List[Dict[str, Any]]:
        query_embedding = self.model.encode([query]).tolist()
        where_clause = filters if filters else None

        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=k,
            where=where_clause
        )

        formatted_results = []
        if results['documents']:
            for i in range(len(results['documents'][0])):
                # 兼容处理
                meta = results['metadatas'][0][i]
                formatted_results.append({
                    "content": results['documents'][0][i],
                    "metadata": meta,
                    "distance": results['distances'][0][i]
                })
        return formatted_results
