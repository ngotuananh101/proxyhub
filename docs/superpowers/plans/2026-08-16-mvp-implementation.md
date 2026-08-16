# ProxyHub MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working end-to-end proxy rotation system: FastAPI backend + proxy.py gateway plugin + React dashboard, with JWT auth and SQLite storage.

**Architecture:** FastAPI serves REST API + internal proxy-selection endpoint. A proxy.py plugin calls the internal API per-request to pick an alive proxy and forwards traffic through it. React dashboard manages the proxy pool via the REST API.

**Tech Stack:** Python 3.10+, FastAPI, SQLModel, Pydantic v2, proxy.py 2.4.10, bcrypt, PyJWT, React 18, Vite, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, React Router v6, Vitest, pytest

## Global Constraints

- Python >= 3.10, Node >= 18
- SQLite with WAL mode + busy_timeout=5000ms
- JWT via PyJWT (not python-jose), password hash via bcrypt directly (not passlib)
- proxy.py pinned to ==2.4.10
- Gateway plugin flag: `--plugins` (not `--plugin-name`)
- Internal API auth: header `X-Internal-Key`, constant-time compare
- CORS: allow `http://localhost:5173` via env `CORS_ORIGINS`
- All backend tests in `tests/`, frontend tests co-located or in `src/__tests__/`
- Ruff for Python linting/formatting
- No Alembic in MVP — SQLModel `create_all()` on startup
- Windows native dev: Celery not needed in Part 1

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/core/__init__.py`
- Create: `app/models/__init__.py`
- Create: `app/schemas/__init__.py`
- Create: `app/api/__init__.py`
- Create: `app/services/__init__.py`
- Create: `app/gateway/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "proxyhub"
version = "0.1.0"
requires-python = ">=3.10"

[tool.ruff]
target-version = "py310"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "W"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create requirements.txt**

```text
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
sqlmodel>=0.0.22
pydantic>=2.9.0
pydantic-settings>=2.5.0
bcrypt>=4.2.0
PyJWT>=2.9.0
httpx>=0.27.0
python-multipart>=0.0.9
proxy.py==2.4.10
```

- [ ] **Step 3: Create requirements-dev.txt**

```text
-r requirements.txt
pytest>=8.3.0
pytest-asyncio>=0.24.0
ruff>=0.6.0
```

- [ ] **Step 4: Create .gitignore**

```text
# Python
venv/
__pycache__/
*.pyc
*.egg-info/
dist/
build/

# Environment
.env

# Database
*.db
*.db-wal
*.db-shm

# Node
node_modules/
frontend/dist/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 5: Create .env.example**

```env
# Database
DATABASE_URL=sqlite:///./proxyhub.db

# Redis (For Celery - Part 2)
REDIS_URL=redis://localhost:6379/0

# JWT Auth
SECRET_KEY=change_me_to_a_random_string
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Celery (Part 2)
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Gateway
GATEWAY_API_URL=http://localhost:8000/internal/proxies
INTERNAL_API_KEY=change_me_internal_key

# CORS
CORS_ORIGINS=http://localhost:5173
```

- [ ] **Step 6: Create package __init__.py files and tests/conftest.py**

All `__init__.py` files are empty. `tests/conftest.py`:

```python
import os
import pytest
from sqlmodel import SQLModel, Session, create_engine

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")

# Import models so SQLModel.metadata knows about them before create_all
from app.models import User, Proxy, ProxyStatus  # noqa: F401, E402


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session
```

- [ ] **Step 7: Install dependencies and verify**

Run:
```bash
cd D:/Source/ponta/proxyhub
./venv/Scripts/pip install -r requirements-dev.txt
```
Expected: all packages install successfully.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml requirements.txt requirements-dev.txt .gitignore .env.example app/ tests/
git commit -m "chore: scaffold project structure and dependencies"
```

---

### Task 2: Core Config + Database

**Files:**
- Create: `app/core/config.py`
- Create: `app/core/database.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `settings` (Settings instance), `get_engine()`, `get_session()` (FastAPI dependency)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from app.core.config import Settings


def test_settings_defaults():
    s = Settings(
        _env_file=None,
        DATABASE_URL="sqlite:///./test.db",
        SECRET_KEY="abc",
        INTERNAL_API_KEY="key",
    )
    assert s.ALGORITHM == "HS256"
    assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 1440
    assert s.cors_origins_list == ["http://localhost:5173"]


def test_settings_cors_parsing():
    s = Settings(
        _env_file=None,
        DATABASE_URL="sqlite:///./test.db",
        SECRET_KEY="abc",
        INTERNAL_API_KEY="key",
        CORS_ORIGINS="http://a.com,http://b.com",
    )
    assert s.cors_origins_list == ["http://a.com", "http://b.com"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.config'`

- [ ] **Step 3: Implement config**

```python
# app/core/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./proxyhub.db"
    SECRET_KEY: str = "change_me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    INTERNAL_API_KEY: str = "change_me"
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 4: Implement database**

```python
# app/core/database.py
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event

from app.core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py app/core/database.py tests/test_config.py
git commit -m "feat: add core config and database setup with SQLite WAL"
```

---

### Task 3: Security (JWT + Password Hashing)

**Files:**
- Create: `app/core/security.py`
- Test: `tests/test_security.py`

**Interfaces:**
- Produces: `hash_password(plain: str) -> str`, `verify_password(plain: str, hashed: str) -> bool`, `create_access_token(data: dict) -> str`, `decode_access_token(token: str) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_security.py
import time
import pytest
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


def test_hash_and_verify_password():
    hashed = hash_password("mypassword")
    assert hashed != "mypassword"
    assert verify_password("mypassword", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_create_and_decode_token():
    token = create_access_token({"sub": "42"})
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert "exp" in payload


def test_expired_token():
    token = create_access_token({"sub": "42"}, expires_delta=-1)
    with pytest.raises(Exception):
        decode_access_token(token)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python -m pytest tests/test_security.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement security module**

```python
# app/core/security.py
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict, expires_delta: int | None = None) -> str:
    to_encode = data.copy()
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + timedelta(minutes=expires_delta)
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/Scripts/python -m pytest tests/test_security.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/core/security.py tests/test_security.py
git commit -m "feat: add JWT token and bcrypt password utilities"
```

---

### Task 4: Database Models

**Files:**
- Create: `app/models/user.py`
- Create: `app/models/proxy.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `User` (SQLModel table), `Proxy` (SQLModel table), `ProxyStatus` (str enum)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from sqlmodel import Session, select
from app.models.user import User
from app.models.proxy import Proxy, ProxyStatus


def test_create_user(session):
    user = User(username="admin", hashed_password="hash123", is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    assert user.id is not None
    assert user.username == "admin"
    assert user.is_admin is True


def test_create_proxy(session):
    proxy = Proxy(
        scheme="http",
        host="1.2.3.4",
        port=8080,
        username="user1",
        password="pass1",
    )
    session.add(proxy)
    session.commit()
    session.refresh(proxy)
    assert proxy.id is not None
    assert proxy.status == ProxyStatus.UNKNOWN
    assert proxy.latency_ms is None


def test_proxy_unique_constraint(session):
    p1 = Proxy(scheme="http", host="1.2.3.4", port=8080)
    session.add(p1)
    session.commit()

    p2 = Proxy(scheme="http", host="1.2.3.4", port=8080)
    session.add(p2)
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement models**

```python
# app/models/user.py
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: Optional[str] = Field(default=None, unique=True)
    hashed_password: str
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

```python
# app/models/proxy.py
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field, UniqueConstraint


class ProxyStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    ALIVE = "alive"
    DEAD = "dead"


class Proxy(SQLModel, table=True):
    __tablename__ = "proxies"
    __table_args__ = (
        UniqueConstraint("scheme", "host", "port", name="uq_proxy_scheme_host_port"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    scheme: str = Field(index=True)  # http | https
    host: str = Field(index=True)
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    status: ProxyStatus = Field(default=ProxyStatus.UNKNOWN, index=True)
    latency_ms: Optional[float] = None
    last_checked_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

```python
# app/models/__init__.py
from app.models.user import User
from app.models.proxy import Proxy, ProxyStatus

__all__ = ["User", "Proxy", "ProxyStatus"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/Scripts/python -m pytest tests/test_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/models/ tests/test_models.py
git commit -m "feat: add User and Proxy database models"
```

---

### Task 5: Auth Service + API

**Files:**
- Create: `app/services/auth_service.py`
- Create: `app/api/deps.py`
- Create: `app/api/auth.py`
- Create: `app/schemas/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `User` model, `hash_password`, `verify_password`, `create_access_token`, `decode_access_token`, `get_session`
- Produces: `get_current_user` (FastAPI dependency), `/api/auth/login`, `/api/auth/me`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth.py
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.user import User
from app.core.security import hash_password


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


@pytest.fixture(name="admin_user")
def admin_user_fixture(engine):
    with Session(engine) as session:
        user = User(
            username="admin",
            hashed_password=hash_password("admin123"),
            is_admin=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def test_login_success(client, admin_user):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client, admin_user):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_with_token(client, admin_user):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python -m pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Implement schemas**

```python
# app/schemas/auth.py
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    email: str | None = None
    is_admin: bool
```

- [ ] **Step 4: Implement auth service**

```python
# app/services/auth_service.py
from sqlmodel import Session, select

from app.models.user import User
from app.core.security import verify_password, create_access_token


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    user = session.exec(select(User).where(User.username == username)).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_token_for_user(user: User) -> str:
    return create_access_token({"sub": str(user.id)})
```

- [ ] **Step 5: Implement API dependencies**

```python
# app/api/deps.py
import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import decode_access_token
from app.core.config import settings
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = int(payload.get("sub", 0))
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def verify_internal_key(x_internal_key: str = "") -> None:
    if not hmac.compare_digest(x_internal_key, settings.INTERNAL_API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal key")
```

- [ ] **Step 6: Implement auth router**

```python
# app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.database import get_session
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.services.auth_service import authenticate_user, create_token_for_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    user = authenticate_user(session, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_token_for_user(user)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_admin=current_user.is_admin,
    )
```

- [ ] **Step 7: Create minimal app/main.py with create_app factory**

```python
# app/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import create_db_and_tables
from app.api.auth import router as auth_router


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
```

> Note: Tasks 7 and 8 will add `proxies_router`, `stats_router`, and `internal_router` to this file.

- [ ] **Step 8: Run test to verify it passes**

Run: `./venv/Scripts/python -m pytest tests/test_auth.py -v`
Expected: PASS (4 tests)

- [ ] **Step 9: Commit**

```bash
git add app/schemas/auth.py app/services/auth_service.py app/api/deps.py app/api/auth.py app/main.py tests/test_auth.py
git commit -m "feat: add JWT auth with login and me endpoints"
```

---

### Task 6: Proxy Service (Parse, Import, Select)

**Files:**
- Create: `app/services/proxy_service.py`
- Create: `app/schemas/proxy.py`
- Test: `tests/test_proxy_service.py`

**Interfaces:**
- Consumes: `Proxy`, `ProxyStatus` models, `Session`
- Produces: `parse_proxy_line(line: str) -> dict | None`, `import_proxies(session, text) -> ImportResult`, `select_random_proxy(session) -> Proxy | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_proxy_service.py
import pytest
from sqlmodel import Session

from app.models.proxy import Proxy, ProxyStatus
from app.services.proxy_service import parse_proxy_line, import_proxies, select_random_proxy


class TestParseProxyLine:
    def test_http_with_auth(self):
        result = parse_proxy_line("http://user:pass@1.2.3.4:8080")
        assert result == {
            "scheme": "http",
            "host": "1.2.3.4",
            "port": 8080,
            "username": "user",
            "password": "pass",
        }

    def test_http_without_auth(self):
        result = parse_proxy_line("http://5.6.7.8:3128")
        assert result == {
            "scheme": "http",
            "host": "5.6.7.8",
            "port": 3128,
            "username": None,
            "password": None,
        }

    def test_https(self):
        result = parse_proxy_line("https://10.0.0.1:443")
        assert result["scheme"] == "https"

    def test_socks5_parsed_but_not_gateway_supported(self):
        result = parse_proxy_line("socks5://1.2.3.4:1080")
        assert result["scheme"] == "socks5"

    def test_invalid_scheme(self):
        assert parse_proxy_line("ftp://1.2.3.4:21") is None

    def test_missing_port(self):
        assert parse_proxy_line("http://1.2.3.4") is None

    def test_empty_line(self):
        assert parse_proxy_line("") is None
        assert parse_proxy_line("   ") is None

    def test_garbage(self):
        assert parse_proxy_line("not a url at all") is None


class TestImportProxies:
    def test_import_multiple(self, session):
        text = "http://1.1.1.1:80\nhttp://2.2.2.2:80\nhttp://3.3.3.3:80"
        result = import_proxies(session, text)
        assert result.imported == 3
        assert result.duplicates == 0
        assert len(result.invalid) == 0

    def test_import_with_duplicates(self, session):
        text = "http://1.1.1.1:80\nhttp://1.1.1.1:80"
        result = import_proxies(session, text)
        assert result.imported == 1
        assert result.duplicates == 1

    def test_import_with_invalid_lines(self, session):
        text = "http://1.1.1.1:80\ngarbage\nhttp://2.2.2.2:80"
        result = import_proxies(session, text)
        assert result.imported == 2
        assert len(result.invalid) == 1
        assert result.invalid[0]["line"] == "garbage"


class TestSelectRandomProxy:
    def test_select_excludes_dead(self, session):
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.DEAD))
        session.add(Proxy(scheme="http", host="2.2.2.2", port=80, status=ProxyStatus.ALIVE))
        session.commit()
        proxy = select_random_proxy(session)
        assert proxy is not None
        assert proxy.host == "2.2.2.2"

    def test_select_includes_unknown(self, session):
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.UNKNOWN))
        session.commit()
        proxy = select_random_proxy(session)
        assert proxy is not None

    def test_select_excludes_socks5(self, session):
        session.add(Proxy(scheme="socks5", host="1.1.1.1", port=1080, status=ProxyStatus.ALIVE))
        session.commit()
        proxy = select_random_proxy(session)
        assert proxy is None

    def test_select_empty_pool(self, session):
        assert select_random_proxy(session) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python -m pytest tests/test_proxy_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement schemas**

```python
# app/schemas/proxy.py
from pydantic import BaseModel


class ProxyCreate(BaseModel):
    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None


class ProxyUpdate(BaseModel):
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None


class ProxyResponse(BaseModel):
    id: int
    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    status: str
    latency_ms: float | None = None
    last_checked_at: str | None = None
    created_at: str
    updated_at: str


class ProxyListResponse(BaseModel):
    items: list[ProxyResponse]
    total: int
    page: int
    size: int


class ImportRequest(BaseModel):
    text: str


class InvalidLine(BaseModel):
    line: str
    reason: str


class ImportResult(BaseModel):
    imported: int
    duplicates: int
    invalid: list[InvalidLine]


class DeleteManyRequest(BaseModel):
    ids: list[int]


class InternalProxyResponse(BaseModel):
    id: int
    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None
```

- [ ] **Step 4: Implement proxy service**

```python
# app/services/proxy_service.py
import random
from urllib.parse import urlparse

from sqlmodel import Session, select, col

from app.models.proxy import Proxy, ProxyStatus
from app.schemas.proxy import ImportResult, InvalidLine

VALID_SCHEMES = {"http", "https", "socks5"}
GATEWAY_SCHEMES = {"http", "https"}  # socks5 not supported by gateway in MVP


def parse_proxy_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        parsed = urlparse(line)
    except Exception:
        return None
    if parsed.scheme not in VALID_SCHEMES:
        return None
    if not parsed.hostname or not parsed.port:
        return None
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname,
        "port": parsed.port,
        "username": parsed.username,
        "password": parsed.password,
    }


def import_proxies(session: Session, text: str) -> ImportResult:
    imported = 0
    duplicates = 0
    invalid: list[InvalidLine] = []

    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parsed = parse_proxy_line(line)
        if parsed is None:
            invalid.append(InvalidLine(line=line, reason="Invalid proxy URL format"))
            continue

        existing = session.exec(
            select(Proxy).where(
                Proxy.scheme == parsed["scheme"],
                Proxy.host == parsed["host"],
                Proxy.port == parsed["port"],
            )
        ).first()
        if existing:
            duplicates += 1
            continue

        proxy = Proxy(**parsed)
        session.add(proxy)
        imported += 1

    session.commit()
    return ImportResult(imported=imported, duplicates=duplicates, invalid=invalid)


def select_random_proxy(session: Session) -> Proxy | None:
    proxies = session.exec(
        select(Proxy).where(
            Proxy.status != ProxyStatus.DEAD,
            col(Proxy.scheme).in_(GATEWAY_SCHEMES),
        )
    ).all()
    if not proxies:
        return None
    return random.choice(proxies)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./venv/Scripts/python -m pytest tests/test_proxy_service.py -v`
Expected: PASS (12 tests)

- [ ] **Step 6: Commit**

```bash
git add app/schemas/proxy.py app/services/proxy_service.py tests/test_proxy_service.py
git commit -m "feat: add proxy parse, import, and random selection service"
```

---

### Task 7: Proxy CRUD API

**Files:**
- Create: `app/api/proxies.py`
- Modify: `app/main.py` (add router)
- Test: `tests/test_proxies_api.py`

**Interfaces:**
- Consumes: `get_current_user`, `get_session`, proxy service functions, schemas
- Produces: `/api/proxies` CRUD endpoints

- [ ] **Step 1: Write the failing test**

```python
# tests/test_proxies_api.py
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.user import User
from app.core.security import hash_password


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(engine, client):
    with Session(engine) as session:
        user = User(username="admin", hashed_password=hash_password("admin123"), is_admin=True)
        session.add(user)
        session.commit()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_proxy(client, auth_headers):
    resp = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["host"] == "1.2.3.4"
    assert data["status"] == "unknown"


def test_create_duplicate_proxy(client, auth_headers):
    body = {"scheme": "http", "host": "1.2.3.4", "port": 8080}
    client.post("/api/proxies", json=body, headers=auth_headers)
    resp = client.post("/api/proxies", json=body, headers=auth_headers)
    assert resp.status_code == 409


def test_list_proxies(client, auth_headers):
    client.post("/api/proxies", json={"scheme": "http", "host": "1.1.1.1", "port": 80}, headers=auth_headers)
    client.post("/api/proxies", json={"scheme": "http", "host": "2.2.2.2", "port": 80}, headers=auth_headers)
    resp = client.get("/api/proxies", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_import_proxies(client, auth_headers):
    resp = client.post(
        "/api/proxies/import",
        json={"text": "http://1.1.1.1:80\nhttp://2.2.2.2:80\nbadline"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2
    assert len(data["invalid"]) == 1


def test_delete_proxy(client, auth_headers):
    create = client.post("/api/proxies", json={"scheme": "http", "host": "9.9.9.9", "port": 80}, headers=auth_headers)
    proxy_id = create.json()["id"]
    resp = client.delete(f"/api/proxies/{proxy_id}", headers=auth_headers)
    assert resp.status_code == 204


def test_proxies_require_auth(client):
    resp = client.get("/api/proxies")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python -m pytest tests/test_proxies_api.py -v`
Expected: FAIL — 404 on `/api/proxies` (router not mounted)

- [ ] **Step 3: Implement proxies router**

```python
# app/api/proxies.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select, func, col

from app.core.database import get_session
from app.api.deps import get_current_user
from app.models.proxy import Proxy, ProxyStatus
from app.models.user import User
from app.schemas.proxy import (
    ProxyCreate, ProxyUpdate, ProxyResponse, ProxyListResponse,
    ImportRequest, ImportResult, DeleteManyRequest,
)
from app.services.proxy_service import import_proxies

router = APIRouter(prefix="/api/proxies", tags=["proxies"])


def _proxy_to_response(p: Proxy) -> ProxyResponse:
    return ProxyResponse(
        id=p.id,
        scheme=p.scheme,
        host=p.host,
        port=p.port,
        username=p.username,
        password=p.password,
        status=p.status.value,
        latency_ms=p.latency_ms,
        last_checked_at=p.last_checked_at.isoformat() if p.last_checked_at else None,
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


@router.post("", response_model=ProxyResponse, status_code=status.HTTP_201_CREATED)
def create_proxy(
    body: ProxyCreate,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    existing = session.exec(
        select(Proxy).where(
            Proxy.scheme == body.scheme,
            Proxy.host == body.host,
            Proxy.port == body.port,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proxy already exists")
    proxy = Proxy(**body.model_dump())
    session.add(proxy)
    session.commit()
    session.refresh(proxy)
    return _proxy_to_response(proxy)


@router.get("", response_model=ProxyListResponse)
def list_proxies(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    scheme: str | None = None,
    q: str | None = None,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    query = select(Proxy)
    if status_filter:
        query = query.where(Proxy.status == ProxyStatus(status_filter))
    if scheme:
        query = query.where(Proxy.scheme == scheme)
    if q:
        query = query.where(col(Proxy.host).contains(q))

    total = session.exec(select(func.count()).select_from(query.subquery())).one()
    items = session.exec(query.offset((page - 1) * size).limit(size)).all()

    return ProxyListResponse(
        items=[_proxy_to_response(p) for p in items],
        total=total,
        page=page,
        size=size,
    )


@router.post("/import", response_model=ImportResult)
def import_proxies_endpoint(
    body: ImportRequest,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    return import_proxies(session, body.text)


@router.get("/{proxy_id}", response_model=ProxyResponse)
def get_proxy(
    proxy_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    proxy = session.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
    return _proxy_to_response(proxy)


@router.put("/{proxy_id}", response_model=ProxyResponse)
def update_proxy(
    proxy_id: int,
    body: ProxyUpdate,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    proxy = session.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(proxy, key, value)
    session.add(proxy)
    session.commit()
    session.refresh(proxy)
    return _proxy_to_response(proxy)


@router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proxy(
    proxy_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    proxy = session.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
    session.delete(proxy)
    session.commit()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_many_proxies(
    body: DeleteManyRequest,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    for proxy_id in body.ids:
        proxy = session.get(Proxy, proxy_id)
        if proxy:
            session.delete(proxy)
    session.commit()
```

- [ ] **Step 4: Mount router in main.py**

In `app/main.py`, add the import after the auth router import:
```python
from app.api.proxies import router as proxies_router
```
And inside `create_app()`, after `app.include_router(auth_router)`:
```python
    app.include_router(proxies_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./venv/Scripts/python -m pytest tests/test_proxies_api.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add app/api/proxies.py app/main.py tests/test_proxies_api.py
git commit -m "feat: add proxy CRUD API endpoints"
```

---

### Task 8: Stats + Internal API

**Files:**
- Create: `app/api/stats.py`
- Create: `app/api/internal.py`
- Modify: `app/main.py` (add routers)
- Test: `tests/test_stats_api.py`
- Test: `tests/test_internal_api.py`

**Interfaces:**
- Consumes: `Proxy`, `ProxyStatus`, `select_random_proxy`, `verify_internal_key`
- Produces: `/api/stats/summary`, `/internal/proxies`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_stats_api.py
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.user import User
from app.models.proxy import Proxy, ProxyStatus
from app.core.security import hash_password


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(engine, client):
    with Session(engine) as session:
        user = User(username="admin", hashed_password=hash_password("admin123"), is_admin=True)
        session.add(user)
        session.commit()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_stats_summary(client, auth_headers, engine):
    with Session(engine) as session:
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.ALIVE))
        session.add(Proxy(scheme="http", host="2.2.2.2", port=80, status=ProxyStatus.DEAD))
        session.add(Proxy(scheme="http", host="3.3.3.3", port=80, status=ProxyStatus.UNKNOWN))
        session.commit()

    resp = client.get("/api/stats/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["alive"] == 1
    assert data["dead"] == 1
    assert data["unknown"] == 1
```

```python
# tests/test_internal_api.py
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.proxy import Proxy, ProxyStatus


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


INTERNAL_HEADERS = {"X-Internal-Key": "test-internal-key"}


def test_internal_requires_key(client):
    resp = client.get("/internal/proxies")
    assert resp.status_code == 401


def test_internal_wrong_key(client):
    resp = client.get("/internal/proxies", headers={"X-Internal-Key": "wrong"})
    assert resp.status_code == 401


def test_internal_returns_proxy(client, engine):
    with Session(engine) as session:
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.ALIVE))
        session.commit()

    resp = client.get("/internal/proxies?strategy=random", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["host"] == "1.1.1.1"
    assert data["port"] == 80


def test_internal_excludes_dead(client, engine):
    with Session(engine) as session:
        session.add(Proxy(scheme="http", host="1.1.1.1", port=80, status=ProxyStatus.DEAD))
        session.commit()

    resp = client.get("/internal/proxies?strategy=random", headers=INTERNAL_HEADERS)
    assert resp.status_code == 404


def test_internal_invalid_strategy(client):
    resp = client.get("/internal/proxies?strategy=sticky", headers=INTERNAL_HEADERS)
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/Scripts/python -m pytest tests/test_stats_api.py tests/test_internal_api.py -v`
Expected: FAIL — 404 (routers not mounted)

- [ ] **Step 3: Implement stats router**

```python
# app/api/stats.py
from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func

from app.core.database import get_session
from app.api.deps import get_current_user
from app.models.proxy import Proxy, ProxyStatus
from app.models.user import User

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary")
def stats_summary(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    total = session.exec(select(func.count(Proxy.id))).one()
    alive = session.exec(
        select(func.count(Proxy.id)).where(Proxy.status == ProxyStatus.ALIVE)
    ).one()
    dead = session.exec(
        select(func.count(Proxy.id)).where(Proxy.status == ProxyStatus.DEAD)
    ).one()
    unknown = session.exec(
        select(func.count(Proxy.id)).where(Proxy.status == ProxyStatus.UNKNOWN)
    ).one()
    return {"total": total, "alive": alive, "dead": dead, "unknown": unknown}
```

- [ ] **Step 4: Implement internal router**

```python
# app/api/internal.py
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from sqlmodel import Session

from app.core.database import get_session
from app.api.deps import verify_internal_key
from app.schemas.proxy import InternalProxyResponse
from app.services.proxy_service import select_random_proxy

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/proxies", response_model=InternalProxyResponse)
def get_proxy_for_gateway(
    strategy: str = Query("random"),
    session: Session = Depends(get_session),
    x_internal_key: str = Header(""),
):
    verify_internal_key(x_internal_key)

    if strategy != "random":
        raise HTTPException(status_code=400, detail=f"Unsupported strategy: {strategy}")

    proxy = select_random_proxy(session)
    if proxy is None:
        raise HTTPException(status_code=404, detail="No available proxy")

    return InternalProxyResponse(
        id=proxy.id,
        scheme=proxy.scheme,
        host=proxy.host,
        port=proxy.port,
        username=proxy.username,
        password=proxy.password,
    )
```

- [ ] **Step 5: Mount routers in main.py**

In `app/main.py`, add the imports after the existing router imports:
```python
from app.api.stats import router as stats_router
from app.api.internal import router as internal_router
```
And inside `create_app()`, after `app.include_router(proxies_router)`:
```python
    app.include_router(stats_router)
    app.include_router(internal_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `./venv/Scripts/python -m pytest tests/test_stats_api.py tests/test_internal_api.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Commit**

```bash
git add app/api/stats.py app/api/internal.py app/main.py tests/test_stats_api.py tests/test_internal_api.py
git commit -m "feat: add stats summary and internal proxy selection API"
```

---

### Task 9: CLI (create-admin)

**Files:**
- Create: `app/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `User` model, `hash_password`, `create_db_and_tables`, `engine`
- Produces: `python -m app.cli create-admin --username X --email Y --password Z`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import subprocess
import sys


def test_cli_create_admin_help():
    result = subprocess.run(
        [sys.executable, "-m", "app.cli", "--help"],
        capture_output=True, text=True, cwd=".",
    )
    assert result.returncode == 0
    assert "create-admin" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement CLI**

```python
# app/cli.py
import argparse
import sys

from app.core.database import create_db_and_tables, engine
from app.core.security import hash_password
from app.models.user import User
from sqlmodel import Session, select


def create_admin(args):
    create_db_and_tables()
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == args.username)).first()
        if existing:
            print(f"Error: user '{args.username}' already exists.")
            sys.exit(1)
        user = User(
            username=args.username,
            email=args.email,
            hashed_password=hash_password(args.password),
            is_admin=True,
        )
        session.add(user)
        session.commit()
        print(f"Admin user '{args.username}' created successfully.")


def main():
    parser = argparse.ArgumentParser(prog="proxyhub-cli", description="ProxyHub CLI")
    subparsers = parser.add_subparsers(dest="command")

    admin_parser = subparsers.add_parser("create-admin", help="Create an admin user")
    admin_parser.add_argument("--username", required=True)
    admin_parser.add_argument("--email", default=None)
    admin_parser.add_argument("--password", required=True)

    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/cli.py tests/test_cli.py
git commit -m "feat: add CLI create-admin command"
```

---

### Task 10: Gateway Plugin (RotateProxyPlugin)

**Files:**
- Create: `app/gateway/plugin.py`
- Test: `tests/test_gateway_plugin.py`

**Interfaces:**
- Consumes: `GATEWAY_API_URL`, `INTERNAL_API_KEY` from env
- Produces: `RotateProxyPlugin` class loadable via `proxy --plugins app.gateway.plugin.RotateProxyPlugin`

**Reference:** Based on `proxy.py v2.4.10` built-in `ProxyPoolPlugin` pattern (see `venv/Lib/site-packages/proxy/plugin/proxy_pool.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gateway_plugin.py
import json
from unittest.mock import patch, MagicMock
import pytest

from app.gateway.plugin import RotateProxyPlugin, fetch_proxy_from_api


class TestFetchProxyFromApi:
    @patch("app.gateway.plugin.httpx.get")
    def test_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 1, "scheme": "http", "host": "1.2.3.4",
            "port": 8080, "username": "user", "password": "pass",
        }
        mock_get.return_value = mock_resp

        result = fetch_proxy_from_api("http://localhost:8000/internal/proxies", "key")
        assert result is not None
        assert result.hostname == b"1.2.3.4"
        assert result.port == 8080

    @patch("app.gateway.plugin.httpx.get")
    def test_no_proxy_available(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = fetch_proxy_from_api("http://localhost:8000/internal/proxies", "key")
        assert result is None

    @patch("app.gateway.plugin.httpx.get")
    def test_backend_down(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        result = fetch_proxy_from_api("http://localhost:8000/internal/proxies", "key")
        assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/Scripts/python -m pytest tests/test_gateway_plugin.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the plugin**

```python
# app/gateway/plugin.py
"""RotateProxyPlugin — proxy.py plugin that fetches a proxy from ProxyHub backend per request."""
import base64
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from proxy.http import Url, httpHeaders, httpMethods
from proxy.core.base import TcpUpstreamConnectionHandler
from proxy.http.proxy import HttpProxyBasePlugin
from proxy.http.parser import HttpParser
from proxy.http.exception import HttpProtocolException
from proxy.common.utils import text_, bytes_
from proxy.common.constants import COLON

logger = logging.getLogger(__name__)

GATEWAY_API_URL = os.environ.get("GATEWAY_API_URL", "http://localhost:8000/internal/proxies")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
API_TIMEOUT = 2.0


def fetch_proxy_from_api(api_url: str, api_key: str) -> Optional[Url]:
    """Call the internal API to get one usable proxy. Returns Url or None."""
    try:
        resp = httpx.get(
            api_url,
            params={"strategy": "random"},
            headers={"X-Internal-Key": api_key},
            timeout=API_TIMEOUT,
        )
    except Exception as e:
        logger.error("Failed to reach backend API: %s", e)
        return None

    if resp.status_code != 200:
        logger.warning("Backend returned %d: %s", resp.status_code, resp.text)
        return None

    data = resp.json()
    # Build proxy URL: scheme://[user:pass@]host:port
    auth = ""
    if data.get("username") and data.get("password"):
        auth = f"{data['username']}:{data['password']}@"
    url_str = f"{data['scheme']}://{auth}{data['host']}:{data['port']}"
    return Url.from_bytes(bytes_(url_str))


class RotateProxyPlugin(TcpUpstreamConnectionHandler, HttpProxyBasePlugin):
    """Fetches a random alive proxy from ProxyHub backend for each request."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._endpoint: Optional[Url] = None
        self._metadata: List[Any] = [None, None, None, None]

    def handle_upstream_data(self, raw: memoryview) -> None:
        self.client.queue(raw)

    def before_upstream_connection(self, request: HttpParser) -> Optional[HttpParser]:
        """Fetch proxy from API and connect to it. Return None to skip default upstream."""
        self._endpoint = fetch_proxy_from_api(GATEWAY_API_URL, INTERNAL_API_KEY)
        if self._endpoint is None:
            raise HttpProtocolException("No available proxy from ProxyHub backend")

        assert self._endpoint.hostname and self._endpoint.port
        endpoint_tuple = (text_(self._endpoint.hostname), self._endpoint.port)
        logger.info("Using upstream proxy %s:%s", *endpoint_tuple)

        self.initialize_upstream(*endpoint_tuple)
        assert self.upstream
        try:
            self.upstream.connect()
        except TimeoutError:
            raise HttpProtocolException(
                f"Timed out connecting to upstream proxy {endpoint_tuple[0]}:{endpoint_tuple[1]}"
            )
        except ConnectionRefusedError:
            raise HttpProtocolException(
                f"Connection refused by upstream proxy {endpoint_tuple[0]}:{endpoint_tuple[1]}"
            )
        return None

    def handle_client_request(self, request: HttpParser) -> Optional[HttpParser]:
        """Forward request to upstream proxy, adding Proxy-Authorization if needed."""
        if not self.upstream:
            return request

        # Track metadata for access log
        host, port = None, None
        if request.has_header(b"host"):
            url = Url.from_bytes(request.header(b"host"))
            if url.hostname:
                host = url.hostname.decode("utf-8")
                port = url.port or (443 if request.is_https_tunnel else 80)
        path = None if not request.path else request.path.decode()
        self._metadata = [host, port, path, request.method]

        # Add Proxy-Authorization header if credentials exist
        if self._endpoint and self._endpoint.has_credentials:
            assert self._endpoint.username and self._endpoint.password
            request.add_header(
                httpHeaders.PROXY_AUTHORIZATION,
                b"Basic " + base64.b64encode(
                    self._endpoint.username + COLON + self._endpoint.password
                ),
            )

        self.upstream.queue(memoryview(request.build(for_proxy=True)))
        return request

    def handle_client_data(self, raw: memoryview) -> Optional[memoryview]:
        """Queue client data to upstream proxy."""
        assert self.upstream
        self.upstream.queue(raw)
        return raw

    def handle_upstream_chunk(self, chunk: memoryview) -> Optional[memoryview]:
        """Should never be called since we manage upstream manually."""
        if not self.upstream:
            return chunk
        raise Exception("handle_upstream_chunk should not be called")

    def on_upstream_connection_close(self) -> None:
        if self.upstream and not self.upstream.closed:
            self.upstream.close()
            self.upstream = None

    def on_access_log(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.upstream:
            return context
        addr, port = (self.upstream.addr[0], self.upstream.addr[1])
        context.update({
            "upstream_proxy_host": addr,
            "upstream_proxy_port": port,
            "server_host": self._metadata[0],
            "server_port": self._metadata[1],
            "request_path": self._metadata[2],
            "response_bytes": self.total_size,
        })
        logger.info(
            "%s:%s %s %s:%s%s -> %s:%s",
            context.get("client_ip"), context.get("client_port"),
            self._metadata[3], self._metadata[0], self._metadata[1],
            self._metadata[2] or "", addr, port,
        )
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/Scripts/python -m pytest tests/test_gateway_plugin.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/gateway/plugin.py tests/test_gateway_plugin.py
git commit -m "feat: add RotateProxyPlugin for proxy.py gateway"
```

---

### Task 11: Frontend Scaffold

**Files:**
- Create: `frontend/` (via Vite scaffold)
- Create: `frontend/.env.example`
- Modify: `frontend/package.json` (add deps)
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Scaffold Vite + React + TypeScript**

```bash
cd D:/Source/ponta/proxyhub
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

- [ ] **Step 2: Install dependencies**

```bash
cd D:/Source/ponta/proxyhub/frontend
npm install axios @tanstack/react-query react-router-dom
npm install -D tailwindcss @tailwindcss/vite vitest @testing-library/react @testing-library/jest-dom jsdom
```

- [ ] **Step 3: Create .env.example**

```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

- [ ] **Step 4: Configure Tailwind CSS and Vitest**

Replace `vite.config.ts` with:
```typescript
/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test-setup.ts',
  },
})
```

Add a test script to `frontend/package.json` under `"scripts"`:
```json
"test": "vitest run"
```

Create `src/test-setup.ts`:
```typescript
import '@testing-library/jest-dom'
```

Replace `src/index.css` with:
```css
@import "tailwindcss";
```

- [ ] **Step 5: Verify dev server starts**

```bash
cd D:/Source/ponta/proxyhub/frontend
npm run dev
```
Expected: Vite dev server starts on http://localhost:5173

- [ ] **Step 6: Commit**

```bash
cd D:/Source/ponta/proxyhub
git add frontend/
git commit -m "feat: scaffold React frontend with Vite, Tailwind, and testing setup"
```

---

### Task 12: Frontend Auth (Login + Guard)

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/lib/auth.ts`
- Create: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/App.tsx` (replace)
- Test: `frontend/src/__tests__/auth.test.tsx`

- [ ] **Step 1: Implement API client**

```typescript
// frontend/src/api/client.ts
import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default client
```

- [ ] **Step 2: Implement auth API + lib**

```typescript
// frontend/src/api/auth.ts
import client from './client'

export interface LoginResponse {
  access_token: string
  token_type: string
}

export interface UserResponse {
  id: number
  username: string
  email: string | null
  is_admin: boolean
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const res = await client.post<LoginResponse>('/api/auth/login', { username, password })
  return res.data
}

export async function getMe(): Promise<UserResponse> {
  const res = await client.get<UserResponse>('/api/auth/me')
  return res.data
}
```

```typescript
// frontend/src/lib/auth.ts
export function getToken(): string | null {
  return localStorage.getItem('access_token')
}

export function setToken(token: string): void {
  localStorage.setItem('access_token', token)
}

export function clearToken(): void {
  localStorage.removeItem('access_token')
}

export function isAuthenticated(): boolean {
  return !!getToken()
}
```

- [ ] **Step 3: Implement LoginPage**

```tsx
// frontend/src/pages/LoginPage.tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../api/auth'
import { setToken } from '../lib/auth'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await login(username, password)
      setToken(data.access_token)
      navigate('/')
    } catch {
      setError('Invalid username or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4 rounded-lg border border-zinc-800 p-8">
        <h1 className="text-xl font-bold text-white">ProxyHub Login</h1>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-white"
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-white"
          required
        />
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-blue-600 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>
    </div>
  )
}
```

- [ ] **Step 4: Implement App with router + guard**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { isAuthenticated } from './lib/auth'
import LoginPage from './pages/LoginPage'
import ProxiesPage from './pages/ProxiesPage'

const queryClient = new QueryClient()

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <ProxiesPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
```

- [ ] **Step 5: Create placeholder ProxiesPage**

```tsx
// frontend/src/pages/ProxiesPage.tsx
export default function ProxiesPage() {
  return <div className="p-8 text-white">Proxies (coming in Task 13)</div>
}
```

- [ ] **Step 6: Write auth test**

```tsx
// frontend/src/__tests__/auth.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import LoginPage from '../pages/LoginPage'
import * as authApi from '../api/auth'

vi.mock('../api/auth')

describe('LoginPage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows error on failed login', async () => {
    vi.mocked(authApi.login).mockRejectedValue(new Error('401'))
    render(<MemoryRouter><LoginPage /></MemoryRouter>)

    fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText('Invalid username or password')).toBeInTheDocument()
    })
  })

  it('stores token on successful login', async () => {
    vi.mocked(authApi.login).mockResolvedValue({ access_token: 'tok123', token_type: 'bearer' })
    render(<MemoryRouter><LoginPage /></MemoryRouter>)

    fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'pass' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(localStorage.getItem('access_token')).toBe('tok123')
    })
  })
})
```

- [ ] **Step 7: Run frontend tests**

```bash
cd D:/Source/ponta/proxyhub/frontend
npx vitest run
```
Expected: PASS (2 tests)

- [ ] **Step 8: Commit**

```bash
cd D:/Source/ponta/proxyhub
git add frontend/
git commit -m "feat: add login page, auth guard, and API client"
```

---

### Task 13: Frontend Proxies Page

**Files:**
- Create: `frontend/src/api/proxies.ts`
- Create: `frontend/src/components/StatCards.tsx`
- Create: `frontend/src/components/ProxyTable.tsx`
- Create: `frontend/src/components/ImportDialog.tsx`
- Create: `frontend/src/components/ProxyForm.tsx`
- Modify: `frontend/src/pages/ProxiesPage.tsx`
- Test: `frontend/src/__tests__/proxies.test.tsx`

- [ ] **Step 1: Implement proxies API**

```typescript
// frontend/src/api/proxies.ts
import client from './client'

export interface ProxyItem {
  id: number
  scheme: string
  host: string
  port: number
  username: string | null
  password: string | null
  status: string
  latency_ms: number | null
  last_checked_at: string | null
  created_at: string
  updated_at: string
}

export interface ProxyListResponse {
  items: ProxyItem[]
  total: number
  page: number
  size: number
}

export interface ImportResult {
  imported: number
  duplicates: number
  invalid: { line: string; reason: string }[]
}

export interface StatsSummary {
  total: number
  alive: number
  dead: number
  unknown: number
}

export async function fetchProxies(params?: {
  page?: number; size?: number; status?: string; q?: string
}): Promise<ProxyListResponse> {
  const res = await client.get('/api/proxies', { params })
  return res.data
}

export async function createProxy(data: {
  scheme: string; host: string; port: number; username?: string; password?: string
}): Promise<ProxyItem> {
  const res = await client.post('/api/proxies', data)
  return res.data
}

export async function importProxies(text: string): Promise<ImportResult> {
  const res = await client.post('/api/proxies/import', { text })
  return res.data
}

export async function deleteProxy(id: number): Promise<void> {
  await client.delete(`/api/proxies/${id}`)
}

export async function deleteManyProxies(ids: number[]): Promise<void> {
  await client.delete('/api/proxies', { data: { ids } })
}

export async function fetchStats(): Promise<StatsSummary> {
  const res = await client.get('/api/stats/summary')
  return res.data
}
```

- [ ] **Step 2: Implement StatCards component**

```tsx
// frontend/src/components/StatCards.tsx
import { useQuery } from '@tanstack/react-query'
import { fetchStats } from '../api/proxies'

const cards = [
  { key: 'total', label: 'Total', color: 'text-white' },
  { key: 'alive', label: 'Alive', color: 'text-green-400' },
  { key: 'dead', label: 'Dead', color: 'text-red-400' },
  { key: 'unknown', label: 'Unknown', color: 'text-yellow-400' },
] as const

export default function StatCards() {
  const { data } = useQuery({ queryKey: ['stats'], queryFn: fetchStats })

  return (
    <div className="grid grid-cols-4 gap-4">
      {cards.map((c) => (
        <div key={c.key} className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
          <p className="text-sm text-zinc-400">{c.label}</p>
          <p className={`text-2xl font-bold ${c.color}`}>{data?.[c.key] ?? '—'}</p>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Implement ProxyTable component**

```tsx
// frontend/src/components/ProxyTable.tsx
import { useState } from 'react'
import type { ProxyItem } from '../api/proxies'

const statusColors: Record<string, string> = {
  alive: 'bg-green-900 text-green-300',
  dead: 'bg-red-900 text-red-300',
  unknown: 'bg-yellow-900 text-yellow-300',
}

interface Props {
  proxies: ProxyItem[]
  selected: Set<number>
  onToggleSelect: (id: number) => void
  onToggleSelectAll: () => void
  onDelete: (id: number) => void
}

export default function ProxyTable({ proxies, selected, onToggleSelect, onToggleSelectAll, onDelete }: Props) {
  const [showCreds, setShowCreds] = useState<Set<number>>(new Set())

  const toggleCreds = (id: number) => {
    setShowCreds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="w-full text-sm text-left">
        <thead className="bg-zinc-900 text-zinc-400">
          <tr>
            <th className="p-3">
              <input type="checkbox" onChange={onToggleSelectAll} checked={selected.size === proxies.length && proxies.length > 0} />
            </th>
            <th className="p-3">Scheme</th>
            <th className="p-3">Host:Port</th>
            <th className="p-3">Credentials</th>
            <th className="p-3">Status</th>
            <th className="p-3">Latency</th>
            <th className="p-3">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800">
          {proxies.map((p) => (
            <tr key={p.id} className="hover:bg-zinc-900/50">
              <td className="p-3">
                <input type="checkbox" checked={selected.has(p.id)} onChange={() => onToggleSelect(p.id)} />
              </td>
              <td className="p-3">
                <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs">{p.scheme}</span>
              </td>
              <td className="p-3 font-mono">{p.host}:{p.port}</td>
              <td className="p-3">
                {p.username ? (
                  <button onClick={() => toggleCreds(p.id)} className="text-zinc-400 hover:text-white">
                    {showCreds.has(p.id) ? `${p.username}:•••` : '👁 •••'}
                  </button>
                ) : '—'}
              </td>
              <td className="p-3">
                <span className={`rounded px-2 py-0.5 text-xs ${statusColors[p.status] || ''}`}>
                  {p.status}
                </span>
              </td>
              <td className="p-3">{p.latency_ms != null ? `${p.latency_ms}ms` : '—'}</td>
              <td className="p-3">
                <button onClick={() => onDelete(p.id)} className="text-red-400 hover:text-red-300">
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 4: Implement ImportDialog**

```tsx
// frontend/src/components/ImportDialog.tsx
import { useState } from 'react'
import { importProxies, type ImportResult } from '../api/proxies'

interface Props {
  open: boolean
  onClose: () => void
  onImported: () => void
}

export default function ImportDialog({ open, onClose, onImported }: Props) {
  const [text, setText] = useState('')
  const [result, setResult] = useState<ImportResult | null>(null)
  const [loading, setLoading] = useState(false)

  if (!open) return null

  const handleImport = async () => {
    setLoading(true)
    try {
      const res = await importProxies(text)
      setResult(res)
      onImported()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-lg rounded-lg border border-zinc-700 bg-zinc-900 p-6">
        <h2 className="mb-4 text-lg font-bold text-white">Import Proxies</h2>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"http://user:pass@1.2.3.4:8080\nsocks5://5.6.7.8:1080"}
          className="h-40 w-full rounded border border-zinc-700 bg-zinc-800 p-3 font-mono text-sm text-white"
        />
        {result && (
          <div className="mt-3 text-sm">
            <p className="text-green-400">Imported: {result.imported}</p>
            <p className="text-yellow-400">Duplicates: {result.duplicates}</p>
            {result.invalid.length > 0 && (
              <div className="text-red-400">
                <p>Invalid ({result.invalid.length}):</p>
                {result.invalid.map((inv, i) => (
                  <p key={i} className="ml-2 font-mono text-xs">{inv.line} — {inv.reason}</p>
                ))}
              </div>
            )}
          </div>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="rounded px-4 py-2 text-zinc-400 hover:text-white">Close</button>
          <button
            onClick={handleImport}
            disabled={loading || !text.trim()}
            className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Importing...' : 'Import'}
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Implement ProxyForm dialog**

```tsx
// frontend/src/components/ProxyForm.tsx
import { useState } from 'react'
import { createProxy } from '../api/proxies'

interface Props {
  open: boolean
  onClose: () => void
  onCreated: () => void
}

export default function ProxyForm({ open, onClose, onCreated }: Props) {
  const [scheme, setScheme] = useState('http')
  const [host, setHost] = useState('')
  const [port, setPort] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (!open) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await createProxy({
        scheme,
        host,
        port: parseInt(port),
        username: username || undefined,
        password: password || undefined,
      })
      onCreated()
      onClose()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create proxy')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <form onSubmit={handleSubmit} className="w-full max-w-md space-y-3 rounded-lg border border-zinc-700 bg-zinc-900 p-6">
        <h2 className="text-lg font-bold text-white">Add Proxy</h2>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <select value={scheme} onChange={(e) => setScheme(e.target.value)} className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-white">
          <option value="http">http</option>
          <option value="https">https</option>
          <option value="socks5" disabled>socks5 (not supported via gateway)</option>
        </select>
        <input placeholder="Host (e.g. 1.2.3.4)" value={host} onChange={(e) => setHost(e.target.value)} required className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-white" />
        <input placeholder="Port (e.g. 8080)" value={port} onChange={(e) => setPort(e.target.value)} required type="number" className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-white" />
        <input placeholder="Username (optional)" value={username} onChange={(e) => setUsername(e.target.value)} className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-white" />
        <input placeholder="Password (optional)" value={password} onChange={(e) => setPassword(e.target.value)} type="password" className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-white" />
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded px-4 py-2 text-zinc-400 hover:text-white">Cancel</button>
          <button type="submit" disabled={loading} className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50">
            {loading ? 'Adding...' : 'Add'}
          </button>
        </div>
      </form>
    </div>
  )
}
```

- [ ] **Step 6: Implement ProxiesPage**

```tsx
// frontend/src/pages/ProxiesPage.tsx
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchProxies, deleteProxy, deleteManyProxies } from '../api/proxies'
import StatCards from '../components/StatCards'
import ProxyTable from '../components/ProxyTable'
import ImportDialog from '../components/ImportDialog'
import ProxyForm from '../components/ProxyForm'

export default function ProxiesPage() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [showImport, setShowImport] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const queryClient = useQueryClient()

  const { data } = useQuery({
    queryKey: ['proxies', page, statusFilter, search],
    queryFn: () => fetchProxies({ page, status: statusFilter || undefined, q: search || undefined }),
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['proxies'] })
    queryClient.invalidateQueries({ queryKey: ['stats'] })
  }

  const handleDelete = async (id: number) => {
    await deleteProxy(id)
    setSelected((prev) => { const n = new Set(prev); n.delete(id); return n })
    invalidate()
  }

  const handleDeleteSelected = async () => {
    await deleteManyProxies([...selected])
    setSelected(new Set())
    invalidate()
  }

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (!data) return
    if (selected.size === data.items.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(data.items.map((p) => p.id)))
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-white">ProxyHub</h1>
          <div className="flex gap-2">
            <button onClick={() => setShowForm(true)} className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">Add Proxy</button>
            <button onClick={() => setShowImport(true)} className="rounded bg-zinc-700 px-4 py-2 text-sm text-white hover:bg-zinc-600">Import</button>
            {selected.size > 0 && (
              <button onClick={handleDeleteSelected} className="rounded bg-red-700 px-4 py-2 text-sm text-white hover:bg-red-600">
                Delete ({selected.size})
              </button>
            )}
          </div>
        </div>

        <StatCards />

        <div className="flex gap-3">
          <input
            placeholder="Search host..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            className="rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white"
          />
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
            className="rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white"
          >
            <option value="">All</option>
            <option value="alive">Alive</option>
            <option value="dead">Dead</option>
            <option value="unknown">Unknown</option>
          </select>
        </div>

        {data && (
          <>
            <ProxyTable
              proxies={data.items}
              selected={selected}
              onToggleSelect={toggleSelect}
              onToggleSelectAll={toggleSelectAll}
              onDelete={handleDelete}
            />
            <div className="flex items-center justify-between text-sm text-zinc-400">
              <span>Page {data.page} — {data.total} total</span>
              <div className="flex gap-2">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded border border-zinc-700 px-3 py-1 disabled:opacity-30">Prev</button>
                <button disabled={page * data.size >= data.total} onClick={() => setPage(page + 1)} className="rounded border border-zinc-700 px-3 py-1 disabled:opacity-30">Next</button>
              </div>
            </div>
          </>
        )}
      </div>

      <ImportDialog open={showImport} onClose={() => setShowImport(false)} onImported={invalidate} />
      <ProxyForm open={showForm} onClose={() => setShowForm(false)} onCreated={invalidate} />
    </div>
  )
}
```

- [ ] **Step 7: Write frontend test for ProxyTable**

```tsx
// frontend/src/__tests__/proxies.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ProxyTable from '../components/ProxyTable'
import type { ProxyItem } from '../api/proxies'

const mockProxies: ProxyItem[] = [
  {
    id: 1, scheme: 'http', host: '1.2.3.4', port: 8080,
    username: null, password: null, status: 'alive',
    latency_ms: 120, last_checked_at: null,
    created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
  },
  {
    id: 2, scheme: 'http', host: '5.6.7.8', port: 3128,
    username: 'user', password: 'pass', status: 'dead',
    latency_ms: null, last_checked_at: null,
    created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
  },
]

describe('ProxyTable', () => {
  it('renders proxy rows', () => {
    render(
      <ProxyTable
        proxies={mockProxies}
        selected={new Set()}
        onToggleSelect={() => {}}
        onToggleSelectAll={() => {}}
        onDelete={() => {}}
      />
    )
    expect(screen.getByText('1.2.3.4:8080')).toBeInTheDocument()
    expect(screen.getByText('5.6.7.8:3128')).toBeInTheDocument()
    expect(screen.getByText('alive')).toBeInTheDocument()
    expect(screen.getByText('dead')).toBeInTheDocument()
  })
})
```

- [ ] **Step 8: Run frontend tests**

```bash
cd D:/Source/ponta/proxyhub/frontend
npx vitest run
```
Expected: PASS (3 tests total)

- [ ] **Step 9: Commit**

```bash
cd D:/Source/ponta/proxyhub
git add frontend/
git commit -m "feat: add proxies dashboard with table, import, and stats"
```

---

### Task 14: Integration Test + README Update

**Files:**
- Create: `tests/test_integration.py`
- Modify: `README.md`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
"""Integration test: full flow from API to internal proxy selection."""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.user import User
from app.models.proxy import Proxy, ProxyStatus
from app.core.security import hash_password


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(engine, client):
    with Session(engine) as session:
        user = User(username="admin", hashed_password=hash_password("admin123"), is_admin=True)
        session.add(user)
        session.commit()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


INTERNAL_HEADERS = {"X-Internal-Key": "test-internal-key"}


def test_full_flow(client, auth_headers, engine):
    """Import proxies → verify stats → internal API returns a proxy."""
    # Import
    resp = client.post(
        "/api/proxies/import",
        json={"text": "http://10.0.0.1:8080\nhttp://10.0.0.2:8080"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["imported"] == 2

    # Stats
    resp = client.get("/api/stats/summary", headers=auth_headers)
    assert resp.json()["total"] == 2
    assert resp.json()["unknown"] == 2

    # Internal API picks one
    resp = client.get("/internal/proxies?strategy=random", headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["host"] in ("10.0.0.1", "10.0.0.2")
    assert data["port"] == 8080


def test_dead_proxy_excluded_from_internal(client, auth_headers, engine):
    """Mark all proxies dead → internal API returns 404."""
    with Session(engine) as session:
        session.add(Proxy(scheme="http", host="10.0.0.1", port=80, status=ProxyStatus.DEAD))
        session.commit()

    resp = client.get("/internal/proxies?strategy=random", headers=INTERNAL_HEADERS)
    assert resp.status_code == 404
```

- [ ] **Step 2: Run all tests**

```bash
cd D:/Source/ponta/proxyhub
./venv/Scripts/python -m pytest tests/ -v
```
Expected: ALL PASS

- [ ] **Step 3: Update README**

In `README.md`:
- Remove the WIP banner (replace with a note that MVP is complete)
- Tick the first roadmap item: `- [x] MVP: CRUD Proxy, Manual Rotate, SQLite`
- Fix the gateway command from `--plugin-name` to `--plugins`:

```bash
proxy --plugins app.gateway.plugin.RotateProxyPlugin \
    --hostname 127.0.0.1 \
    --port 8899
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py README.md
git commit -m "feat: add integration tests and update README for MVP completion"
```

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | Project scaffold | — |
| 2 | Config + Database | 2 |
| 3 | Security (JWT + bcrypt) | 3 |
| 4 | Models (User, Proxy) | 3 |
| 5 | Auth API | 4 |
| 6 | Proxy Service | 12 |
| 7 | Proxy CRUD API | 6 |
| 8 | Stats + Internal API | 6 |
| 9 | CLI | 1 |
| 10 | Gateway Plugin | 3 |
| 11 | Frontend scaffold | — |
| 12 | Frontend Auth | 2 |
| 13 | Frontend Proxies | 1 |
| 14 | Integration + README | 2 |
| **Total** | | **45 tests** |
