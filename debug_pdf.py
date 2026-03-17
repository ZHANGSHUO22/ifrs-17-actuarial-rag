# scripts/debug_pdf.py
import fitz  # PyMuPDF
import os

# 请确保路径正确，指向你的 public 文件夹
# 如果你在根目录运行，路径应该是 knowledge_base/public/...
file_path = "knowledge_base/public/ifrs17_eu_07.2025.pdf"

if not os.path.exists(file_path):
    print(f"❌ 找不到文件: {file_path}")
    exit()

print(f"📖 使用 PyMuPDF (Fitz) 引擎读取: {os.path.basename(file_path)}")

try:
    doc = fitz.open(file_path)
    print(f"📄 总页数: {len(doc)}")

    # 我们依然检查第 5, 10, 20 页
    for i in [5, 10, 20]:
        if i < len(doc):
            print(f"\n--- 第 {i} 页内容预览 (PyMuPDF) ---")

            # 🌟 关键点：fitz 的 get_text() 通常能自动修复单词内的奇怪空格
            text = doc[i].get_text()

            # 打印前 800 个字符
            print(text[:800])
            print("-----------------------")

    doc.close()

except Exception as e:
    print(f"❌ 读取失败: {e}")
