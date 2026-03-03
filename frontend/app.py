import streamlit as st
from streamlit_pdf_viewer import pdf_viewer # 确保安装了 pip install streamlit-pdf-viewer
import base64
import requests
import os

# --- 1. 语言包配置 (Language Dictionary) ---
# 这里定义了所有界面文字的中/英/捷克语映射
TRANSLATIONS = {
    "en": {
        "page_title": "IFRS 17 Actuarial Copilot",
        "sidebar_title": "📂 Document Ingestion",
        "upload_label": "Upload IFRS 17 PDFs",
        "ingest_btn": "Ingest Document",
        "ingest_success": "✅ Indexed:",
        "ingest_error": "Error:",
        "connect_error": "Connection failed:",
        "select_file_warn": "Please select a file first.",
        "expertise_title": "**Expertise Areas:**",
        "chat_title": "💬 Actuarial Chat",
        "chat_placeholder": "Ask a question about IFRS 17... (You can ask in English, Czech or Chinese)",
        "analyzing": "🔍 Analyzing regulations & Retrieving context...",
        "backend_error": "Backend Error:",
        "source_trace": "### 🔍 Source Trace",
        "select_source_instruction": "Click below to jump to the PDF page:",
        "snippet_label": "**💡 Text Snippet from page:**",
        "viewer_title": "📄 Regulatory Document Viewer",
        "viewer_placeholder": "👈 Ask a question on the left to see the document here.",
        "waiting_msg": "Waiting for Analysis...",
        "waiting_sub": "Upload a document and ask a question to begin."
    },
    "cs": {  # Czech Translations
        "page_title": "IFRS 17 Pojistně-matematický Copilot",
        "sidebar_title": "📂 Nahrávání dokumentů",
        "upload_label": "Nahrát IFRS 17 PDF soubory",
        "ingest_btn": "Zpracovat dokument",
        "ingest_success": "✅ Indexováno:",
        "ingest_error": "Chyba:",
        "connect_error": "Připojení selhalo:",
        "select_file_warn": "Nejprve vyberte soubor.",
        "expertise_title": "**Oblasti expertní znalosti:**",
        "chat_title": "💬 Chat s pojistným matematikem",
        "chat_placeholder": "Položte otázku k IFRS 17... (Můžete se ptát anglicky, česky nebo čínsky)",
        "analyzing": "🔍 Analyzuji předpisy a hledám kontext...",
        "backend_error": "Chyba backendu:",
        "source_trace": "### 🔍 Zdrojové citace",
        "select_source_instruction": "Klikněte níže pro přechod na stránku PDF:",
        "snippet_label": "**💡 Úryvek textu ze stránky:**",
        "viewer_title": "📄 Prohlížeč regulačních dokumentů",
        "viewer_placeholder": "👈 Položte otázku vlevo pro zobrazení dokumentu.",
        "waiting_msg": "Čekám na analýzu...",
        "waiting_sub": "Nahrajte dokument a položte otázku."
    }
}

# --- 2. 页面初始化 ---
st.set_page_config(
    page_title="IFRS 17 Copilot",
    page_icon="📊",
    layout="wide"
)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# --- 3. 状态管理与辅助函数 ---
if "language" not in st.session_state:
    st.session_state.language = "en"  # 默认英语

def get_text(key):
    """根据当前语言获取对应的文本"""
    lang = st.session_state.language
    return TRANSLATIONS[lang].get(key, f"MISSING_{key}")

# 自定义 CSS
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stChatMessage { border-radius: 15px; padding: 10px; margin-bottom: 10px; }
    /* 针对 pdf_viewer 的容器样式微调 */
    div[data-testid="stIFrame"] { border: 1px solid #e0e0e0; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. 侧边栏 (Sidebar) ---
with st.sidebar:
    # --- 语言切换器 (Language Switcher) ---
    lang_choice = st.radio(
        "Language / Jazyk",
        ["English", "Čeština"],
        index=0 if st.session_state.language == "en" else 1,
        horizontal=True
    )
    # 更新状态
    if lang_choice == "English":
        st.session_state.language = "en"
    else:
        st.session_state.language = "cs"

    st.divider()

    # ---原本的上传逻辑 ---
    st.header(get_text("sidebar_title"))
    uploaded_file = st.file_uploader(get_text("upload_label"), type=["pdf", "txt"])

    if st.button(get_text("ingest_btn"), use_container_width=True):
        if uploaded_file is not None:
            with st.spinner("Uploading..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                    response = requests.post(f"{BACKEND_URL}/api/v1/ingest", files=files)
                    if response.status_code == 200:
                        st.success(f"{get_text('ingest_success')} {uploaded_file.name}")
                    else:
                        st.error(f"{get_text('ingest_error')} {response.json().get('detail')}")
                except Exception as e:
                    st.error(f"{get_text('connect_error')} {str(e)}")
        else:
            st.warning(get_text("select_file_warn"))

    st.divider()
    st.markdown(get_text("expertise_title"))
    st.markdown("""
    - General Model (BBA/GMM)
    - Premium Allocation (PAA)
    - Variable Fee (VFA)
    - CSM & Risk Adjustment
    """)

# --- 5. 主页面布局 ---
st.title(get_text("page_title"))

# 初始化消息历史
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_analysis" not in st.session_state:
    st.session_state.current_analysis = None

# 分栏
col_left, col_right = st.columns([1, 1.2])

# === 左栏：聊天 ===
with col_left:
    st.subheader(get_text("chat_title"))

    # 显示历史
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 输入框
    if prompt := st.chat_input(get_text("chat_placeholder")):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner(get_text("analyzing")):
                try:
                    # 注意：这里我们不需要改后端的 language 参数，
                    # 因为我们希望 AI 根据用户输入的问题语言自动决定回答语言。
                    # 获取当前选中的语言代码 ('en' 或 'cs')
                    current_lang = st.session_state.language

                    # 传给后端
                    payload = {"query": prompt, "language": current_lang}
                    response = requests.post(f"{BACKEND_URL}/api/v1/query", json=payload)

                    if response.status_code == 200:
                        data = response.json()
                        answer = data["answer"]
                        st.markdown(answer)

                        st.session_state.current_analysis = data
                        st.session_state.messages.append({"role": "assistant", "content": answer})
                    else:
                        st.error(f"{get_text('backend_error')} {response.status_code}")
                except Exception as e:
                    st.error(f"{get_text('connect_error')} {str(e)}")

    # 来源选择器
    if st.session_state.current_analysis and st.session_state.current_analysis.get("sources"):
        data = st.session_state.current_analysis
        st.divider()
        st.markdown(get_text("source_trace"))

        # 构造选项
        source_options = [
            f"Src {i+1}: {s['document_id']} (Pg {s.get('page_number', '?')})"
            for i, s in enumerate(data["sources"])
        ]

        selected_idx = st.radio(
            get_text("select_source_instruction"),
            range(len(source_options)),
            format_func=lambda x: source_options[x],
            key="source_selector"
        )

        current_source = data["sources"][selected_idx]
        st.info(f"{get_text('snippet_label')}\n\n...{current_source['text_snippet']}...")

# === 右栏：PDF 预览 (使用 streamlit-pdf-viewer + 二进制流) ===
with col_right:
    if st.session_state.current_analysis and st.session_state.current_analysis.get("sources"):
        st.subheader(get_text("viewer_title"))

        # 获取当前选择的索引
        idx = st.session_state.get("source_selector", 0)
        if idx >= len(st.session_state.current_analysis["sources"]): idx = 0

        target_source = st.session_state.current_analysis["sources"][idx]
        doc_id = target_source['document_id']
        page_num = int(target_source.get('page_number', 1))

        st.caption(f"Document: {doc_id} | Page: **{page_num}**")


		# --- 核心修改 1：黄色高亮提示框 ---
        # 1. 获取 AI 检索到的那段原文
        snippet = target_source.get('text_snippet', 'No snippet available.')

        # 2. 使用 st.warning 生成黄色框
        # 这里的 f-string 负责把文档名、页码和原文片段拼接到框里
        st.warning(
            f"📄 **{doc_id}** | Page: **{page_num}**\n\n"
            f"💡 **Look for this text (请在下方寻找此段文字):**\n\n"
            f"> *{snippet}*"
        )
        # 构造 URL
        pdf_url = f"{BACKEND_URL}/files/{doc_id}"

        try:
            # 获取二进制数据，绕过浏览器跨域屏蔽
            response_pdf = requests.get(pdf_url)

            if response_pdf.status_code == 200:
                binary_pdf = response_pdf.content

                # 渲染 PDF，并自动跳到指定页
                pdf_viewer(
                    input=binary_pdf,
                    width=700,
                    height=800,
                    scroll_to_page=page_num
                )
            else:
                st.error("Error loading PDF from backend.")

        except Exception as e:
            st.error(f"Viewer Error: {str(e)}")

    else:
        # 空状态显示
        st.subheader(get_text("viewer_title"))
        st.markdown(
            f"""
            <div style='text-align: center; color: gray; padding: 100px; border: 2px dashed #e0e0e0; border-radius: 10px;'>
                <h3>{get_text('waiting_msg')}</h3>
                <p>{get_text('waiting_sub')}</p>
            </div>
            """,
            unsafe_allow_html=True
        )
