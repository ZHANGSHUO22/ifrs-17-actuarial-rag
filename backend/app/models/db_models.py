from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)

# ==========================================
# 🌟 新增：聊天记录表 (Chat History Table)
# ==========================================
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)       # 谁聊的 (存 username)
    session_id = Column(String, index=True)    # 属于哪一次对话 (UUID)
    role = Column(String)                      # "user" 或 "assistant"
    content = Column(Text)                     # 聊天内容 (含回答与引用的 sources)
    timestamp = Column(DateTime, default=datetime.utcnow) # 发生时间
