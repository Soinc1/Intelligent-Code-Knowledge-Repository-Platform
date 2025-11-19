"""数据库连接和模型定义"""
from sqlalchemy import create_engine, Column, Integer, String, Text, TIMESTAMP, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import DATABASE_URL

Base = declarative_base()

# 创建数据库引擎
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class CodeFile(Base):
    """代码文件表"""
    __tablename__ = "code_files"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text)
    file_content = Column(Text, nullable=False)
    language = Column(String(50))
    file_hash = Column(String(64), unique=True)
    ast_json = Column(JSON)
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)
    
    # 关系
    review_comments = relationship("ReviewComment", back_populates="code_file", cascade="all, delete-orphan")
    code_reviews = relationship("CodeReview", back_populates="code_file", cascade="all, delete-orphan")


class ReviewComment(Base):
    """审查评论表"""
    __tablename__ = "review_comments"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    code_file_id = Column(Integer, ForeignKey("code_files.id", ondelete="CASCADE"))
    code_snippet = Column(Text)
    comment_text = Column(Text, nullable=False)
    comment_type = Column(String(50))  # security/performance/style/best_practice
    severity = Column(String(20))  # high/medium/low
    reviewer_id = Column(Integer)
    review_date = Column(TIMESTAMP, default=datetime.now)
    milvus_id = Column(String(64))
    meta_data = Column(JSON)  # 改为meta_data，因为metadata是SQLAlchemy保留字
    
    # 关系
    code_file = relationship("CodeFile", back_populates="review_comments")


class KnowledgeBase(Base):
    """知识库表"""
    __tablename__ = "knowledge_base"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50))
    code_pattern = Column(Text)
    best_practice = Column(Text)
    milvus_id = Column(String(64))
    created_by = Column(Integer)
    status = Column(String(20), default="pending_review")  # draft/pending_review/published
    tags = Column(JSON, default=list)
    source_comment_id = Column(Integer, ForeignKey("review_comments.id"))
    last_reviewed_by = Column(Integer)
    review_notes = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)
    
    source_comment = relationship("ReviewComment", backref="knowledge_entries", foreign_keys=[source_comment_id])


class CodeReview(Base):
    """代码审查记录表"""
    __tablename__ = "code_reviews"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    code_file_id = Column(Integer, ForeignKey("code_files.id", ondelete="CASCADE"))
    review_result = Column(JSON)
    matched_knowledge_ids = Column(JSON)  # 数组
    review_time_ms = Column(Integer)
    created_at = Column(TIMESTAMP, default=datetime.now)
    
    # 关系
    code_file = relationship("CodeFile", back_populates="code_reviews")


class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)  # 存储密码哈希
    email = Column(String(100))
    role = Column(String(20), default="user")  # admin/user
    is_active = Column(Integer, default=1)  # 1=激活, 0=禁用
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)
    
    # 关系
    operation_logs = relationship("OperationLog", back_populates="user", cascade="all, delete-orphan")


class OperationLog(Base):
    """操作历史记录表"""
    __tablename__ = "operation_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    operation_type = Column(String(50), nullable=False)  # code_review/knowledge_add/knowledge_extract/history_query
    operation_detail = Column(JSON)  # 操作详情
    ip_address = Column(String(50))
    user_agent = Column(String(255))
    created_at = Column(TIMESTAMP, default=datetime.now)
    
    # 关系
    user = relationship("User", back_populates="operation_logs")


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库表"""
    Base.metadata.create_all(bind=engine)

