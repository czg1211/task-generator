from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from typing import Dict
from app import crud
from app.utils.logger import get_public_logger
from app.services import TaskGenerationService

logger = get_public_logger()


class TaskScheduler:
    def __init__(self, db_session: Session):
        self.scheduler = BackgroundScheduler()
        self.db_session = db_session
        self.task_service = TaskGenerationService(db_session)
        self.jobs: Dict[str, str] = {}  # policy_id -> job_id

    def start(self):
        """启动调度器"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("任务调度器已启动")

    def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("任务调度器已停止")

    def is_running(self) -> bool:
        """检查调度器是否运行"""
        return self.scheduler.running

    def add_policy_job(self, policy_config):
        """添加策略任务"""
        try:
            # 一次性任务不需要添加到调度器
            if policy_config.task_type.value == "one_time":
                logger.info(f"策略 {policy_config.policy_id} 是一次性任务，不添加到调度器")
                return True

            # 移除已存在的任务
            self.remove_policy_job(policy_config.policy_id)

            # 添加新任务（仅定时任务）
            job_id = f"policy_{policy_config.policy_id}"
            trigger = CronTrigger.from_crontab(policy_config.cron_expression)

            job = self.scheduler.add_job(
                self._execute_policy,
                trigger=trigger,
                args=[policy_config.policy_id],
                id=job_id,
                replace_existing=True
            )

            self.jobs[policy_config.policy_id] = job_id
            logger.info(f"已添加策略任务: {policy_config.policy_id}, cron: {policy_config.cron_expression}")
            return True

        except Exception as e:
            logger.error(f"添加策略任务失败: {str(e)}")
            return False

    def remove_policy_job(self, policy_id: str):
        """移除策略任务"""
        job_id = self.jobs.get(policy_id)
        if job_id and self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            self.jobs.pop(policy_id, None)
            logger.info(f"已移除策略任务: {policy_id}")

    def _execute_policy(self, policy_id: str):
        """执行策略生成任务"""
        try:
            policy_config = crud.get_policy_task_gen_config(self.db_session, policy_id)
            if policy_config:
                # 只执行定时任务
                if policy_config.task_type.value == "scheduled":
                    generated = self.task_service.generate_seed_tasks(policy_config)
                    logger.info(f"策略 {policy_id} 执行完成，生成 {generated} 个任务")
                else:
                    logger.info(f"策略 {policy_id} 是一次性任务，跳过定时执行")
        except Exception as e:
            logger.error(f"执行策略 {policy_id} 失败: {str(e)}")

    def load_all_policies(self):
        """加载所有策略配置"""
        policies = crud.get_enabled_policy_configs(self.db_session)
        loaded_count = 0

        for policy in policies:
            if self.add_policy_job(policy):
                loaded_count += 1

        logger.info(f"已加载 {loaded_count} 个策略配置（{len(policies) - loaded_count} 个一次性任务）")

    def get_job_count(self) -> int:
        """获取任务数量"""
        return len(self.scheduler.get_jobs())