import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import action_log, auth, chat, diagnosis, memory, profiles, reports
from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import AppError, app_error_handler

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)

app = FastAPI(
    title="FamilyHealth AI",
    description="Family health management platform API",
    version="0.1.0",
)

origins = (
    ["*"]
    if settings.app_env == "development"
    else settings.allowed_origins.split(",") if settings.allowed_origins else []
)

app.add_exception_handler(AppError, app_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
API_V1 = "/api/v1"
app.include_router(auth.router, prefix=API_V1)
app.include_router(profiles.router, prefix=API_V1)
app.include_router(diagnosis.router, prefix=API_V1)
app.include_router(reports.router, prefix=API_V1)
app.include_router(chat.router, prefix=API_V1)
app.include_router(memory.router, prefix=API_V1)
app.include_router(action_log.router, prefix=API_V1)


@app.on_event("startup")
async def startup() -> None:
    logger.info("FamilyHealth AI backend starting up (env=%s)", settings.app_env)


@app.on_event("shutdown")
async def shutdown() -> None:
    await engine.dispose()
    logger.info("FamilyHealth AI backend shut down")


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}
