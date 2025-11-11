from sqlalchemy.orm import Session
from typing import List, Optional
from app import models

# PolicyConfig CRUD
def get_policy_configs(db: Session, skip: int = 0, limit: int = 100) -> List[models.PolicyConfig]:
    return db.query(models.PolicyConfig).offset(skip).limit(limit).all()

def get_policy_config(db: Session, policy_id: str) -> Optional[models.PolicyConfig]:
    return db.query(models.PolicyConfig).filter(models.PolicyConfig.policy_id == policy_id).first()

def create_policy_config(db: Session, policy_config: models.PolicyConfig) -> models.PolicyConfig:
    db.add(policy_config)
    db.commit()
    db.refresh(policy_config)
    return policy_config

def update_policy_config_status(db: Session, policy_id: str, is_enabled: bool) -> Optional[models.PolicyConfig]:
    policy_config = get_policy_config(db, policy_id)
    if policy_config:
        policy_config.is_enabled = is_enabled
        db.commit()
        db.refresh(policy_config)
    return policy_config

# PolicyTaskGenConfig CRUD
def get_policy_task_gen_configs(db: Session, skip: int = 0, limit: int = 100) -> List[models.PolicyTaskGenConfig]:
    return db.query(models.PolicyTaskGenConfig).offset(skip).limit(limit).all()

def get_policy_task_gen_config(db: Session, policy_id: str) -> Optional[models.PolicyTaskGenConfig]:
    return db.query(models.PolicyTaskGenConfig).filter(models.PolicyTaskGenConfig.policy_id == policy_id).first()

def get_enabled_policy_configs(db: Session) -> List[models.PolicyTaskGenConfig]:
    # 获取启用的策略配置
    return db.query(models.PolicyTaskGenConfig).all()

def create_policy_task_gen_config(db: Session, config: models.PolicyTaskGenConfig) -> models.PolicyTaskGenConfig:
    db.add(config)
    db.commit()
    db.refresh(config)
    return config

# TaskSource CRUD
def get_task_sources(db: Session, skip: int = 0, limit: int = 100) -> List[models.TaskSource]:
    return db.query(models.TaskSource).offset(skip).limit(limit).all()

def get_task_source(db: Session, source_id: int) -> Optional[models.TaskSource]:
    return db.query(models.TaskSource).filter(models.TaskSource.id == source_id).first()

def create_task_source(db: Session, task_source: models.TaskSource) -> models.TaskSource:
    db.add(task_source)
    db.commit()
    db.refresh(task_source)
    return task_source

def update_task_source_status(db: Session, source_id: int, status: bool) -> Optional[models.TaskSource]:
    task_source = get_task_source(db, source_id)
    if task_source:
        task_source.status = status
        db.commit()
        db.refresh(task_source)
    return task_source

# SeedTask CRUD
def get_seed_tasks(db: Session, skip: int = 0, limit: int = 100) -> List[models.SeedTask]:
    return db.query(models.SeedTask).offset(skip).limit(limit).all()

def get_pending_seed_tasks(db: Session, policy_id: Optional[str] = None) -> List[models.SeedTask]:
    query = db.query(models.SeedTask).filter(models.SeedTask.is_consumed == False)
    if policy_id:
        query = query.filter(models.SeedTask.policy_id == policy_id)
    return query.all()

def create_seed_task(db: Session, seed_task: models.SeedTask) -> models.SeedTask:
    db.add(seed_task)
    db.commit()
    db.refresh(seed_task)
    return seed_task

def mark_seed_task_consumed(db: Session, task_id: int) -> Optional[models.SeedTask]:
    seed_task = db.query(models.SeedTask).filter(models.SeedTask.id == task_id).first()
    if seed_task:
        seed_task.is_consumed = True
        db.commit()
        db.refresh(seed_task)
    return seed_task