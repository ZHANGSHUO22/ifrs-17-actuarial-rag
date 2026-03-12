import os
import sys
import uvicorn
from pathlib import Path
from dotenv import load_dotenv

# --- FastAPI 核心组件 ---
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm # 用于处理登录表单

# --- 1. 路径与环境配置 ---
CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[1]
sys.path.append(str(PROJECT_ROOT))
load_dotenv(dotenv_path=PROJECT_ROOT / '.env')

# --- 2. 导入内部模块 ---
try:
    from app.models.api_models import QueryRequest, QueryResponse
    from app.services.rag.service import RAGService
    from app.core.database import engine, get_db
    from app.models.db_models import Base, User
    from app.core.security import get_password_hash, get_current_user, create_access_token, verify_password
except ImportError as e:
    print(f"❌ Import failed! 确保你已经创建了 database.py, security.py 和 db_models.py. Error: {e}")
    raise e

# ==========================================
# 🚀 3. 初始化 FastAPI
# ==========================================
app = FastAPI(
    title="IFRS 17 Actuarial RAG API",
    description="Professional-grade accounting regulation query engine with Auth.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 💾 4. 初始化数据库表
# ==========================================
# 这一句会在项目根目录自动创建 sql_app.db 文件和 users 表
Base.metadata.create_all(bind=engine)

# ==========================================
# 📂 5. 目录准备
# ==========================================
PUBLIC_KB_DIR = PROJECT_ROOT / "knowledge_base" / "public"
TEMP_UPLOAD_DIR = PROJECT_ROOT / "backend" / "data" / "temp"
os.makedirs(PUBLIC_KB_DIR, exist_ok=True)
os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)

# ==========================================
# ⚙️ 6. 系统启动事件 (只保留这一个)
# ==========================================
rag_service: RAGService = None

@app.on_event("startup")
async def startup_event():
    global rag_service
    print("🚀 Initializing IFRS 17 Actuarial Engine...")
    try:
        rag_service = RAGService()
        print("✅ Engine Ready.")
    except Exception as e:
        print(f"❌ Failed to initialize RAG Service: {e}")

    # --- 自动创建测试账号 ---
    try:
        db = next(get_db())
        test_user = db.query(User).filter(User.username == "admin").first()
        if not test_user:
            print("👤 创建默认测试账号: admin / admin123")
            hashed_pw = get_password_hash("admin123")
            new_user = User(username="admin", hashed_password=hashed_pw)
            db.add(new_user)
            db.commit()
        db.close()
    except Exception as e:
        print(f"❌ 创建测试账号失败: {e}")

# ==========================================
# 🔐 7. 登录接口 (前端调用的接口)
# ==========================================
@app.post("/api/v1/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="用户名或密码错误")

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "engine_status": "ready" if rag_service else "initializing"}

# ==========================================
# 🛡️ 8. 核心业务接口 (已加锁)
# ==========================================
@app.post("/api/v1/query", response_model=QueryResponse)
async def query_ifrs17(
    request: QueryRequest,
    current_user: User = Depends(get_current_user) # 👈 加锁：必须带 Token
):
    print(f"\n👤 当前提问用户: {current_user.username}")
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG Service is not initialized.")
    return await rag_service.answer_query(request)

@app.post("/api/v1/ingest")
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user) # 👈 加锁：必须带 Token
):
    print(f"\n👤 收到用户 {current_user.username} 上传的文件: {file.filename}")
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG Service is not initialized.")

    file_path = TEMP_UPLOAD_DIR / file.filename
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        background_tasks.add_task(rag_service.vector_engine.ingest_document, str(file_path))
        return {"status": "Ingestion started in background", "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

# ==========================================
# 📄 9. 文件下载接口 (公开)
# ==========================================
@app.get("/api/v1/files/{filename}")
async def get_pdf_file(filename: str):
    public_path = PUBLIC_KB_DIR / filename
    if public_path.exists() and public_path.is_file():
        return FileResponse(path=public_path, media_type="application/pdf", filename=filename)

    temp_path = TEMP_UPLOAD_DIR / filename
    if temp_path.exists() and temp_path.is_file():
        return FileResponse(path=temp_path, media_type="application/pdf", filename=filename)

    raise HTTPException(status_code=404, detail=f"File not found: {filename}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
