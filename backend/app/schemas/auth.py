"""
Pydantic schemas for authentication, user registration, and profile management.
"""

from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128, description="Minimum 8 characters")
    full_name: str = Field(..., min_length=2, max_length=100)
    organization_name: Optional[str] = Field(default=None, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    organization_id: str
    role: str
    is_platform_admin: bool


class UserProfile(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: Optional[str] = None
    is_active: bool
    is_verified: bool
    is_platform_admin: bool
    organization_id: str
    organization_name: str
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)
