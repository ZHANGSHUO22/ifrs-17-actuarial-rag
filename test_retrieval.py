import os
import sys
from pathlib import Path

# 把当前目录加入路径，防止找不到包
sys.path.append(str(Path(__file__).resolve().parent))

from backend.app.services.rag.vector_engine import VectorEngine

def run_language_test():
    print("🚀 正在加载向量引擎...")
    engine = VectorEngine(db_path="./chroma_db")

    # 我们用同一个问题，三种语言
    queries = {
        "🇬🇧 英语 (基准)": "How is a group of onerous contracts measured on initial recognition?",
        "🇨🇿 捷克语 (你的直觉)": "Jak se oceňuje skupina nevýhodných smluv při prvotním zachycení?",
        "🇨🇳 中文 (翻车案例)": "亏损合同组在初始确认时应该如何计量？"
    }

    for lang, q_text in queries.items():
        print(f"\n=====================================")
        print(f"🔍 测试语言: {lang}")
        print(f"💬 查询内容: {q_text}")

        # 将问题转为向量
        query_embedding = engine.model.encode(q_text).tolist()

        # 直接去 ChromaDB 搜最相关的前 3 条
        results = engine.collection.query(
            query_embeddings=[query_embedding],
            n_results=3
        )

        print(f"\n🏆 召回的前 3 个片段 (Top 3 Chunks):")
        for i, (doc, meta) in enumerate(zip(results['documents'][0], results['metadatas'][0])):
            para_id = meta.get('para_id', 'Unknown')
            page = meta.get('page', 'Unknown')
            # 截取前 100 个字符展示
            preview = doc[:100].replace('\n', ' ')
            print(f"  [{i+1}] 段落 {para_id} (第 {page} 页) -> {preview}...")

if __name__ == "__main__":
    run_language_test()
