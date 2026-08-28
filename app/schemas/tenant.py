from pydantic import BaseModel


class TenantCreate(BaseModel):
    name: str
    slug: str | None = None


class TenantResponse(BaseModel):
    id: int
    name: str
    slug: str
    created_at: str


class MembershipCreate(BaseModel):
    user_id: int
    role: str = "member"


class MembershipResponse(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    role: str
