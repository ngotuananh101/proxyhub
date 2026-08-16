from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import get_current_admin, get_current_user
from app.core.database import get_session
from app.core.datetime_utils import utc_isoformat
from app.models.source import ProxySource
from app.models.user import User
from app.schemas.source import SourceCreate, SourceResponse, SourceUpdate
from app.services.settings_service import get_all as get_settings
from app.services.source_service import fetch_and_import

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _to_response(s: ProxySource) -> SourceResponse:
    return SourceResponse(
        id=s.id,
        name=s.name,
        url=s.url,
        enabled=s.enabled,
        interval_minutes=s.interval_minutes,
        last_fetched_at=utc_isoformat(s.last_fetched_at) if s.last_fetched_at else None,
        last_status=s.last_status,
        created_at=utc_isoformat(s.created_at),
    )


@router.get("", response_model=list[SourceResponse])
def list_sources(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    return [_to_response(s) for s in session.exec(select(ProxySource)).all()]


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(
    body: SourceCreate,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    source = ProxySource(**body.model_dump())
    session.add(source)
    session.commit()
    session.refresh(source)
    return _to_response(source)


@router.put("/{source_id}", response_model=SourceResponse)
def update_source(
    source_id: int,
    body: SourceUpdate,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    source = session.get(ProxySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(source, key, value)
    session.add(source)
    session.commit()
    session.refresh(source)
    return _to_response(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    source_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    source = session.get(ProxySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    session.delete(source)
    session.commit()


@router.post("/{source_id}/fetch", status_code=status.HTTP_202_ACCEPTED)
def fetch_source_now(
    source_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    source = session.get(ProxySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    values = get_settings(session)
    status_msg = fetch_and_import(
        session,
        source,
        timeout=float(values["SOURCE_FETCH_TIMEOUT"]),
        retention_days=float(values["DEAD_PROXY_RETENTION_DAYS"]),
    )
    return {"detail": "Fetch completed", "status": status_msg}
