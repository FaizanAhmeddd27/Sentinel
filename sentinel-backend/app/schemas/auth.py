from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID
from app.models.user import UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: Optional[str]
    avatar_url: Optional[str]
    role: UserRole
    is_first_login: bool

    model_config = {"from_attributes": True}


class AuthCallbackResponse(BaseModel):
    user: UserResponse
    message: str