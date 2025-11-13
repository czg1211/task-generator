import os
from urllib.parse import quote_plus
from typing import Optional


class Settings:
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "password")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "task_generator")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")

    # 处理密码中的特殊字符
    def _encode_password(self, password: str) -> str:
        """对密码进行URL编码，处理特殊字符"""
        return quote_plus(password)

    @property
    def DATABASE_URL(self) -> str:
        encoded_password = self._encode_password(self.POSTGRES_PASSWORD)
        return f"postgresql://{self.POSTGRES_USER}:{encoded_password}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    SCHEDULER_AUTO_START: bool = os.getenv("SCHEDULER_AUTO_START", "True").lower() == "true"


settings = Settings()