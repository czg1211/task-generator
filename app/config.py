import os


class Settings:
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "task_generator")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")

    DATABASE_URL: str = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}" if POSTGRES_USER else f"postgresql://{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"

    SCHEDULER_AUTO_START: bool = os.getenv("SCHEDULER_AUTO_START", "True").lower() == "true"


settings = Settings()