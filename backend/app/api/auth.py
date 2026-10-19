"""
Authentication Router.
Handles user registration, login with HttpOnly secure cookie issuance,
session inspection, and secure logout.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database import get_db
from app.models.user import User, UserPreference
from app.models.organization import Organization, OrganizationMembership, RoleEnum
from app.models.billing import Subscription, SubscriptionStatus
from app.models.audit import AuditLog
from app.schemas.auth import UserRegister, UserLogin, TokenResponse, UserProfile, PasswordResetRequest, PasswordResetConfirm
from app.utils.security import hash_password, verify_password, create_access_token
from app.services.payment_service import PaymentService
from app.services.credit_engine import CreditEngine
from app.api.deps import get_current_user, get_current_membership
from app.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse)
def register(
    data: UserRegister,
    response: Response,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Registers a new user, provisions their primary organization,
    assigns the default Free plan, and allocates complimentary AI credits.
    """
    # Check if email is already taken
    existing_user = db.query(User).filter(User.email == data.email.lower().strip()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists"
        )

    # Ensure plans are seeded
    PaymentService.seed_plans(db)

    # 1. Create User
    # In dev or first user check: if email is admin@varuna.ai, grant platform admin
    is_admin = (data.email.lower() == "admin@varuna.ai")
    user = User(
        email=data.email.lower().strip(),
        hashed_password=hash_password(data.password),
        full_name=data.full_name.strip(),
        is_active=True,
        is_verified=True,
        is_platform_admin=is_admin
    )
    db.add(user)
    db.flush()

    # 2. Create User Preferences
    pref = UserPreference(user_id=user.id)
    db.add(pref)

    # 3. Create Primary Organization
    org_name = data.organization_name.strip() if data.organization_name else f"{data.full_name.strip()}'s Workspace"
    org_slug = f"{org_name.lower().replace(' ', '-')[:30]}-{user.id[:6]}"
    organization = Organization(
        name=org_name,
        slug=org_slug,
        billing_email=user.email
    )
    db.add(organization)
    db.flush()

    # 4. Create Organization Membership (as ORG_OWNER)
    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=organization.id,
        role=RoleEnum.ORG_OWNER
    )
    db.add(membership)

    # 5. Assign Free Plan Subscription
    free_plan = PaymentService.get_plan_by_tier(db, "FREE")
    if free_plan:
        sub = Subscription(
            organization_id=organization.id,
            plan_id=free_plan.id,
            status=SubscriptionStatus.ACTIVE,
            billing_period="monthly",
            current_period_end=datetime.now(timezone.utc)
        )
        db.add(sub)

    # 6. Initialize Credit Account & Welcome credits
    CreditEngine.get_or_create_account(db, organization.id)

    # 7. Audit log
    audit = AuditLog(
        organization_id=organization.id,
        user_id=user.id,
        action="AUTH_REGISTER",
        resource_type="User",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None
    )
    db.add(audit)
    db.commit()

    # Create Access Token
    token = create_access_token({
        "sub": user.id,
        "email": user.email,
        "org_id": organization.id,
        "role": RoleEnum.ORG_OWNER.value,
        "is_admin": is_admin
    })

    # Set secure HttpOnly cookie
    response.set_cookie(
        key="varuna_access_token",
        value=token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=settings.ENVIRONMENT != "development"
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        organization_id=organization.id,
        role=RoleEnum.ORG_OWNER.value,
        is_platform_admin=is_admin
    )


@router.post("/login", response_model=TokenResponse)
def login(
    data: UserLogin,
    response: Response,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Authenticates user, verifies password, and sets HttpOnly cookie.
    """
    user = db.query(User).filter(User.email == data.email.lower().strip()).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    # Find organization membership
    membership = db.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).first()
    org_id = membership.organization_id if membership else ""
    role_str = membership.role.value if membership else RoleEnum.MEMBER.value

    # Issue token
    token = create_access_token({
        "sub": user.id,
        "email": user.email,
        "org_id": org_id,
        "role": role_str,
        "is_admin": user.is_platform_admin
    })

    response.set_cookie(
        key="varuna_access_token",
        value=token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=settings.ENVIRONMENT != "development"
    )

    audit = AuditLog(
        organization_id=org_id,
        user_id=user.id,
        action="AUTH_LOGIN",
        resource_type="User",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None
    )
    db.add(audit)
    db.commit()

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        organization_id=org_id,
        role=role_str,
        is_platform_admin=user.is_platform_admin
    )


@router.get("/me", response_model=UserProfile)
def get_current_profile(
    user: User = Depends(get_current_user),
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db)
):
    """Returns profile for currently authenticated user."""
    org = db.query(Organization).filter(Organization.id == membership.organization_id).first()
    return UserProfile(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_platform_admin=user.is_platform_admin,
        organization_id=membership.organization_id,
        organization_name=org.name if org else "Default Org",
        role=membership.role.value,
        created_at=user.created_at
    )


@router.post("/logout")
def logout(response: Response):
    """Clears authentication session cookies."""
    response.delete_cookie(key="varuna_access_token")
    return {"message": "Logged out successfully"}
