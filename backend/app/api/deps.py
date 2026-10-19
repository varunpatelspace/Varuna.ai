"""
Authentication and Role-Based Access Control (RBAC) Dependencies.
Enforces multi-tenant data isolation and authorization on every endpoint.
"""

from typing import List, Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.organization import Organization, OrganizationMembership, RoleEnum
from app.utils.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Extracts authentication credentials from Authorization Header or HttpOnly Cookie.
    Validates token signature, expiration, and user active status.
    """
    # Fallback to cookie if Authorization header is absent
    auth_token = token or request.cookies.get("varuna_access_token")
    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(auth_token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive or not found")

    return user


def get_current_membership(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> OrganizationMembership:
    """
    Resolves the user's primary organization membership.
    """
    membership = db.query(OrganizationMembership).filter(
        OrganizationMembership.user_id == user.id
    ).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active organization membership found")

    return membership


class RoleChecker:
    def __init__(self, allowed_roles: List[RoleEnum]):
        self.allowed_roles = allowed_roles

    def __call__(
        self,
        membership: OrganizationMembership = Depends(get_current_membership)
    ) -> OrganizationMembership:
        if membership.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires one of the following roles: {[r.value for r in self.allowed_roles]}"
            )
        return membership


def require_platform_admin(user: User = Depends(get_current_user)) -> User:
    """Restricts access to global platform owner administrators."""
    if not user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to VARUNA AI Platform Administrators"
        )
    return user
