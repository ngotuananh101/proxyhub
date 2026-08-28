import hmac

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from app.core.config import settings
from app.core.database import get_session
from app.core.security import decode_access_token
from app.models.tenant import TenantMembership
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
        user_id = int(payload.get("sub", 0))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user


def verify_internal_key(x_internal_key: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_internal_key, settings.INTERNAL_API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal key")


def get_active_tenant_id(
    current_user: User = Depends(get_current_user),
    x_tenant_id: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> int:
    from app.services.tenant_service import ensure_default_tenant

    memberships = session.exec(
        select(TenantMembership).where(TenantMembership.user_id == current_user.id)
    ).all()

    requested = None
    if x_tenant_id is not None:
        try:
            requested = int(x_tenant_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid tenant id")

    # Super admin may access any tenant, even without membership.
    if current_user.is_admin:
        if requested is not None:
            return requested
        if memberships:
            return memberships[0].tenant_id
        return ensure_default_tenant(session).id

    if not memberships:
        raise HTTPException(status_code=403, detail="No tenant membership")

    if requested is not None:
        if any(m.tenant_id == requested for m in memberships):
            return requested
        raise HTTPException(status_code=403, detail="Not a member of this tenant")

    return memberships[0].tenant_id


def require_tenant_role(min_role: str):
    def dependency(
        current_user: User = Depends(get_current_user),
        x_tenant_id: str | None = Header(default=None),
        session: Session = Depends(get_session),
    ) -> User:
        if current_user.is_admin:
            return current_user
        tenant_id = get_active_tenant_id(
            current_user=current_user,
            x_tenant_id=x_tenant_id,
            session=session,
        )
        m = session.exec(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == current_user.id,
            )
        ).first()
        if m is None or m.role != min_role:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return current_user
    return dependency
