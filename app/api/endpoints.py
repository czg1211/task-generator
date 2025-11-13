from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import crud
from app import schemas
from app import models
from app.config import settings
from app.services import TaskGenerationService
from app.scheduler import TaskScheduler
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# 创建调度器实例（单例模式）
_scheduler_instance = None


def get_scheduler() -> TaskScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TaskScheduler()
    return _scheduler_instance


@router.on_event("startup")
async def startup_event():
    """应用启动时初始化调度器"""
    scheduler = get_scheduler()
    if settings.SCHEDULER_AUTO_START:
        scheduler.start()
        # 使用独立的数据库会话来加载策略
        scheduler.load_all_policies()
        logger.info("调度器启动完成")


@router.on_event("shutdown")
async def shutdown_event():
    """应用关闭时停止调度器"""
    scheduler = get_scheduler()
    scheduler.stop()
    logger.info("调度器已停止")


# 服务状态接口
@router.get("/status", response_model=schemas.ServiceStatus)
async def get_service_status(scheduler: TaskScheduler = Depends(get_scheduler)):
    return schemas.ServiceStatus(
        status="running",
        scheduler_running=scheduler.is_running(),
        active_jobs=scheduler.get_job_count()
    )


@router.get("/status/active-policies")
async def get_active_policies(scheduler: TaskScheduler = Depends(get_scheduler)):
    """获取当前活跃的策略列表"""
    return {"active_policies": list(scheduler.get_active_policies())}


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
def create_policy_config(
        policy_config: schemas.PolicyConfigCreate,
        db: Session = Depends(get_db),
        scheduler: TaskScheduler = Depends(get_scheduler)
):
    db_policy_config = crud.get_policy_config(db, policy_id=policy_config.policy_id)
    if db_policy_config:
        raise HTTPException(status_code=400, detail="策略ID已存在")

    new_policy = crud.create_policy_config(db, models.PolicyConfig(**policy_config.model_dump()))

    # 如果策略是启用的，立即添加到调度器
    if policy_config.is_enabled:
        # 使用独立的数据库会话来获取策略配置
        task_db = crud.create_db_session()
        try:
            policy_task_config = crud.get_policy_task_gen_config(task_db, policy_config.policy_id)
            if policy_task_config:
                scheduler.add_policy_job(policy_task_config)
                logger.info(f"新策略 {policy_config.policy_id} 已立即上线")
        finally:
            task_db.close()

    return new_policy


@router.put("/policy-configs/{policy_id}/enable")
def enable_policy_config(
        policy_id: str,
        db: Session = Depends(get_db),
        scheduler: TaskScheduler = Depends(get_scheduler)
):
    policy_config = crud.update_policy_config_status(db, policy_id, True)
    if policy_config is None:
        raise HTTPException(status_code=404, detail="策略配置不存在")

    # 立即启用策略 - 使用独立的数据库会话
    task_db = crud.create_db_session()
    try:
        policy_task_config = crud.get_policy_task_gen_config(task_db, policy_id)
        if policy_task_config:
            scheduler.add_policy_job(policy_task_config)
            logger.info(f"策略 {policy_id} 已立即启用")
    finally:
        task_db.close()

    return policy_config


@router.put("/policy-configs/{policy_id}/disable")
def disable_policy_config(
        policy_id: str,
        db: Session = Depends(get_db),
        scheduler: TaskScheduler = Depends(get_scheduler)
):
    policy_config = crud.update_policy_config_status(db, policy_id, False)
    if policy_config is None:
        raise HTTPException(status_code=404, detail="策略配置不存在")

    # 立即停用策略
    scheduler.remove_policy_job(policy_id)
    logger.info(f"策略 {policy_id} 已立即停用")

    return policy_config


# 其他接口保持不变...
# PolicyTaskGenConfig, TaskSource, SeedTask 等接口...

# 手动触发任务生成
@router.post("/generate-tasks/{policy_id}")
async def generate_tasks_manual(policy_id: str, db: Session = Depends(get_db)):
    """手动触发任务生成"""
    # 使用独立的数据库会话来执行任务生成
    task_db = crud.create_db_session()
    try:
        task_service = TaskGenerationService(task_db)
        policy_config = crud.get_policy_task_gen_config(task_db, policy_id)
        if not policy_config:
            raise HTTPException(status_code=404, detail="策略配置不存在")

        # 检查策略是否启用
        policy = crud.get_policy_config(task_db, policy_id)
        if not policy or not policy.is_enabled:
            raise HTTPException(status_code=400, detail="策略未启用")

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
    finally:
        task_db.close()


# 立即执行策略
@router.post("/policies/{policy_id}/execute")
async def execute_policy_immediately(
        policy_id: str,
        scheduler: TaskScheduler = Depends(get_scheduler)
):
    """立即执行策略，不依赖cron表达式"""
    # 使用独立的数据库会话来执行
    db = crud.create_db_session()
    try:
        task_service = TaskGenerationService(db)
        policy_config = crud.get_policy_task_gen_config(db, policy_id)
        if not policy_config:
            raise HTTPException(status_code=404, detail="策略配置不存在")

        # 检查策略是否启用
        policy = crud.get_policy_config(db, policy_id)
        if not policy or not policy.is_enabled:
            raise HTTPException(status_code=400, detail="策略未启用")

        generated = task_service.generate_seed_tasks(policy_config)

        return schemas.TaskGenerationResult(
            success=True,
            generated_tasks=generated,
            message=f"立即执行成功，生成 {generated} 个任务"
        )
    finally:
        db.close()