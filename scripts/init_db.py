import os
import sys

# --- 关键步骤：把项目根目录加入 Python 搜索路径 ---
# 获取当前脚本所在目录 (scripts) 的上一级目录 (根目录)
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
sys.path.append(root_dir)

# 现在可以正常导入后端代码了
from backend.app.services.rag.vector_engine import VectorEngine

def init_public_knowledge_base():
    # 1. 定义内置文件的路径
    public_dir = os.path.join(root_dir, "knowledge_base", "public")

    # 2. 初始化向量引擎
    # 注意：这里会使用 vector_engine.py 里默认的数据库路径
    print("🚀 正在初始化向量引擎...")
    engine = VectorEngine()

    # 3. 检查文件夹是否存在
    if not os.path.exists(public_dir):
        print(f"❌ 错误：找不到文件夹 {public_dir}")
        print("请先创建文件夹，并放入 PDF 文件！")
        return

    # 4. 遍历文件夹里的所有 PDF
    files = [f for f in os.listdir(public_dir) if f.lower().endswith('.pdf')]

    if not files:
        print("⚠️ 警告：public 文件夹里是空的，没有找到 PDF 文件。")
        return

    print(f"📂 发现 {len(files)} 个内置文件，准备处理...")

    for filename in files:
        file_path = os.path.join(public_dir, filename)

        # 这一步会自动调用我们写好的“智能侦探”和“结构化切分”
        # 它会自动判断是 IFRS 还是普通文件，并存入 ChromaDB
        try:
            engine.ingest_document(file_path)
            print(f"✅ 成功入库: {filename}")
        except Exception as e:
            print(f"❌ 处理失败 {filename}: {str(e)}")

    print("\n🎉 所有内置文件初始化完成！数据库已准备就绪。")

if __name__ == "__main__":
    init_public_knowledge_base()
