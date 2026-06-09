from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class AuthToken(SQLModel, table=True):
    __tablename__ = "auth_tokens"

    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(unique=True, index=True)
    user_id: int = Field(foreign_key="users.id")
    issued_at: datetime
    expires_at: Optional[datetime] = Field(default=None)
    revoked: bool = Field(default=False)
