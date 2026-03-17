# Vector Engine 核心实现
import os
import re
from typing import List, Dict, Any
import chromadb
from sentence_transformers import SentenceTransformer
import fitz  # PyMuPDF
import time

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer
from optimum.onnxruntime import ORTModelForFeatureExtraction

# ==========================================
# 🔧 工具类 1：IFRS 专用切分器 (工业级防弹版)
# ==========================================
class UniversalIFRSSplitter:
    def __init__(self):
        # 🌟 真正的终极正则：
        # (?m) 开启多行模式，让 ^ 能匹配每一行的开头。
        # (?=...) 是“零宽断言”，只负责“看”后面有没有点号或空白，绝对不“吃”掉它们！
        self.pattern = re.compile(r'(?m)^([A-Z]?\d{1,3}(?:\.\d{1,3})*(?:[A-Z]{1,2})?|Appendix\s+[A-Z])(?=\.\s|\s*$)')

    def split(self, text: str) -> List[Dict[str, Any]]:
        parts = self.pattern.split(text)
        chunks = []

        # 1. 处理开头的引言/通用部分 (保留全量文本，移除 debug 的截断)
        if parts[0].strip():
            chunks.append({
                "para_id": "Header/Intro",
                "content": parts[0].strip(),
                "type": "header"
            })

        # 2. 遍历提取的所有法规段落
        for i in range(1, len(parts), 2):
            para_id = parts[i].strip()

            # 因为断言没有吃掉字符，所以文本开头可能留着 ". " 或者换行符。
            # 洗掉开头的点，再剥除空白，获取纯净的正文。
            content_text = parts[i+1].strip().lstrip('.').strip()

            # 🚀 熔断机制：过滤掉极短的干扰项（比如欧盟法规里的 M6, VB 等孤立排版字符）
            if len(content_text) < 5:
                continue

            # 🌟 组合最终入库的文本：强制加上一个规范的点，给大模型提供完美的上下文
            # 这样入库的文本会变成："5A. The credit risk disclosure requirements..."
            full_text = f"{para_id}. {content_text}"

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
# ⚡ 极速推理引擎：ONNX INT8 专用
# ==========================================
class ONNXEmbeddingEngine:
    def __init__(self, model_path: str):
        # (这部分保持不变，保留之前写的从官方拉字典的代码)
        print(f"🚀 Loading Quantized INT8 Engine from {model_path}...")
        self.tokenizer = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
        self.model = ORTModelForFeatureExtraction.from_pretrained(model_path, file_name="model_quantized.onnx")

    # 🌟 替换这里的 encode 方法，加入 tqdm 显示进度和 batch 机制
    def encode(self, texts, batch_size=16):
        import torch
        import torch.nn.functional as F
        from tqdm import tqdm # 如果你没装 tqdm，可以在终端运行 pip install tqdm
        import numpy as np

        is_single_string = isinstance(texts, str)
        texts_list = [texts] if is_single_string else texts

        all_embeddings = []

        # 🌟 核心提速秘籍：分批处理 (Batching)
        # 加上 tqdm 可以让你在终端看到炫酷的进度条，不再盲目等待！
        for i in tqdm(range(0, len(texts_list), batch_size), desc="Encoding Chunks"):
            batch_texts = texts_list[i: i + batch_size]

            # 1. 文本转 Token
            inputs = self.tokenizer(batch_texts, max_length=512, padding=True, truncation=True, return_tensors='pt')

            # 2. ONNX 极速推理
            with torch.no_grad():
                outputs = self.model(**inputs)

            # 3. E5 专属的平均池化
            attention_mask = inputs['attention_mask']
            last_hidden = outputs.last_hidden_state.masked_fill(~attention_mask[..., None].bool(), 0.0)
            batch_embeddings = last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]

            # 4. 归一化处理
            batch_embeddings = F.normalize(batch_embeddings, p=2, dim=1)
            all_embeddings.extend(batch_embeddings.numpy())

        # 将所有的 batch 结果合并
        result = np.array(all_embeddings)

        if is_single_string:
            return result[0]
        return result
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
            model_path = "./backend/ml_models/e5-large-int8"
            self._model = ONNXEmbeddingEngine(model_path=model_path)
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

    def ingest_document(self, file_path: str, user_id: str = "public") -> List[str]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at: {file_path}")

        MAX_CHUNKS_PER_USER = 5000 # 每个普通用户的免费切片额度

        if user_id != "public":
            try:
                # 去数据库里查一下这个 user_id 名下已经存了多少个切片
                existing_data = self.collection.get(where={"user_id": user_id}, include=[])
                current_usage = len(existing_data['ids']) if existing_data and existing_data['ids'] else 0

                print(f"📊 [配额检查] 用户 {user_id} 当前已用切片: {current_usage} / {MAX_CHUNKS_PER_USER}")

                if current_usage >= MAX_CHUNKS_PER_USER:
                    print(f"❌ [拦截] 用户 {user_id} 的存储配额已耗尽！")
                    raise Exception(f"Quota Exceeded: 您的专属向量库容量已满 ({MAX_CHUNKS_PER_USER} 块)，请联系管理员升级或清理历史文件。")
            except Exception as e:
                if "Quota Exceeded" in str(e):
                    raise e
                print(f"⚠️ 无法获取用户配额状态，放行: {e}")

        doc_name = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        print(f"📖 正在扫描文档: {doc_name} (归属: {user_id})")

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
                    "parent_context": "true",
                    "user_id": user_id,
                    "upload_timestamp": int(time.time())
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
    # ==========================================
    # 🗑️ 数据清理：彻底删除某文件的所有向量切片
    # ==========================================
    def delete_document(self, filename: str, user_id: str):
        print(f"🗑️ [引擎粉碎机] 正在抹除用户 {user_id} 的文件: {filename}")
        try:
            # 🌟 必须使用双重复合锁：既要匹配文件名，又要匹配是该用户！
            # 绝对防止黑客恶意删除 public 基础库或其他人的文件
            delete_filter = {
                "$and": [
                    {"source": filename},
                    {"user_id": user_id}
                ]
            }

            # 1. 先查出到底有多少个切片的 ID 符合条件
            results = self.collection.get(where=delete_filter, include=[])
            ids_to_delete = results.get("ids", [])

            if ids_to_delete:
                # 2. 执行真正的物理抹除
                self.collection.delete(ids=ids_to_delete)
                print(f"✅ 成功从 ChromaDB 彻底清除了 {len(ids_to_delete)} 个相关数据块！")
            else:
                print("⚠️ 未在向量库中找到对应文件，可能已经被清理过了。")

        except Exception as e:
            print(f"❌ 向量库清理失败: {e}")
            raise e

    def add_to_store(self, chunks: List[str], metadata: List[Dict[str, Any]]):
        if not chunks: return
        print(f"🚀 Embedding {len(chunks)} chunks using E5-large...")

        # 🌟 E5 强制规则：存入数据库的文档必须带上 "passage: " 前缀
        passages = [f"passage: {chunk}" for chunk in chunks]

        # 注意：这里 encode 的是加了前缀的 passages，但存入数据库的 document 依然是原始的 chunks
        embeddings = self.model.encode(passages).tolist()

        ids = []
        for i, meta in enumerate(metadata):
            source = meta.get("source", "unknown")
            p_id = meta.get("para_id", "chunk")
            # 移除随机数，避免重复数据堆积 (可选，但在开发阶段好用)
            clean_id = f"{source}_{p_id}_{i}".replace(" ", "_")
            ids.append(clean_id)

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadata
        )

    def search(self, query: str, max_k: int = 20, filters: Dict = None) -> List[Dict[str, Any]]:
        """
        🚀 动态阈值检索：只返回真正相关的片段，拒绝凑数！
        """
        # 1. 给问题加上 E5 强制的查询前缀
        e5_query = f"query: {query}"

        # 2. 依然调用极速引擎，把传入的单句放入列表中处理，引擎返回二维数组，我们取第一个
        query_embedding = self.model.encode([e5_query])[0].tolist()

        # 3. 贪婪召回：先向数据库狮子大开口，要前 20 名（扩大基础池）
        where_clause = filters if filters else None
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=max_k,
            where=where_clause,
            include=['metadatas', 'documents', 'distances'] # 必须要求返回距离分数！
        )

        if not results['ids'][0]:
            return []

        # 4. 提取原始数据
        distances = results['distances'][0]
        metadatas = results['metadatas'][0]
        documents = results['documents'][0]
        ids = results['ids'][0]

        # # ==========================================
        # # 🌟 核心算法：带“法律级保底”的动态落差截断
        # # ==========================================
        # final_results = []

        # DROP_THRESHOLD = 0.020        # 你的专属致密空间落差阈值
        # ABSOLUTE_MAX_DISTANCE = 0.250 # 绝对垃圾箱阈值
        # MIN_K = 3                     # 🛡️ 法律级护城河：保底召回数量

        # # 第 1 名无条件入选（只要它不是离谱的垃圾）
        # if distances[0] <= ABSOLUTE_MAX_DISTANCE:
        #     final_results.append({
        #         "id": ids[0],
        #         "content": documents[0],
        #         "metadata": metadatas[0],
        #         "distance": distances[0]
        #     })

        # # 从第 2 名开始，逐个判断
        # for i in range(1, len(distances)):
        #     current_dist = distances[i]
        #     prev_dist = distances[i-1]
        #     jump = current_dist - prev_dist

        #     # 🛡️ 触发截断条件 1：已经满足了保底数量 (MIN_K)，且出现了语义断层
        #     if i >= MIN_K and jump > DROP_THRESHOLD:
        #         print(f"🔪 触发动态截断！第 {i+1} 名距离发生断崖式跳水 (落差 {jump:.4f})")
        #         break

        #     # 🗑️ 触发截断条件 2：绝对距离太远，坚决不要（就算在保底名额内，如果是纯垃圾也不收）
        #     if current_dist > ABSOLUTE_MAX_DISTANCE:
        #         print(f"🔪 触发绝对截断！第 {i+1} 名距离太远 ({current_dist:.4f})")
        #         break

        #     # 顺利通过滤网，加入结果集
        #     final_results.append({
        #         "id": ids[i],
        #         "content": documents[i],
        #         "metadata": metadatas[i],
        #         "distance": current_dist
        #     })

        # print(f"🎯 检索完毕：向数据库请求了 {max_k} 个，最终为您呈上 {len(final_results)} 个最核心的合规片段。")
        # return final_results


		# ==========================================
        # ⚠️ 调试模式：关闭所有截断，无脑返回全部 Top-K (20个) 切片
        # ==========================================
        final_results = []

        for i in range(len(distances)):
            # 记录每一次的距离，方便我们在终端观察中文跨语言的真实分数
            print(f"🔍 强制召回第 {i+1} 名 | 距离: {distances[i]:.4f}")

            final_results.append({
                "id": ids[i],
                "content": documents[i],
                "metadata": metadatas[i],
                "distance": distances[i]
            })

        print(f"🎯 调试检索完毕：未开启截断，强制为您呈上全部 {len(final_results)} 个片段。")
        return final_results
