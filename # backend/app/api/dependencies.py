# backend/app/api/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.database import get_db
from ..core.security import verify_token
from ..models.user import User
import redis

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user"""
    try:
        user_id = verify_token(credentials.credentials)
        result = await db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        return user
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

async def check_subscription_limits(
    current_user: User = Depends(get_current_active_user)
):
    """Check if user is within subscription limits"""
    # Implementation for subscription limit checking
    subscription_limits = {
        "free_trial": {"emails": 1000, "api_calls": 100},
        "starter": {"emails": 10000, "api_calls": 1000},
        "professional": {"emails": 100000, "api_calls": 10000},
        "enterprise": {"emails": -1, "api_calls": -1}  # Unlimited
    }
    
    limits = subscription_limits.get(current_user.subscription_tier.value, subscription_limits["free_trial"])
    
    if limits["emails"] != -1 and current_user.emails_processed >= limits["emails"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Email processing limit exceeded for your subscription tier"
        )
    
    if limits["api_calls"] != -1 and current_user.api_calls_this_month >= limits["api_calls"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="API call limit exceeded for your subscription tier"
        )
    
    return current_user
