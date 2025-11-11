from sqlalchemy.orm import Session
from sqlalchemy import text
from app import models
from app import crud
from typing import Dict, Any, List

from app.utils.logger import get_public_logger

logger = get_public_logger()


class TaskGenerationService:
    def __init__(self, db: Session):
        self.db = db

    def execute_task_generation_sql(self, policy_id: str, task_gen_sql: str) -> List[Dict[str, Any]]:
        """执行任务生成SQL，返回结果集"""
        try:
            # 这里可以添加SQL安全检查和参数绑定
            result = self.db.execute(text(task_gen_sql))
            rows = []
            for row in result:
                # 将行转换为字典
                row_dict = {}
                for i, col in enumerate(result.keys()):
                    # 处理枚举值的转换
                    value = row[i]
                    if hasattr(value, 'value'):  # 如果是枚举类型，获取其值
                        value = value.value
                    row_dict[col] = value
                rows.append(row_dict)
            return rows
        except Exception as e:
            logger.error(f"执行策略 {policy_id} 的SQL失败: {str(e)}")
            return []

    def generate_seed_tasks(self, policy_config: models.PolicyTaskGenConfig) -> int:
        """根据策略配置生成种子任务"""
        try:
            # 检查策略是否启用
            policy = crud.get_policy_config(self.db, policy_config.policy_id)
            if not policy or not policy.is_enabled:
                logger.info(f"策略 {policy_config.policy_id} 未启用，跳过任务生成")
                return 0

            # 执行任务生成SQL
            results = self.execute_task_generation_sql(
                policy_config.policy_id,
                policy_config.task_gen_sql
            )

            generated_count = 0
            for result in results:
                # 创建种子任务
                seed_task = models.SeedTask(
                    policy_id=policy_config.policy_id,
                    task_type=policy_config.task_type,  # 直接使用枚举值
                    task_params=result
                )
                crud.create_seed_task(self.db, seed_task)
                generated_count += 1

            logger.info(f"策略 {policy_config.policy_id} 生成 {generated_count} 个种子任务")
            return generated_count

        except Exception as e:
            logger.error(f"生成种子任务失败: {str(e)}")
            return 0

    def get_one_time_tasks(self, policy_id: str) -> List[models.SeedTask]:
        """获取一次性任务"""
        return crud.get_pending_seed_tasks(self.db, policy_id)

    def consume_one_time_task(self, task_id: int) -> bool:
        """消费一次性任务"""
        task = crud.mark_seed_task_consumed(self.db, task_id)
        return task is not None

    def handle_one_time_task_generation(self, policy_config: models.PolicyTaskGenConfig) -> int:
        """处理一次性任务生成（生成后立即标记为已消费）"""
        if policy_config.task_type != models.TaskType.ONE_TIME:
            logger.warning(f"策略 {policy_config.policy_id} 不是一次性任务类型")
            return 0

        generated_count = self.generate_seed_tasks(policy_config)

        # 对于一次性任务，生成后立即标记为已消费
        if generated_count > 0:
            pending_tasks = self.get_one_time_tasks(policy_config.policy_id)
            for task in pending_tasks:
                self.consume_one_time_task(task.id)
            logger.info(f"一次性任务 {policy_config.policy_id} 已生成并消费 {generated_count} 个任务")

        return generated_count