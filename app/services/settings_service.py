from sqlmodel import Session, select

from app.core.datetime_utils import is_valid_timezone
from app.core.settings_registry import REGISTRY, SettingDef
from app.models.setting import AppSetting


class SettingValidationError(ValueError):
    pass


def _parse(defn: SettingDef, raw: str) -> str | int | float:
    if defn.type == "int":
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise SettingValidationError(f"{defn.key}: expected an integer")
    elif defn.type == "float":
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise SettingValidationError(f"{defn.key}: expected a number")
    else:
        value = str(raw).strip()
        if not value:
            raise SettingValidationError(f"{defn.key}: must not be empty")
        if defn.key == "TIMEZONE" and not is_valid_timezone(value):
            raise SettingValidationError(
                f"{defn.key}: unknown IANA timezone '{value}'"
            )
        return value

    if defn.min is not None and value < defn.min:
        raise SettingValidationError(f"{defn.key}: must be at least {defn.min:g}")
    if defn.max is not None and value > defn.max:
        raise SettingValidationError(f"{defn.key}: must be at most {defn.max:g}")
    return value


def seed_settings(session: Session) -> None:
    """Insert registry defaults for any key not yet stored. Idempotent."""
    for defn in REGISTRY.values():
        existing = session.exec(select(AppSetting).where(AppSetting.key == defn.key)).first()
        if existing is None:
            session.add(AppSetting(key=defn.key, value=str(defn.default)))
    session.commit()


def get_all(session: Session) -> dict[str, str | int | float]:
    """Current value for every registry key (stored value or default)."""
    stored = {
        s.key: s.value
        for s in session.exec(select(AppSetting).where(AppSetting.key.in_(REGISTRY.keys()))).all()
    }
    values: dict[str, str | int | float] = {}
    for key, defn in REGISTRY.items():
        raw = stored.get(key, str(defn.default))
        try:
            values[key] = _parse(defn, raw)
        except SettingValidationError:
            # A value that no longer validates falls back to its default
            values[key] = defn.default
    return values


def update(session: Session, updates: dict[str, str]) -> dict[str, str | int | float]:
    """Validate and persist a batch of updates; returns all current values."""
    parsed: dict[str, str | int | float] = {}
    for key, raw in updates.items():
        defn = REGISTRY.get(key)
        if defn is None:
            raise SettingValidationError(f"Unknown setting: {key}")
        parsed[key] = _parse(defn, raw)

    for key, value in parsed.items():
        row = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
        if row is None:
            row = AppSetting(key=key, value="")
        row.value = str(value)
        session.add(row)
    session.commit()

    return get_all(session)
