import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import get_active_tenant_id, get_current_user, require_tenant_role
from app.core.database import get_session
from app.core.datetime_utils import utc_isoformat
from app.core.security import hash_password
from app.models.credential import AuthMode, GatewayCredential
from app.models.tenant import TenantRole
from app.models.user import User
from app.schemas.credential import (
    GatewayCredentialCreate,
    GatewayCredentialCreatedResponse,
    GatewayCredentialListResponse,
    GatewayCredentialResponse,
    GatewayCredentialUpdate,
)
from app.services.gateway_auth_service import clear_auth_cache, validate_cidrs

router = APIRouter(prefix="/api/gateway-credentials", tags=["gateway-credentials"])


def _to_response(cred: GatewayCredential) -> GatewayCredentialResponse:
    return GatewayCredentialResponse(
        id=cred.id,
        tenant_id=cred.tenant_id,
        name=cred.name,
        auth_mode=cred.auth_mode,
        username=cred.username,
        cidrs=cred.cidrs,
        is_active=cred.is_active,
        last_used_at=utc_isoformat(cred.last_used_at) if cred.last_used_at else None,
        created_at=utc_isoformat(cred.created_at),
    )


@router.get("", response_model=GatewayCredentialListResponse)
def list_credentials(
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_active_tenant_id),
    session: Session = Depends(get_session),
):
    """List all credentials for the active tenant."""
    query = (
        select(GatewayCredential)
        .where(GatewayCredential.tenant_id == tenant_id)
        .order_by(GatewayCredential.created_at.desc())
    )
    creds = session.exec(query).all()
    return GatewayCredentialListResponse(
        items=[_to_response(c) for c in creds],
        total=len(creds),
    )


@router.post("", response_model=GatewayCredentialCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_credential(
    body: GatewayCredentialCreate,
    current_user: User = Depends(require_tenant_role(TenantRole.ADMIN)),
    tenant_id: int = Depends(get_active_tenant_id),
    session: Session = Depends(get_session),
):
    """Create a new gateway credential. Server generates password for Basic auth."""
    generated_pw = None
    pw_hash = None
    normalized_cidrs = None

    if body.auth_mode == AuthMode.BASIC:
        if not body.username or not body.username.strip():
            raise HTTPException(status_code=422, detail="Username is required for Basic auth")
        username = body.username.strip()

        # Check unique username per tenant
        existing = session.exec(
            select(GatewayCredential).where(
                GatewayCredential.tenant_id == tenant_id,
                GatewayCredential.auth_mode == AuthMode.BASIC,
                GatewayCredential.username == username,
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{username}' already exists for this tenant",
            )

        generated_pw = secrets.token_urlsafe(16)
        pw_hash = hash_password(generated_pw)
    elif body.auth_mode == AuthMode.IP_WHITELIST:
        if not body.cidrs or not body.cidrs.strip():
            raise HTTPException(status_code=422, detail="CIDR list is required for IP whitelist")
        try:
            normalized_cidrs = validate_cidrs(body.cidrs)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        if not normalized_cidrs:
            raise HTTPException(status_code=422, detail="At least one valid CIDR or IP is required")
        username = None
    else:
        raise HTTPException(status_code=422, detail=f"Invalid auth_mode: {body.auth_mode}")

    cred = GatewayCredential(
        tenant_id=tenant_id,
        name=body.name,
        auth_mode=body.auth_mode,
        username=username,
        password_hash=pw_hash,
        cidrs=normalized_cidrs,
        is_active=True,
    )
    session.add(cred)
    session.commit()
    session.refresh(cred)

    resp = _to_response(cred)
    return GatewayCredentialCreatedResponse(
        **resp.model_dump(),
        generated_password=generated_pw,
    )


@router.patch("/{credential_id}", response_model=GatewayCredentialCreatedResponse)
def update_credential(
    credential_id: int,
    body: GatewayCredentialUpdate,
    current_user: User = Depends(require_tenant_role(TenantRole.ADMIN)),
    tenant_id: int = Depends(get_active_tenant_id),
    session: Session = Depends(get_session),
):
    """Update credential name, active status, CIDRs, or rotate password."""
    cred = session.get(GatewayCredential, credential_id)
    if not cred or cred.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Credential not found")

    generated_pw = None
    if body.name is not None:
        s = body.name.strip()
        if not s:
            raise HTTPException(status_code=422, detail="Name cannot be empty")
        cred.name = s

    if body.is_active is not None:
        cred.is_active = body.is_active
        clear_auth_cache()

    if body.cidrs is not None:
        if cred.auth_mode != AuthMode.IP_WHITELIST:
            raise HTTPException(status_code=422, detail="Cannot set CIDRs on basic auth credential")
        try:
            cred.cidrs = validate_cidrs(body.cidrs)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    if body.rotate_password:
        if cred.auth_mode != AuthMode.BASIC:
            raise HTTPException(status_code=422, detail="Cannot rotate password on IP whitelist credential")
        generated_pw = secrets.token_urlsafe(16)
        cred.password_hash = hash_password(generated_pw)
        clear_auth_cache()

    session.add(cred)
    session.commit()
    session.refresh(cred)

    resp = _to_response(cred)
    return GatewayCredentialCreatedResponse(
        **resp.model_dump(),
        generated_password=generated_pw,
    )


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(
    credential_id: int,
    current_user: User = Depends(require_tenant_role(TenantRole.ADMIN)),
    tenant_id: int = Depends(get_active_tenant_id),
    session: Session = Depends(get_session),
):
    """Delete credential. Existing logs keep auth_credential_id (SET NULL)."""
    cred = session.get(GatewayCredential, credential_id)
    if not cred or cred.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Credential not found")

    session.delete(cred)
    session.commit()
    clear_auth_cache()
