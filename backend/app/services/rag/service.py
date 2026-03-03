import time
import os
from fastapi import HTTPException
from app.models.api_models import QueryRequest, QueryResponse, SourceMetadata
from app.services.llm.gemini_client import GeminiClient

# ✅ 核心修复：根据你刚才 ls 出来的文件路径，正确的导入是这个！
from app.services.rag.vector_engine import VectorEngine

class RAGService:
    def __init__(self):
        # 1. 初始化 LLM
        self.llm_client = GeminiClient()

        # 2. 初始化 向量引擎
        # 统一叫 self.vector_engine
        self.vector_engine = VectorEngine()

        print("✅ RAGService Initialized: LLM & VectorEngine ready.")

    async def answer_query(self, request: QueryRequest) -> QueryResponse:
        """
        修复版：
        1. 导入路径修正为 app.services.rag.vector_engine
        2. 变量名统一为 self.vector_engine
        3. 兼容 Document 对象 (r.page_content)
        """
        start_time = time.time()
        query = request.query

        # (可选) 限流
        # if not await global_limiter.check_limit("user"): ...

        try:
            print(f"\n" + "="*50)
            print(f"🔍 收到提问: {query}")

            # --- 1. 检索 (Retrieval) ---
            # 尝试调用 search() 或 similarity_search()
            # ⚠️ 注意：如果你之前的 VectorEngine 类用的是 .similarity_search()，请保留这个
            # 如果报错 "object has no attribute 'search'"，请把下面改成 .similarity_search(query, k=20)
            try:
                results = self.vector_engine.search(query, k=20)
            except AttributeError:
                # 容错处理：如果 vector_engine 没有 search 方法，试试 similarity_search
                results = self.vector_engine.similarity_search(query, k=20)

            print(f"📂 向量数据库返回了 {len(results)} 个相关片段")

            # --- 2. 构建上下文 ---
            # 这里我们要小心：results 里的东西可能是字典(dict)也可能是对象(Document)
            # 为了稳健，我们做一个判断
            context_pieces = []
            for i, r in enumerate(results):
                # 兼容性处理：判断 r 是对象还是字典
                if isinstance(r, dict):
                    content = r.get("content") or r.get("page_content", "")
                    src = r.get("metadata", {}).get("source", "Unknown")
                    page = r.get("metadata", {}).get("page", "?")
                else:
                    # 它是 Document 对象
                    content = r.page_content
                    src = r.metadata.get("source", "Unknown")
                    page = r.metadata.get("page", "?")

                context_pieces.append(f"Source {i+1} (Doc: {src} | Page: {page}):\n{content}")

            context_text = "\n\n".join(context_pieces)

            if not context_text:
                context_text = "No relevant regulatory context found."

            # --- 3. 智能提示词 (Smart Prompt) ---
            prompt = f"""
            You are an expert IFRS 17 Actuarial Consultant.

            Context:
            {context_text}

            User Question: {query}

            Instructions:
            1. Answer based ONLY on the context.
            2. Cite sources.

            IMPORTANT - LANGUAGE:
            - **Answer in the SAME language as the User Question.**
            - If Czech -> Answer in Czech.
            - If English -> Answer in English.
            - If Turkish -> Answer in Turkish.
            - If Slovak -> Answer in Slovak.
            """

            # --- 4. 生成回答 ---
            answer = await self.llm_client.generate(prompt)

            # --- 5. 构造返回数据 ---
            sources_list = []
            for r in results:
                # 同样做兼容处理
                if isinstance(r, dict):
                    content = r.get("content") or r.get("page_content", "")
                    src = os.path.basename(r.get("metadata", {}).get("source", "Unknown"))
                    page = int(r.get("metadata", {}).get("page", 1))
                else:
                    content = r.page_content
                    src = os.path.basename(r.metadata.get("source", "Unknown"))
                    page = int(r.metadata.get("page", 1))

                sources_list.append(SourceMetadata(
                    document_id=src,
                    page_number=page,
                    text_snippet=str(content[:150].replace("\n", " "))
                ))

            # --- 6. 返回结果 ---
            return QueryResponse(
                answer=answer,
                sources=sources_list,
                process_time=time.time() - start_time
            )

        except Exception as e:
            print(f"❌ Error in answer_query: {str(e)}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
