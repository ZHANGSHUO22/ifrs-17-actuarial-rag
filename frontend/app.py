import streamlit as st
from streamlit_pdf_viewer import pdf_viewer
import requests
import os
import uuid
import requests

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
import uuid
import requests
import streamlit as st

def login_ui():
    st.title("🔐 JurisLens by Shuo Log In")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Enter System")

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
    st.stop() # 🛑 核心：不登录就不执行后面的逻辑

# ==========================================
# 🌟 新增：记忆神经元接入区 (Memory Hub)
# ==========================================
# 1. 发放本次对话的唯一身份证
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# 2. 初始化前端聊天容器
if "messages" not in st.session_state:
    st.session_state.messages = []

# 3. 定义与后端数据库通信的两个搬运工函数
def load_chat_history():
    """从后端拉取当前 session_id 的历史聊天记录"""
    if not st.session_state.get("token"):
        return
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    try:
        res = requests.get(
            f"{BACKEND_URL}/api/v1/chat/history/{st.session_state.session_id}",
            headers=headers
        )
        if res.status_code == 200:
            history = res.json()
            if history:
                # 把后端的记录无缝塞进前端的 session_state 里
                st.session_state.messages = [{"role": msg["role"], "content": msg["content"]} for msg in history]
    except Exception as e:
        st.error(f"Failed to load history: {e}")

def save_message_to_db(role: str, content: str):
    """悄悄把单条聊天记录存入数据库"""
    if not st.session_state.get("token"):
        return
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    payload = {
        "session_id": st.session_state.session_id,
        "role": role,
        "content": content
    }
    try:
        requests.post(f"{BACKEND_URL}/api/v1/chat/history", json=payload, headers=headers)
    except Exception as e:
        print(f"Failed to save message: {e}")

# 4. 如果是刚进入页面，拉取一次历史记录 (防止刷新丢失)
if "history_loaded" not in st.session_state:
    load_chat_history()
    st.session_state.history_loaded = True

# ==========================================

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


    st.markdown(
        """
        <div style='background-color: #1e1e1e; padding: 15px; border-radius: 8px; border: 1px solid #4CAF50;'>
        <h4 style='color: #4CAF50; margin-top: 0;'>🚀 Open to Work</h4>
        <p style='color: #4CAF50; font-size: 14px; margin-bottom: 10px;'>
        This AI solution is done by Shuo , who has an M.S. in Actuarial Science</b>. <br>
        Currently looking for my next adventure.
        </p>
        <a href='www.linkedin.com/in/shuo-zhang-295888237' target='_blank' style='color: #4CAF50; text-decoration: none; font-weight: bold;'>💬 Let's chat on LinkedIn</a>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()
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
        "ifrs7_eu_07.2025.pdf",
        "ifrs9_eu_07.2025.pdf",
        "ifrs17_eu_07.2025.pdf"
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

    MAX_FILE_SIZE_MB = 15
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

    uploaded_file = st.file_uploader(get_text("upload_label"), type=["pdf"])

    if uploaded_file:
        # 🌟 第一道防线：前端物理拦截
        if uploaded_file.size > MAX_FILE_SIZE_BYTES:
            st.error(f"❌ File too large! Current size is {uploaded_file.size / (1024*1024):.1f}MB, which exceeds the {MAX_FILE_SIZE_MB}MB limit. Please split the file and try again.")
        else:
            # 只有在文件大小合规的情况下，才渲染上传按钮和执行后续逻辑
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
        # 🌟 核心：复制列表 list(...)，防止在循环中删除元素导致 Streamlit 报错
        for f_name in list(st.session_state.my_uploaded_files):
            # 用两列布局：左边占 85% 放勾选框，右边占 15% 放删除按钮
            col_file, col_del = st.columns([0.85, 0.15])

            with col_file:
                # 默认勾选刚上传的文件
                if st.checkbox(f"📄 {f_name}", value=True, key=f"chk_{f_name}"):
                    selected_private_docs.append(f_name)

            with col_del:
                # 🌟 1. 窄列里只渲染按钮，获取点击状态，绝不在这里打印文本！
                delete_clicked = st.button("❌", key=f"del_{f_name}", help="Delete permanently")

            # ==========================================
            # 🌟 2. 关键修复：注意这里的缩进！退出 with col_del，回到外层！
            # 这样报错信息就会显示在宽敞的侧边栏，而不会变成面条字。
            # ==========================================
            if delete_clicked:
                with st.spinner("Deleting..."):
                    # 呼叫后端的 Delete API
                    headers = {"Authorization": f"Bearer {st.session_state.token}"}
                    try:
                        res = requests.delete(f"{BACKEND_URL}/api/v1/files/{f_name}", headers=headers)
                        if res.status_code == 200:
                            # 从前端状态中彻底移除
                            st.session_state.my_uploaded_files.remove(f_name)
                            # 使用 toast 弹出式通知，比硬塞在布局里更优雅
                            st.toast(f"✅ {f_name} deleted!", icon="🗑️")
                            import time
                            time.sleep(1) # 停顿一秒，让用户看清成功提示
                            st.rerun() # 强制刷新页面
                        else:
                            st.sidebar.error(f"Deletion failed: {res.status_code}. 请检查后端是否加了 delete 路由！")
                    except Exception as e:
                        # 报错现在有了整个侧边栏的宽度，清清楚楚！
                        st.sidebar.error(f"❌ 后端连接失败！请确认后端终端正在运行。报错详情: {str(e)}")

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

	# 在侧边栏的最后加上这段声明
    st.divider()

    st.markdown("### 🏛️ About the Knowledge Base")
    st.info(
        "**Official Data Source:**\n\n"
        "The built-in IFRS regulations are directly sourced from the "
        "[Official Website of the European Union (EUR-Lex)](https://eur-lex.europa.eu/). "
        "It reflects the **EU-endorsed version** of the standard.\n\n"
        "**Disclaimer:**\n"
        "This Copilot is an AI assistant for navigating complex regulations. "
        "It does not constitute binding audit or legal advice."
    )


# --- 主界面 (Main Interface) ---
st.title("📊 JurisLens from Shuo ")

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
        save_message_to_db("user", prompt)

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

                        save_message_to_db("assistant", answer)

                        # 显示引用来源的简要提示
                        if data.get("sources"):
                            num_sources = len(data["sources"])
                            st.caption(f"📚 Referenced {num_sources} source(s) from selected documents.")

                    else:
                        st.error(f"Backend Error ({res.status_code}): {res.text}")

                except Exception as e:
                    st.error(f"Connection Error: {str(e)}")

# === 右栏：文档预览 (极致性能版) ===
with col2:
    if st.session_state.current_analysis:
        analysis = st.session_state.current_analysis
        sources = analysis.get("sources", [])

        if sources:
            st.subheader("📄 Document Context")

            # ==========================================
            # 🌟 核心优化 1：放弃 st.tabs，改用下拉选单！
            # 保证任何时候，浏览器内存里只有 1 个 PDF 渲染器
            # ==========================================

            # 构造下拉菜单的显示文字
            options = [f"[{i+1}] {s.get('document_id', 'Unknown')} (Page {s.get('page_number', '?')})" for i, s in enumerate(sources)]

            # 让用户选择要看哪个片段
            selected_idx = st.selectbox(
                "🔍 选择要查阅的引用来源：",
                range(len(options)),
                format_func=lambda x: options[x]
            )

            # ==========================================
            # 🌟 核心优化 2：只提取用户选中的那【唯一一个】片段进行渲染
            # ==========================================
            src = sources[selected_idx]
            doc_id = src.get("document_id", "Unknown")
            try:
                page_num = int(src.get("page_number", 1))
            except:
                page_num = 1
            snippet = src.get("text_snippet", "...")
            para_id = src.get("para_id", "N/A")

            # 显示黄色高亮提示框
            st.info(f"📍 **Location:** {doc_id} | **Page {page_num}**")
            st.warning(
                f"**Source:** {doc_id}\n\n"
                f"**Location:** Page {page_num} (Para {para_id})\n\n"
                f"💡 **Snippet:** ...{snippet}..."
            )

            # ==========================================
            # 🌟 核心优化 3：极速渲染单个 PDF
            # ==========================================
            pdf_binary = fetch_pdf_binary(BACKEND_URL, doc_id)

            if pdf_binary:
                # 只有这里会消耗渲染性能，由于只有 1 个，将极其丝滑
                pdf_viewer(
                    input=pdf_binary,
                    width=700,
                    height=800,
                    scroll_to_page=page_num,
                    render_text=True,
                    key=f"pdf_{doc_id}_{page_num}" # 动态 Key，页码一切换就会强制刷新组件并跳页
                )
            else:
                st.error(f"❌ Failed to load PDF: {doc_id}")

        else:
            st.info("No sources cited.")
    else:
        # 空状态：显示一个占位提示
        st.markdown(
            f"""
            <div style='text-align: center; color: #888; padding: 100px; border: 2px dashed #ddd; border-radius: 10px;'>
                <h3>👈 Ask a question to see documents</h3>
                <p>Select documents from the sidebar first.</p>
            </div>
            """,
            unsafe_allow_html=True
        )
