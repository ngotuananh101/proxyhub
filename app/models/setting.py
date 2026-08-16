from typing import Optional

from sqlmodel import Field, SQLModel


class AppSetting(SQLModel, table=True):
    __tablename__ = "appsettings"

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value: str
