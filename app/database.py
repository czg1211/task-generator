from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from app.config import settings
import logging
import threading

logger = logging.getLogger(__name__)

# 添加连接参数
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
    connect_args={
        'connect_timeout': 10,
        'application_name': 'task_generator'
    }
)

# 使用scoped_session确保线程安全
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()

def get_db():
    """获取数据库会话（用于API请求）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        SessionLocal.remove()  # 重要：移除线程局部会话

def create_db_session():
    """创建新的数据库会话（用于后台线程）"""
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()

def create_tables():
    """创建所有表"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("数据库表创建成功")
    except Exception as e:
        logger.error(f"创建数据库表失败: {str(e)}")
        raise