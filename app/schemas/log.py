from pydantic import BaseModel


class RequestLogResponse(BaseModel):
    id: int
    client_ip: str | None = None
    method: str | None = None
    host: str | None = None
    path: str | None = None
    proxy_host: str | None = None
    proxy_port: int | None = None
    response_bytes: int | None = None
    created_at: str


class RequestLogListResponse(BaseModel):
    items: list[RequestLogResponse]
    total: int
    page: int
    size: int
