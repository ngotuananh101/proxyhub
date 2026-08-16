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
    default_target_url: str | None = None
