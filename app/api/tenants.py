from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import get_current_admin
from app.core.database import get_session
from app.core.datetime_utils import utc_isoformat
from app.models.tenant import Tenant, TenantMembership, TenantRole
from app.models.user import User
from app.schemas.tenant import (
    MembershipCreate,
    MembershipResponse,
    TenantCreate,
    TenantResponse,
)

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


def _to_tenant_response(t: Tenant) -> TenantResponse:
    return TenantResponse(
        id=t.id,
        name=t.name,
        slug=t.slug,
        created_at=utc_isoformat(t.created_at),
    )


def _to_membership_response(m: TenantMembership) -> MembershipResponse:
    return MembershipResponse(
        id=m.id,
        tenant_id=m.tenant_id,
        user_id=m.user_id,
        role=m.role,
    )


@router.get("", response_model=list[TenantResponse])
def list_tenants(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    return [_to_tenant_response(t) for t in session.exec(select(Tenant)).all()]


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    body: TenantCreate,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    slug = body.slug or body.name.lower().replace(" ", "-")
    existing = session.exec(select(Tenant).where(Tenant.slug == slug)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Tenant slug already exists")
    tenant = Tenant(name=body.name, slug=slug)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return _to_tenant_response(tenant)


@router.get("/{tenant_id}/members", response_model=list[MembershipResponse])
def list_members(
    tenant_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    return [
        _to_membership_response(m)
        for m in session.exec(
            select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
        ).all()
    ]


@router.post("/{tenant_id}/members", response_model=MembershipResponse, status_code=status.HTTP_201_CREATED)
def add_member(
    tenant_id: int,
    body: MembershipCreate,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    if body.role not in (TenantRole.ADMIN, TenantRole.MEMBER):
        raise HTTPException(status_code=422, detail="role must be admin or member")
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    existing = session.exec(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == body.user_id,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="User already in tenant")
    membership = TenantMembership(
        tenant_id=tenant_id, user_id=body.user_id, role=body.role
    )
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return _to_membership_response(membership)


@router.delete("/{tenant_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    tenant_id: int,
    user_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    membership = session.exec(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")
    session.delete(membership)
    session.commit()
