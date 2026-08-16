from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import get_current_admin, get_current_user
from app.core.database import get_session
from app.core.settings_registry import REGISTRY
from app.models.user import User
from app.services import settings_service
from app.services.settings_service import SettingValidationError

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    values: dict[str, str]


@router.get("")
def get_settings(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    values = settings_service.get_all(session)
    return {
        "items": [
            {
                "key": defn.key,
                "label": defn.label,
                "description": defn.description,
                "type": defn.type,
                "default": defn.default,
                "min": defn.min,
                "max": defn.max,
                "value": values[defn.key],
            }
            for defn in REGISTRY.values()
        ]
    }


@router.put("")
def update_settings(
    body: SettingsUpdate,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    try:
        values = settings_service.update(session, body.values)
    except SettingValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"values": values}
