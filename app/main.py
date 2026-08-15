from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import create_db_and_tables
from app.api.auth import router as auth_router
from app.api.proxies import router as proxies_router


def create_app(db_engine=None):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if db_engine is None:
            create_db_and_tables()
        yield

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

    if db_engine is not None:
        # Override get_session dependency for testing
        from sqlmodel import Session
        from app.core.database import get_session

        def override_get_session():
            with Session(db_engine) as session:
                yield session

        app.dependency_overrides[get_session] = override_get_session

    return app


app = create_app()
