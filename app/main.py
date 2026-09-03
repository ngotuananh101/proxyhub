from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.api.auth import router as auth_router
from app.api.events import router as events_router
from app.api.gateway_credentials import router as gateway_credentials_router
from app.api.internal import router as internal_router
from app.api.logs import router as logs_router
from app.api.proxies import router as proxies_router
from app.api.settings import router as settings_router
from app.api.sources import router as sources_router
from app.api.stats import router as stats_router
from app.api.tenants import router as tenants_router
from app.core.config import settings, validate_secrets
from app.core.database import create_db_and_tables, engine
from app.services.events import start_relay, stop_relay
from app.services.settings_service import seed_settings
from app.services.source_service import seed_default_sources
from app.services.tenant_service import ensure_default_tenant


def create_app(db_engine=None):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        validate_secrets(settings)
        if db_engine is None:
            create_db_and_tables()
        with Session(db_engine or engine) as session:
            seed_settings(session)
            default_tenant = ensure_default_tenant(session)
            seed_default_sources(session, tenant_id=default_tenant.id)
        start_relay()
        yield
        await stop_relay()

    app = FastAPI(title="ProxyHub", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(proxies_router)
    app.include_router(stats_router)
    app.include_router(settings_router)
    app.include_router(sources_router)
    app.include_router(logs_router)
    app.include_router(events_router)
    app.include_router(internal_router)
    app.include_router(tenants_router)
    app.include_router(gateway_credentials_router)

    if db_engine is not None:
        # Override get_session dependency for testing
        from app.core.database import get_session

        def override_get_session():
            with Session(db_engine) as session:
                yield session

        app.dependency_overrides[get_session] = override_get_session

    return app


app = create_app()
