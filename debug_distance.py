import os
from backend.app.services.rag.vector_engine import VectorEngine

def run_sonar_test():
    print("🚀 启动向量引擎雷达探测 (正则修复验证版)...")
    engine = VectorEngine()

    # 1. 替换为导致你报错的中文问题
    query = "保险业在亏损合同中是怎么处理的"
    e5_query = f"query: {query}"

    # 2. 🌟 替换为你刚刚测试的 IFRS 7 文件名 (确保名字和你前端上传的一致)
    target_file = "ifrs7_eu_07.2025.pdf"

    # ==========================================
    # 🌟 新增体检逻辑：先查一下新正则到底切出了多少块？
    # ==========================================
    try:
        all_docs = engine.collection.get(where={"source": target_file}, include=['metadatas'])
        total_chunks = len(all_docs['ids']) if all_docs['ids'] else 0
        print(f"\n📊 [数据库体检] 文件 '{target_file}' 在数据库中共有: {total_chunks} 个切片！")

        if total_chunks == 0:
            print("❌ 警告：数据库里完全没有这个文件！请检查是否已在前端重新上传。")
            return
        elif total_chunks <= 10:
            print("⚠️ 警告：切片数量依然极少！说明新正则没起效，或者你忘记删掉旧的 chroma_db 文件夹了！\n")
        else:
            print("✅ 恭喜！切片数量正常 (几百块)，新正则完美生效了！\n")
    except Exception as e:
        print(f"检查数据库时出错: {e}")

    # ==========================================

    # 极速生成向量
    print(f"🧠 正在将中文问题转化为高维向量...")
    query_embedding = engine.model.encode([e5_query])[0].tolist()

    # 3. 模拟前端传递的过滤条件
    where_filter = {"source": target_file}

    print(f"📡 正在扫描 ChromaDB 空间距离...")
    print(f"🔒 启用的过滤条件: {where_filter}")

    # 穿透到底层 ChromaDB
    results = engine.collection.query(
        query_embeddings=[query_embedding],
        n_results=20,
        where=where_filter,
        include=['metadatas', 'distances', 'documents']
    )

    # 🚨 拦截空结果报错
    if not results['ids'][0]:
        print("\n" + "❌"*25)
        print("惨烈失败！ChromaDB 在这个过滤条件下连一条数据都没搜到！")
        print("❌"*25 + "\n")
        return

    distances = results['distances'][0]
    metadatas = results['metadatas'][0]
    documents = results['documents'][0]

    print("\n" + "="*50)
    print(f"🎯 前 {len(distances)} 名切片的真实距离分数 (中搜英跨语言):")
    for i in range(len(distances)):
        doc = metadatas[i].get('source', 'Unknown')
        page = metadatas[i].get('page', 'N/A')
        para = metadatas[i].get('para_id', 'N/A')
        dist = distances[i]

        # 截取前 60 个字符看看内容
        snippet = documents[i][:60].replace('\n', ' ') + "..."

        jump = dist - distances[i-1] if i > 0 else 0.0

        print(f"[{i+1}] 距离: {dist:.4f} | 落差: +{jump:.4f} | 页: {page} | 段: {para}")
        print(f"    💡 预览: {snippet}")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_sonar_test()
