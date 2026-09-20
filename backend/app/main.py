"""FinSight AI — app factory, FINAL (Phase 7): auth guards on v1 routes,
rate limits, Prometheus /metrics, /usage cost panel.

Public routes: /api/v1/health, /metrics, /api/v1/auth/*.
Everything else requires a Bearer token or X-API-Key (disabled in dev).
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import ALL_ROUTERS
from app.core.errors import register_error_handlers
from app.core.logging import bind_request_id, configure_logging, get_logger
from app.core.metrics import instrument_app
from app.core.middleware import RequestIDMiddleware
from app.core.ratelimit import build_limiter, register_rate_limit_handler
from app.core.security import get_current_user
from app.core.settings import get_settings
from app.db.session import dispose_engine, get_db, get_engine

logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.app_env, settings.log_level)
    app.state.limiter = build_limiter()
    logger.info("startup", env=settings.app_env, version=app.version)
    yield
    await dispose_engine()
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="FinSight AI",
        version="1.0.0",
        description="AI investment due-diligence & valuation platform (deterministic-first).",
        lifespan=lifespan,
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,  # prod: lock to the frontend origin
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    register_rate_limit_handler(app)

    # --- public routes ------------------------------------------------------
    @app.get(f"{settings.api_prefix}/health")
    async def health() -> dict:
        db_status, redis_status = "ok", "ok"
        try:
            from sqlalchemy import text

            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001
            db_status = f"error: {type(exc).__name__}"
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
        except Exception:  # noqa: BLE001
            redis_status = "error"
        status = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
        return {"status": status, "db": db_status, "redis": redis_status,
                "version": app.version}

    from app.api.v1.auth import router as auth_router

    app.include_router(auth_router, prefix=settings.api_prefix)

    @app.get(f"{settings.api_prefix}/usage")
    async def usage(db: AsyncSession = Depends(get_db),
                    user=Depends(get_current_user)) -> dict:
        from app.core.metrics import usage_summary

        return await usage_summary(db)

    # --- guarded business routes -------------------------------------------
    for router in ALL_ROUTERS:
        app.include_router(router, prefix=settings.api_prefix,
                           dependencies=[Depends(get_current_user)])

    instrument_app(app)  # /metrics (prometheus format)
    return app


bind_request_id()
app = create_app()
