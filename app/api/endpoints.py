from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from .. import crud, config
from .. import schemas
from .. import models
from ..services import TaskGenerationService
from ..scheduler import TaskScheduler

router = APIRouter()


# 依赖注入调度器实例
def get_scheduler() -> TaskScheduler:
    return router.scheduler


@router.on_event("startup")
async def startup_event():
    """应用启动时初始化调度器"""
    db = next(get_db())
    router.scheduler = TaskScheduler(db)
    if config.settings.SCHEDULER_AUTO_START:
        router.scheduler.start()
        router.scheduler.load_all_policies()


@router.on_event("shutdown")
async def shutdown_event():
    """应用关闭时停止调度器"""
    if hasattr(router, 'scheduler'):
        router.scheduler.stop()


# 服务状态接口
@router.get("/status", response_model=schemas.ServiceStatus)
async def get_service_status(scheduler: TaskScheduler = Depends(get_scheduler)):
    return schemas.ServiceStatus(
        status="running",
        scheduler_running=scheduler.is_running(),
        active_jobs=scheduler.get_job_count()
    )


@router.post("/scheduler/start")
async def start_scheduler(scheduler: TaskScheduler = Depends(get_scheduler)):
    """启动调度器"""
    scheduler.start()
    scheduler.load_all_policies()
    return {"message": "调度器已启动"}


@router.post("/scheduler/stop")
async def stop_scheduler(scheduler: TaskScheduler = Depends(get_scheduler)):
    """停止调度器"""
    scheduler.stop()
    return {"message": "调度器已停止"}


@router.post("/scheduler/reload")
async def reload_scheduler(scheduler: TaskScheduler = Depends(get_scheduler)):
    """重新加载所有策略"""
    scheduler.load_all_policies()
    return {"message": "策略已重新加载"}


# PolicyConfig 接口
@router.get("/policy-configs", response_model=List[schemas.PolicyConfig])
def read_policy_configs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_policy_configs(db, skip=skip, limit=limit)


@router.post("/policy-configs", response_model=schemas.PolicyConfig)
def create_policy_config(policy_config: schemas.PolicyConfigCreate, db: Session = Depends(get_db)):
    db_policy_config = crud.get_policy_config(db, policy_id=policy_config.policy_id)
    if db_policy_config:
        raise HTTPException(status_code=400, detail="策略ID已存在")
    return crud.create_policy_config(db, models.PolicyConfig(**policy_config.dict()))


@router.put("/policy-configs/{policy_id}/enable")
def enable_policy_config(policy_id: str, db: Session = Depends(get_db)):
    policy_config = crud.update_policy_config_status(db, policy_id, True)
    if policy_config is None:
        raise HTTPException(status_code=404, detail="策略配置不存在")
    return policy_config


@router.put("/policy-configs/{policy_id}/disable")
def disable_policy_config(policy_id: str, db: Session = Depends(get_db)):
    policy_config = crud.update_policy_config_status(db, policy_id, False)
    if policy_config is None:
        raise HTTPException(status_code=404, detail="策略配置不存在")
    return policy_config


# PolicyTaskGenConfig 接口
@router.get("/policy-task-configs", response_model=List[schemas.PolicyTaskGenConfig])
def read_policy_task_configs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_policy_task_gen_configs(db, skip=skip, limit=limit)


@router.post("/policy-task-configs", response_model=schemas.PolicyTaskGenConfig)
def create_policy_task_config(config: schemas.PolicyTaskGenConfigCreate, db: Session = Depends(get_db)):
    db_config = crud.get_policy_task_gen_config(db, policy_id=config.policy_id)
    if db_config:
        raise HTTPException(status_code=400, detail="策略任务配置已存在")

    # 创建模型实例，枚举值会自动转换
    db_model = models.PolicyTaskGenConfig(**config.dict())
    return crud.create_policy_task_gen_config(db, db_model)


# TaskSource 接口
@router.get("/task-sources", response_model=List[schemas.TaskSource])
def read_task_sources(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_task_sources(db, skip=skip, limit=limit)


@router.post("/task-sources", response_model=schemas.TaskSource)
def create_task_source(task_source: schemas.TaskSourceCreate, db: Session = Depends(get_db)):
    return crud.create_task_source(db, models.TaskSource(**task_source.dict()))


# SeedTask 接口
@router.get("/seed-tasks", response_model=List[schemas.SeedTask])
def read_seed_tasks(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    tasks = crud.get_seed_tasks(db, skip=skip, limit=limit)
    return tasks


@router.get("/seed-tasks/pending", response_model=List[schemas.SeedTask])
def read_pending_seed_tasks(policy_id: str = None, db: Session = Depends(get_db)):
    tasks = crud.get_pending_seed_tasks(db, policy_id)
    return tasks


@router.post("/seed-tasks/{task_id}/consume")
def consume_seed_task(task_id: int, db: Session = Depends(get_db)):
    task = crud.mark_seed_task_consumed(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="种子任务不存在")
    return {"message": "任务已消费"}


# 手动触发任务生成
@router.post("/generate-tasks/{policy_id}")
async def generate_tasks_manual(policy_id: str, db: Session = Depends(get_db)):
    """手动触发任务生成"""
    task_service = TaskGenerationService(db)
    policy_config = crud.get_policy_task_gen_config(db, policy_id)
    if not policy_config:
        raise HTTPException(status_code=404, detail="策略配置不存在")

    # 根据任务类型选择不同的处理方法
    if policy_config.task_type == models.TaskType.ONE_TIME:
        generated = task_service.handle_one_time_task_generation(policy_config)
    else:
        generated = task_service.generate_seed_tasks(policy_config)

    return schemas.TaskGenerationResult(
        success=True,
        generated_tasks=generated,
        message=f"成功生成 {generated} 个任务"
    )


# 获取可用的任务类型
@router.get("/task-types")
async def get_task_types():
    """获取可用的任务类型枚举"""
    return {task_type.value: task_type.value for task_type in schemas.TaskType}