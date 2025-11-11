from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class TaskType(str, Enum):
    SCHEDULED = "scheduled"
    ONE_TIME = "one_time"

# PolicyConfig Schemas
class PolicyConfigBase(BaseModel):
    policy_id: str
    data_source_type: str
    is_enabled: bool = True
    description: Optional[str] = None


class PolicyConfigCreate(PolicyConfigBase):
    pass


class PolicyConfig(PolicyConfigBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# PolicyTaskGenConfig Schemas
class PolicyTaskGenConfigBase(BaseModel):
    policy_id: str
    task_gen_sql: str
    cron_expression: str
    task_type: str  # 'scheduled' or 'one_time'


class PolicyTaskGenConfigCreate(PolicyTaskGenConfigBase):
    pass


class PolicyTaskGenConfig(PolicyTaskGenConfigBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# TaskSource Schemas
class TaskSourceBase(BaseModel):
    source_name: str
    url: str
    parse_template: Optional[Dict[str, Any]] = None
    status: bool = True


class TaskSourceCreate(TaskSourceBase):
    pass


class TaskSource(TaskSourceBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# SeedTask Schemas
class SeedTaskBase(BaseModel):
    policy_id: str
    task_type: str
    task_params: Dict[str, Any]


class SeedTaskCreate(SeedTaskBase):
    pass


class SeedTask(SeedTaskBase):
    id: int
    is_consumed: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# API Response Schemas
class ServiceStatus(BaseModel):
    status: str
    scheduler_running: bool
    active_jobs: int


class TaskGenerationResult(BaseModel):
    success: bool
    generated_tasks: int
    message: str