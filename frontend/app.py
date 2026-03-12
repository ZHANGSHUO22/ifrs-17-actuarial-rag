import streamlit as st
from streamlit_pdf_viewer import pdf_viewer
import requests
import os

# --- 配置 ---
st.set_page_config(page_title="IFRS 17 Copilot", layout="wide")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# --- 语言包 ---
TRANSLATIONS = {
    "en": {
        "sidebar_title": "📂 Knowledge Base",
        "source_select": "Select Source:",
        "option_upload": "📤 Upload New File",
        "option_library": "📚 Public Library (Built-in)",
        "library_label": "Choose a document:",
        "upload_label": "Upload PDF",
        "chat_placeholder": "Ask about IFRS 17...",
        "ingest_btn": "Process Upload",
        "analyzing": "🔍 Searching...",
        "snippet_label": "💡 Relevant Context:",
        "page_ref": "Page"
    },
    "cs": {
        "sidebar_title": "📂 Znalostní báze",
        "source_select": "Vybrat zdroj:",
        "option_upload": "📤 Nahrát nový soubor",
        "option_library": "📚 Veřejná knihovna (Vestavěná)",
        "library_label": "Vyberte dokument:",
        "upload_label": "Nahrát PDF",
        "chat_placeholder": "Zeptejte se na IFRS 17...",
        "ingest_btn": "Zpracovat",
        "analyzing": "🔍 Hledám...",
        "snippet_label": "💡 Relevantní kontext:",
        "page_ref": "Strana"
    }
}


# frontend/app.py

def login_ui():
    st.title("🔐 IFRS 17 Copilot 登录")
    with st.form("login_form"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submit = st.form_submit_button("进入系统")

        if submit:
            res = requests.post(
                f"{BACKEND_URL}/api/v1/auth/login",
                data={"username": username, "password": password}
            )
            if res.status_code == 200:
                token = res.json()["access_token"]
                st.session_state.authenticated = True
                st.session_state.token = token
                st.session_state.username = username
                st.success("Welcome back!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

# --- 逻辑控制 ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    login_ui()
    st.stop() # 🛑 核心：不登录就不执行后面的 RAG 逻辑

@st.cache_data(ttl=3600)  # 缓存 1 小时
def fetch_pdf_binary(base_url, filename):
    """从后端获取 PDF 二进制流，并缓存以提高速度"""
    url = f"{base_url}/api/v1/files/{filename}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.content
        return None
    except Exception:
        return None

if "language" not in st.session_state: st.session_state.language = "en"
def get_text(key): return TRANSLATIONS[st.session_state.language].get(key, key)

# --- 侧边栏 (Sidebar) ---
with st.sidebar:
    # 1. 语言切换 (保持不变)
    st.radio(
        "Language",
        ["English", "Čeština"],
        key="lang_radio",
        index=0 if st.session_state.language == "en" else 1,
        on_change=lambda: st.session_state.update(language="en" if st.session_state.lang_radio=="English" else "cs")
    )

    st.divider()

    # 2. 内置公共库 (Public Library)
    st.header(get_text("sidebar_title")) # "Document Ingestion" -> 改意为 "Knowledge Base" 更好
    st.subheader("📚 " + get_text("option_library"))

    # === 关键修改点：定义内置文件列表 ===
    # 这些文件名必须与你 knowledge_base/public 文件夹里的文件名一模一样！
    LIBRARY_FILES = [
        "ifrs17_regulation_eu_2021.pdf",
        # "solvency_ii_directive.pdf",  # 以后有了新文件加在这里
        # "czech_insurance_act.pdf"
    ]

    # 使用 multiselect 实现“即点即用，取消即停”
    # 这里的 default=[] 表示默认不选，你可以改成 default=LIBRARY_FILES 默认全选
    selected_library_docs = st.multiselect(
        label=get_text("library_label"),
        options=LIBRARY_FILES,
        default=[],
        placeholder="Select regulations..."
    )

    st.divider()

    # 3. 私有文件上传 (Private Upload)
    st.subheader("📤 " + get_text("option_upload"))

    # 使用 session_state 来记住用户上传成功的文件名
    if "my_uploaded_files" not in st.session_state:
        st.session_state.my_uploaded_files = []

    uploaded_file = st.file_uploader(get_text("upload_label"), type=["pdf"])

    if uploaded_file:
        # 如果点击上传按钮
        # 如果点击上传按钮
        if st.button(get_text("ingest_btn"), use_container_width=True):
            with st.spinner("Processing..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}

                    # 🌟 同样构造 headers
                    headers = {
                        "Authorization": f"Bearer {st.session_state.token}"
                    }

                    # 调用后端入库接口，带上 headers
                    res = requests.post(
                        f"{BACKEND_URL}/api/v1/ingest",
                        files=files,
                        headers=headers  # 👈 加上这一行
                    )

                    if res.status_code == 200:
                        st.success(f"✅ {get_text('ingest_success')}")
                        # 将上传成功的文件名加入到 session 记录中，防止页面刷新后丢失
                        if uploaded_file.name not in st.session_state.my_uploaded_files:
                            st.session_state.my_uploaded_files.append(uploaded_file.name)
                    else:
                        st.error(f"{get_text('ingest_error')} {res.json().get('detail')}")
                except Exception as e:
                    st.error(f"{get_text('connect_error')} {str(e)}")

    # 显示已上传的文件，并允许用户勾选是否将其包含在搜索中
    selected_private_docs = []
    if st.session_state.my_uploaded_files:
        st.caption("Your Uploaded Files:")
        for f_name in st.session_state.my_uploaded_files:
            # 默认勾选刚上传的文件
            if st.checkbox(f"📄 {f_name}", value=True, key=f"chk_{f_name}"):
                selected_private_docs.append(f_name)

    # === 4. 汇总所有被选中的文件 ===
    # 这个变量 active_docs 就是我们要传给聊天框去搜索的最终列表
    active_docs = selected_library_docs + selected_private_docs

    # 将其存入 session_state 供主页面使用
    st.session_state.active_docs = active_docs

    # 调试显示 (可选，开发完后可以注释掉)
    if active_docs:
        st.success(f"🔍 Searching in {len(active_docs)} document(s)")
    else:
        st.warning("⚠️ No documents selected.")


# --- 主界面 (Main Interface) ---
st.title("📊 IFRS 17 Copilot")

# 初始化 Session State
if "messages" not in st.session_state: st.session_state.messages = []
if "current_analysis" not in st.session_state: st.session_state.current_analysis = None

# 分栏布局：左侧聊天，右侧文档预览
col1, col2 = st.columns([1, 1.2])

# === 左栏：聊天窗口 ===
with col1:
    # 1. 显示聊天历史
    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    # 2. 处理用户输入
    if prompt := st.chat_input(get_text("chat_placeholder")):
        # 先把用户的问题显示出来
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        # 3. 准备调用后端
        with st.chat_message("assistant"):
            # 获取侧边栏选中的所有文件 (我们在侧边栏里存进去的)
            active_docs = st.session_state.get("active_docs", [])

            # --- 🛑 关键拦截：如果用户没选任何文件，直接报错，不发请求 ---
            if not active_docs:
                st.warning("⚠️ Please select at least one document from the sidebar to start searching.")
                st.stop() # 停止运行，节省资源

            with st.spinner(get_text("analyzing")):
                try:
                    payload = {
                        "query": prompt,
                        "language": st.session_state.language,
                        "selected_files": active_docs
                    }

                    # 🌟 核心修复：构造请求头，带上你的 Token！
                    headers = {
                        "Authorization": f"Bearer {st.session_state.token}"
                    }

                    # 🌟 发送请求时，把 headers 传进去
                    res = requests.post(
                        f"{BACKEND_URL}/api/v1/query",
                        json=payload,
                        headers=headers  # 👈 就是加了这一行
                    )

                    if res.status_code == 200:
                        data = res.json()
                        answer = data.get("answer", "No answer provided.")

                        # 显示 AI 回答
                        st.markdown(answer)

                        # 保存上下文
                        st.session_state.messages.append({"role": "assistant", "content": answer})
                        st.session_state.current_analysis = data

                        # 显示引用来源的简要提示
                        if data.get("sources"):
                            num_sources = len(data["sources"])
                            st.caption(f"📚 Referenced {num_sources} source(s) from selected documents.")

                    else:
                        st.error(f"Backend Error ({res.status_code}): {res.text}")

                except Exception as e:
                    st.error(f"Connection Error: {str(e)}")

# === 右栏：文档预览 (保持 PDF Viewer 逻辑) ===
with col2:
    if st.session_state.current_analysis:
        analysis = st.session_state.current_analysis
        sources = analysis.get("sources", [])

        if sources:
            st.subheader("📄 Document Context")

            tab_labels = [f"[{i+1}] Page {s.get('page_number', '?')}" for i, s in enumerate(sources)]
            tabs = st.tabs(tab_labels)

            for i, tab in enumerate(tabs):
                src = sources[i]
                with tab:
                    doc_id = src.get("document_id", "Unknown")
                    try:
                        page_num = int(src.get("page_number", 1))
                    except:
                        page_num = 1
                    snippet = src.get("text_snippet", "...")
                    para_id = src.get("paragraph_id", "N/A")

                    st.info(f"📍 **Location:** {doc_id} | **Page {page_num}**")

                    # 显示黄色高亮提示框
                    st.warning(
                        f"**Source:** {doc_id}\n\n"
                        f"**Location:** Page {page_num} (Para {para_id})\n\n"
                        f"💡 **Snippet:** ...{snippet}..."
                    )

                    # 尝试加载 PDF
                    # 注意：这里需要后端提供文件下载接口，或者直接读取本地文件
                    # 如果你还没有做文件服务，这里暂时只显示文本即可
                    pdf_url = f"{BACKEND_URL}/api/v1/files/{doc_id}" # 假设你之后会做这个接口

                    pdf_binary = fetch_pdf_binary(BACKEND_URL, doc_id)

                    if pdf_binary:
                        # 2. 渲染 PDF
                        # 注意 key 的构造：一定要包含 page_num
                        # 这样当页码变化时，Streamlit 会强制销毁旧组件，创建新组件并滚动到新位置
                        pdf_viewer(
                            input=pdf_binary,
                            width=700,
                            height=800,
                            scroll_to_page=page_num,  # 👈 自动跳转的核心参数
                            render_text=True,         # 允许选中文本复制
                            key=f"pdf_v_{i}_{doc_id}_{page_num}" # 🔥 唯一且动态的 Key
                        )
                    else:
                        st.error(f"❌ Failed to load PDF: {doc_id}")
                    # --- 🚀 核心优化结束 ---

        else:
            st.info("No sources cited.")
    else:
        # 空状态：显示一个占位图或文字
        st.markdown(
            f"""
            <div style='text-align: center; color: #888; padding: 100px; border: 2px dashed #ddd; border-radius: 10px;'>
                <h3>👈 Ask a question to see documents</h3>
                <p>Select documents from the sidebar first.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

