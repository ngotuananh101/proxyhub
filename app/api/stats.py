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
