import os
import sys
import time
from pathlib import Path

# 确保能导入后端的模块
CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[1]
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.rag.vector_engine import VectorEngine

def run_midnight_cleanup(days_to_keep=7):
    print(f"🧹 [TTL 清洁工] 启动！准备清理超过 {days_to_keep} 天的临时私有切片...")
    engine = VectorEngine()

    # 计算过期时间线
    current_time = int(time.time())
    cutoff_time = current_time - (days_to_keep * 24 * 60 * 60)

    try:
        # ChromaDB 支持过滤整数大小 ($lt 表示 less than / 小于)
        # 注意：这里我们过滤出带有 upload_timestamp 且时间小于 cutoff_time 的数据
        expired_filter = {
            "upload_timestamp": {"$lt": cutoff_time}
        }

        # 先查出来看看有多少个符合条件
        expired_docs = engine.collection.get(
            where=expired_filter,
            include=['metadatas']
        )

        expired_ids = expired_docs.get('ids', [])

        if not expired_ids:
            print("✨ 检查完毕：你的数据库非常干净，没有过期的临时切片！")
            return

        # 过滤掉公共库的数据（为了绝对安全，我们只删个人的，绝不删 public 的）
        # 因为我们不想误删官方的 IFRS 法规
        ids_to_delete = []
        for i, meta in enumerate(expired_docs.get('metadatas', [])):
            if meta.get("user_id") != "public":
                ids_to_delete.append(expired_ids[i])

        if not ids_to_delete:
            print("✨ 检查完毕：找到的都是公共永久文件，跳过清理。")
            return

        print(f"🚨 锁定目标：发现 {len(ids_to_delete)} 个过期的私人切片，准备执行物理删除...")

        # 执行终极抹除
        engine.collection.delete(ids=ids_to_delete)

        print(f"✅ 清理完成！成功释放了服务器硬盘空间。")

    except Exception as e:
        print(f"❌ 清理脚本执行失败: {e}")

if __name__ == "__main__":
    #  7 天改
    run_midnight_cleanup(days_to_keep=7)
