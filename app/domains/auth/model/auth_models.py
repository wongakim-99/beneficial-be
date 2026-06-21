from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

UserRole = Literal["student", "teacher", "developer"]


class User(BaseModel):
    user_id: str = Field(..., description="Stable user identifier")
    email: str = Field(..., description="Unique login email")
    password_hash: str = Field(..., description="PBKDF2 password hash")
    display_name: str = Field(..., description="Name shown in the learning UI")
    role: UserRole = Field(default="student")
    school_name: Optional[str] = Field(default=None, description="School or organization name (teacher only)")
    created_at: datetime
    updated_at: datetime


class RefreshTokenSession(BaseModel):
    session_id: str
    user_id: str
    refresh_token_hash: str
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    created_at: datetime
