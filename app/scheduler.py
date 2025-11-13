from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from app.database import create_db_session
from app import crud
from app.services import TaskGenerationService
import logging
from typing import Dict, Any, Set
from datetime import datetime
import threading
import time

logger = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.jobs: Dict[str, str] = {}  # policy_id -> job_id
        self.last_check_time = datetime.now()
        self.monitor_thread = None
        self.monitor_running = False
        self.lock = threading.Lock()

    def start(self):
        """启动调度器"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("任务调度器已启动")

            # 启动策略监控线程
            self.monitor_running = True
            self.monitor_thread = threading.Thread(target=self._monitor_policies, daemon=True)
            self.monitor_thread.start()
            logger.info("策略监控线程已启动")

    def stop(self):
        """停止调度器"""
        self.monitor_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

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
        """执行策略生成任务 - 每个任务使用独立的数据库会话"""
        db = create_db_session()
        try:
            task_service = TaskGenerationService(db)
            policy_config = crud.get_policy_task_gen_config(db, policy_id)
            if policy_config:
                # 检查策略是否启用
                policy = crud.get_policy_config(db, policy_id)
                if not policy or not policy.is_enabled:
                    logger.info(f"策略 {policy_id} 已禁用，跳过执行")
                    return

                # 只执行定时任务
                if policy_config.task_type.value == "scheduled":
                    generated = task_service.generate_seed_tasks(policy_config)
                    logger.info(f"策略 {policy_id} 执行完成，生成 {generated} 个任务")
                else:
                    logger.info(f"策略 {policy_id} 是一次性任务，跳过定时执行")
        except Exception as e:
            logger.error(f"执行策略 {policy_id} 失败: {str(e)}")
        finally:
            db.close()

    def _monitor_policies(self):
        """监控策略变化 - 使用独立的数据库会话"""
        logger.info("开始监控策略变化")

        while self.monitor_running:
            try:
                # 为监控线程创建独立的数据库会话
                db = create_db_session()
                try:
                    # 获取当前所有策略配置
                    current_policies = crud.get_policy_task_gen_configs(db)

                    # 获取当前活跃的策略ID
                    current_active_policies = set(self.jobs.keys())

                    # 获取应该启用的策略ID
                    should_be_active = set()
                    for policy in current_policies:
                        policy_config = crud.get_policy_config(db, policy.policy_id)
                        if (policy_config and policy_config.is_enabled and
                                policy.task_type.value == "scheduled"):
                            should_be_active.add(policy.policy_id)

                    # 添加新策略
                    new_policies = should_be_active - current_active_policies
                    for policy_id in new_policies:
                        logger.info(f"检测到新策略上线: {policy_id}")
                        policy_config = crud.get_policy_task_gen_config(db, policy_id)
                        if policy_config:
                            self.add_policy_job(policy_config)

                    # 移除下线的策略
                    removed_policies = current_active_policies - should_be_active
                    for policy_id in removed_policies:
                        logger.info(f"检测到策略下线: {policy_id}")
                        self.remove_policy_job(policy_id)

                finally:
                    db.close()

                # 每30秒检查一次（减少数据库压力）
                for i in range(30):
                    if not self.monitor_running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"策略监控出错: {str(e)}")
                time.sleep(10)  # 出错后等待10秒再继续

    def load_all_policies(self):
        """加载所有策略配置 - 使用独立的数据库会话"""
        db = create_db_session()
        try:
            policies = crud.get_policy_task_gen_configs(db)
            loaded_count = 0

            for policy in policies:
                # 只加载启用的策略
                policy_config = crud.get_policy_config(db, policy.policy_id)
                if policy_config and policy_config.is_enabled:
                    if self.add_policy_job(policy):
                        loaded_count += 1

            logger.info(f"已加载 {loaded_count} 个策略配置")
        finally:
            db.close()

    def get_job_count(self) -> int:
        """获取任务数量"""
        return len(self.scheduler.get_jobs())

    def get_active_policies(self) -> Set[str]:
        """获取当前活跃的策略ID"""
        return set(self.jobs.keys())