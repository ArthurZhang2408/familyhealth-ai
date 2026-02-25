import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, diagnosis, memory, profiles, reports
from app.core.config import settings
from app.core.database import engine

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)

app = FastAPI(
    title="FamilyHealth AI",
    description="Family health management platform API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router)
app.include_router(profiles.router)
app.include_router(diagnosis.router)
app.include_router(reports.router)
app.include_router(chat.router)
app.include_router(memory.router)


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
