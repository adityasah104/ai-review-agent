import structlog
from fastapi import FastAPI
from contextlib import asynccontextmanager
from src.db.database import init_db
from src.gateway.routes import router
from src.queue.worker import start_worker_thread

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown."""
    log.info("app_starting")

    # Step 1: Initialize SQLite tables
    init_db()
    log.info("database_initialized")

    # Step 2: Start background worker thread
    start_worker_thread()
    log.info("worker_started")

    yield

    log.info("app_shutting_down")


app = FastAPI(
    title="AI PR Review Agent",
    description="Azure DevOps PR review bot using Amazon Bedrock Nova Pro + Aider",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)