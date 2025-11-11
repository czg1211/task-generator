from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, UniqueConstraint, Enum
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base
import enum

class TaskType(enum.Enum):
    SCHEDULED = "scheduled"  # 定时任务
    ONE_TIME = "one_time"    # 一次性任务

class PolicyConfig(Base):
    __tablename__ = "policy_configs"

    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(String(100), unique=True, index=True, nullable=False)
    data_source_type = Column(String(50), nullable=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PolicyTaskGenConfig(Base):
    __tablename__ = "policy_task_gen_configs"

    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(String(100), nullable=False, index=True)
    task_gen_sql = Column(Text, nullable=False)
    cron_expression = Column(String(100), nullable=False)
    task_type = Column(Enum(TaskType), nullable=False)  # 'scheduled' or 'one_time'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TaskSource(Base):
    __tablename__ = "task_source"

    id = Column(Integer, primary_key=True, index=True)
    source_name = Column(String(200), nullable=False)
    url = Column(Text, nullable=False)
    parse_template = Column(JSONB)  # 存储JSON格式的解析模板
    status = Column(Boolean, default=True)  # True:启用, False:禁用
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('source_name', 'url', name='uq_task_source_name_url'),
    )


class SeedTask(Base):
    __tablename__ = "seed_tasks"

    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(String(100), nullable=False, index=True)
    task_type = Column(Enum(TaskType), nullable=False)  # 'scheduled' or 'one_time'
    task_params = Column(JSONB, nullable=False)  # 任务参数
    is_consumed = Column(Boolean, default=False)  # 是否已被消费（针对一次性任务）
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())