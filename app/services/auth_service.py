from sqlmodel import Session, select

from app.core.security import create_access_token, verify_password
from app.models.user import User


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    user = session.exec(select(User).where(User.username == username)).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_token_for_user(user: User) -> str:
    return create_access_token({"sub": str(user.id)})
