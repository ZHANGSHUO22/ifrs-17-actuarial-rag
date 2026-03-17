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

    async def answer_query(self, request: QueryRequest, user_id: str = "public") -> QueryResponse:
        start_time = time.time()
        query = request.query

        # 1. 构建身份锁 (只允许看自己的私有文件，或者公共基础文件)
        user_filter = {
            "$or": [
                {"user_id": user_id},
                {"user_id": "public"}
            ]
        }

        # 2. 构建搜索过滤器 (为绝对兼容的 ChromaDB 查询语法)
        search_filters = None
        if request.selected_files and len(request.selected_files) > 0:
            # 构建文件锁
            if len(request.selected_files) == 1:
                file_filter = {"source": request.selected_files[0]}
            else:
                file_filter = {"$or": [{"source": f} for f in request.selected_files]}

            # 🌟 复合锁：使用 $and 把“身份”和“文件”死死焊在一起！
            search_filters = {
                "$and": [
                    file_filter,
                    user_filter
                ]
            }
        else:
            # 如果没选文件，就全局搜索（但依然被身份锁死死限制，绝不会越界）
            search_filters = user_filter

        # 💡 加一个探照灯打印，让你清楚看到传给数据库的“锁”到底是什么
        print(f"🔒 [租户隔离防线] 当前生效的复合过滤条件: {search_filters}")

        try:
            print(f"\n" + "="*50)
            print(f"🔍 收到提问: {query}")

            # 1. 向量搜索 (把带着复合锁的 search_filters 传进去)
            results = self.vector_engine.search(query, max_k=20, filters=search_filters)
            print(f"📂 向量数据库返回了 {len(results)} 个相关片段")

            # ==========================================
            # 🌟统一数据清洗区 (Data Normalization)
            # ==========================================
            parsed_chunks = []
            for r in results:
                meta = r.get("metadata", {}) if isinstance(r, dict) else r.metadata
                content = r.get("content", "") if isinstance(r, dict) else r.page_content

                src_path = meta.get("source", "Unknown")

                # 🚨 终极探测器：把第一条切片的真实字典结构打印出来看看！
                if len(parsed_chunks) == 0:
                    print(f"🧬 [底层元数据解剖] ChromaDB 给出的真实 meta 字典是: {meta}")

                # 💡 核心修复：多键名兜底匹配 (Fallback)
                # 尝试拿 page_number，拿不到就拿 page，再拿不到才给默认值 1
                raw_page = meta.get("page_number") or meta.get("page") or 1
                try:
                    page_val = int(raw_page)
                except:
                    page_val = 1

                # 尝试拿 para_id，拿不到就尝试 para，或者保持 N/A
                para_val = str(meta.get("para_id") or meta.get("para") or "N/A")

                # 组装成“标准净菜”
                parsed_chunks.append({
                    "content": content,
                    "document_id": os.path.basename(src_path),
                    "page_number": page_val,
                    "para_id": para_val
                })

            print("\n--- 🕵️‍♂️ DEBUG: 检查检索到的顶级切片 ---")
            for idx, chunk in enumerate(parsed_chunks):
                print(f"片段 {idx+1}: Doc={chunk['document_id']} | Page={chunk['page_number']} | Para={chunk['para_id']}")
            print("--------------------------------------\n")

            # --- 2. 组装上下文 & 返回前端的数据 ---
            context_pieces = []
            sources_list = []

            for i, chunk in enumerate(parsed_chunks):
                context_pieces.append(
                    f"[Source {i+1}] (Doc: {chunk['document_id']} | Page: {chunk['page_number']} | Para: {chunk['para_id']}):\n{chunk['content']}"
                )
                sources_list.append(SourceMetadata(
                    document_id=chunk['document_id'],
                    page_number=chunk['page_number'],
                    text_snippet=chunk['content'][:150].replace("\n", " "),
                    para_id=chunk['para_id']
                ))

            context_text = "\n\n".join(context_pieces) if context_pieces else "No relevant regulatory context found."

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
            4. If referencing a specific table or calculation formula, preserve the exact formatting from the context.

            IMPORTANT - LANGUAGE:
            - **Answer in the SAME language as the User Question.**
            - If Czech -> Answer in Czech.
            - If English -> Answer in English.
            """

            # --- 4. 生成回答 ---
            answer = await self.llm_client.generate(prompt)


            # --- 5. 返回结果 ---
            return QueryResponse(
                answer=answer,
                sources=sources_list, # 👈 直接使用第 2 步完美清洗好的数据！
                process_time=time.time() - start_time
            )


        except Exception as e:
            print(f"❌ Error in answer_query: {str(e)}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
