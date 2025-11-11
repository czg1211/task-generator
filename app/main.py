from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.utils.logger import get_public_logger
from app.database import create_tables
from app.api.endpoints import router as api_router

logger = get_public_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时创建表
    create_tables()
    logger.info("数据库表创建完成")
    yield
    # 关闭时清理资源
    logger.info("应用关闭")

app = FastAPI(
    title="任务生成服务",
    description="基于策略的任务生成服务",
    version="1.0.0",
    lifespan=lifespan
)

# 注册路由
app.include_router(api_router, prefix="/api/v1", tags=["tasks"])

@app.get("/")
async def root():
    return {"message": "任务生成服务运行中"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)