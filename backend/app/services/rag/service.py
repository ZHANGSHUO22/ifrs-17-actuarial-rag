import time
import os
import traceback
from fastapi import HTTPException
from app.models.api_models import QueryRequest, QueryResponse, SourceMetadata
from app.services.llm.gemini_client import GeminiClient
from app.services.rag.vector_engine import VectorEngine

class RAGService:
    def __init__(self):
        # 1. 初始化 LLM
        self.llm_client = GeminiClient()

        # 2. 初始化 向量引擎
        self.vector_engine = VectorEngine()

        print("✅ RAGService Initialized: LLM & VectorEngine ready.")

    async def answer_query(self, request: QueryRequest) -> QueryResponse:
        start_time = time.time()
        query = request.query

        # 构建搜索过滤器
        search_filters = None # 默认为 None，防止传空字典导致某些版本的 Chroma 报错
        if request.selected_files and len(request.selected_files) > 0:
            search_filters = {
                "source": {"$in": request.selected_files}
            }

        try:
            print(f"\n" + "="*50)
            print(f"🔍 收到提问: {query}")

            # 1. 向量搜索
            results = self.vector_engine.search(query, k=20, filters=search_filters)
            print(f"📂 向量数据库返回了 {len(results)} 个相关片段")

			# 🔥🔥🔥 新增调试代码 START 🔥🔥🔥
            print("\n--- 🕵️‍♂️ DEBUG: 检查检索到的元数据 ---")
            for idx, r in enumerate(results):
                # 兼容性处理获取 metadata
                meta = r.get("metadata", {}) if isinstance(r, dict) else r.metadata
                p_num = meta.get("page_number", "MISSING")
                p_id = meta.get("paragraph_id", "MISSING")
                print(f"片段 {idx+1}: Page={p_num} | Para={p_id}")
            print("--------------------------------------\n")
            # 🔥🔥🔥 新增调试代码 END 🔥🔥🔥

            # --- 2. 构建上下文 (Context Construction) ---
            context_pieces = []
            for i, r in enumerate(results):
                # 统一提取逻辑
                if isinstance(r, dict):
                    meta = r.get("metadata", {})
                    content = r.get("content", "")
                else:
                    meta = r.metadata
                    content = r.page_content

                src = meta.get("source", "Unknown")
                page = meta.get("page_number", "?")

                # 拼接上下文片段
                context_pieces.append(f"Source {i+1} (Doc: {src} | Page: {page}):\n{content}")

            context_text = "\n\n".join(context_pieces)
            if not context_text:
                context_text = "No relevant regulatory context found."

            # --- 3. 智能提示词 (Smart Prompt) ---
            prompt = f"""
            You are an expert Actuarial Consultant specializing in IFRS 17.

            Context:
            {context_text}

            User Question: {query}

            Instructions:
            1. Answer based ONLY on the provided context.
            2. If the context doesn't contain the answer, admit it.
            3. Cite sources using the Document Name and Paragraph ID if available.

            IMPORTANT - LANGUAGE:
            - **Answer in the SAME language as the User Question.**
            - If Czech -> Answer in Czech.
            - If English -> Answer in English.
            """

            # --- 4. 生成回答 ---
            answer = await self.llm_client.generate(prompt)

            # --- 5. 构造返回数据 (Source Metadata) ---
            sources_list = []
            for r in results:
                # 统一提取逻辑
                if isinstance(r, dict):
                    meta = r.get("metadata", {})
                    content = r.get("content", "")
                else:
                    meta = r.metadata
                    content = r.page_content

                # [FIXED] 变量名统一修复
                # 无论走哪个分支，这里都叫 src_name
                full_src_path = meta.get("source", "Unknown")
                src_name = os.path.basename(full_src_path)

                # 确保 page_number 是 int
                try:
                    page_val = int(meta.get("page_number", 1))
                except:
                    page_val = 1

                para_val = str(meta.get("paragraph_id", "N/A"))

                sources_list.append(SourceMetadata(
                    document_id=src_name, # ✅ 现在 src_name 肯定有值了
                    page_number=page_val,
                    text_snippet=str(content[:150].replace("\n", " ")),
                    paragraph_id=para_val
                ))

            # --- 6. 返回结果 ---
            return QueryResponse(
                answer=answer,
                sources=sources_list,
                process_time=time.time() - start_time
            )

        except Exception as e:
            print(f"❌ Error in answer_query: {str(e)}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
