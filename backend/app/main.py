import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import action_log, auth, chat, debug, diagnosis, memory, profiles, reports
from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import AppError, app_error_handler
from app.core.middleware import RequestIDFilter, RequestIDFormatter, RequestLoggingMiddleware
from app.core.rate_limit import limiter

if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        traces_sample_rate=0.1,  # 10% of requests get performance tracing
    )


def _setup_logging() -> None:
    """Configure root logger with console + rotating file handler.

    All log lines include the current request ID (``rid``) so that every
    log entry during a single HTTP request can be correlated.
    """
    level = settings.log_level.upper()
    fmt = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
    formatter = RequestIDFormatter(fmt)

    logging.basicConfig(level=level)

    # Replace default handler's formatter and add request ID filter
    root = logging.getLogger()
    root.addFilter(RequestIDFilter())
    for handler in root.handlers:
        handler.setFormatter(formatter)

    # Add rotating file handler (local/dev only — Railway containers are ephemeral)
    if settings.app_env != "production":
        log_dir = settings.log_dir
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "familyhealth.log"),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


_setup_logging()
logger = logging.getLogger(__name__)


async def _purge_old_traces() -> None:
    """Delete LLM traces older than the configured retention period."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import text

    from app.core.database import async_session_factory

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.llm_trace_retention_days)
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                text("DELETE FROM llm_traces WHERE created_at < :cutoff"),
                {"cutoff": cutoff},
            )
            await session.commit()
            if result.rowcount:
                logger.info(
                    "Purged %d LLM traces older than %d days",
                    result.rowcount,
                    settings.llm_trace_retention_days,
                )
    except Exception:
        logger.warning("LLM trace purge failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("FamilyHealth AI backend starting up (env=%s)", settings.app_env)
    settings.validate_prod_secrets()
    await _purge_old_traces()
    yield
    await engine.dispose()
    logger.info("FamilyHealth AI backend shut down")


app = FastAPI(
    title="FamilyHealth AI",
    description="Family health management platform API",
    version="0.1.0",
    lifespan=lifespan,
)

origins = (
    ["*"]
    if settings.app_env == "development"
    else [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(AppError, app_error_handler)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
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
app.include_router(debug.router, prefix=API_V1)


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}
