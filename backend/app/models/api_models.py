# models/api_models.py
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

class QueryRequest(BaseModel):
    query: str = Field(..., description="用户的提问")

    # 这里放宽限制，允许任何语言代码传入 (en, cs, sk, tr, zh 等)
    # 这样你就不用每次加一种语言都来改代码了
    language: Optional[str] = Field("en", description="语言代码 (e.g., 'en', 'cs', 'sk')")

class SourceMetadata(BaseModel):
    """
    Metadata for retrieved regulatory sources.
    """
    document_id: str
    page_number: int
    text_snippet: str

class QueryResponse(BaseModel):
    answer: str = Field(..., description="AI 生成的回答")

    # ✅ 核心修复：明确指定列表里的元素必须是 SourceMetadata 类型
    sources: List[SourceMetadata] = Field(default_factory=list, description="引用的法规来源列表")

    # 这里我们用 process_time (float) 来匹配 service.py 中的逻辑
    # 如果你之前的代码用的是 processing_time_ms，请确保 service.py 里也改了
    process_time: float = Field(..., description="处理耗时 (秒)")
