from pydantic import BaseModel, Field


class ProxyCreate(BaseModel):
    scheme: str
    host: str
    port: int = Field(ge=1, le=65535)
    username: str | None = None
    password: str | None = None


class ProxyUpdate(BaseModel):
    scheme: str | None = None
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    status: str | None = None


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
    default_target_url: str | None = None
