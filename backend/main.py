# backend/main.py
import os
import sys
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Add project root to path to ensure imports work correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our components
from app.models.api_models import QueryRequest, QueryResponse
from backend.app.services.rag.service import RAGService

# Load environment variables
from pathlib import Path
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# 修改这一段
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# --- 新加的调试代码 ---
print(f"🔍 正在寻找 .env 文件，路径是: {env_path.absolute()}")
print(f"📂 该文件是否存在: {env_path.exists()}")
print(f"🔑 获取到的 API Key 前几个字: {str(os.getenv('GOOGLE_API_KEY'))[:5]}...")
# ---------------------


app = FastAPI(
    title="IFRS 17 Actuarial RAG API",
    description="Professional-grade accounting regulation query engine.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（生产环境可改为前端的具体域名）
    allow_credentials=True,
    allow_methods=["*"],  # 允许 GET, POST 等所有方法
    allow_headers=["*"],
)

# 确保目录存在
os.makedirs("backend/data/temp", exist_ok=True)

# 将 temp 文件夹挂载到 /files 路径下
app.mount("/files", StaticFiles(directory="backend/data/temp"), name="files")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Service Instance
rag_service: RAGService = None

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.on_event("startup")
async def startup_event():
    """Initialize heavy models and connections on startup."""
    global rag_service
    print("Initializing IFRS 17 Actuarial Engine...")
    try:
        rag_service = RAGService()
        print("Engine Ready.")
    except Exception as e:
        print(f"Failed to initialize RAG Service: {e}")

@app.post("/api/v1/query", response_model=QueryResponse)
async def query_ifrs17(request: QueryRequest):
    """
    Primary endpoint for actuarial queries.
    """
    if not rag_service:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="RAG Service is not initialized.")
    return await rag_service.answer_query(request)

@app.post("/api/v1/ingest")
async def ingest_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Endpoint to upload and ingest a document.
    """
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG Service is not initialized.")

    # Create temp directory if not exists
    temp_dir = "backend/data/temp"
    os.makedirs(temp_dir, exist_ok=True)

    file_path = os.path.join(temp_dir, file.filename)

    # Save uploaded file
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    # Run heavy ingestion in background
    background_tasks.add_task(rag_service.vector_engine.ingest_document, file_path)

    return {"status": "Ingestion started in background", "filename": file.filename}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
