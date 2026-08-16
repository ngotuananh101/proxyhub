from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, pattern=r"^https?://")
    enabled: bool = True
    interval_minutes: int = Field(default=60, ge=1, le=10080)


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = Field(default=None, min_length=1, pattern=r"^https?://")
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=10080)


class SourceResponse(BaseModel):
    id: int
    name: str
    url: str
    enabled: bool
    interval_minutes: int
    last_fetched_at: str | None = None
    last_status: str | None = None
    created_at: str
