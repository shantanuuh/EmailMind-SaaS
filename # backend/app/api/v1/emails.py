# backend/app/api/v1/emails.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from ...core.database import get_db
from ...models.user import User
from ...models.email import Email, EmailAccount
from ..dependencies import get_current_active_user, check_subscription_limits

router = APIRouter(prefix="/emails")

class EmailAccountCreate(BaseModel):
    provider: str
    email_address: str
    display_name: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None

class EmailResponse(BaseModel):
    id: int
    subject: str
    sender_email: str
    sender_name: Optional[str]
    snippet: str
    sent_date: datetime
    is_read: bool
    ai_category: Optional[str]
    ai_importance_score: Optional[float]
    ai_sentiment: Optional[str]

class EmailDetailResponse(BaseModel):
    id: int
    subject: str
    sender_email: str
    sender_name: Optional[str]
    recipient_emails: List[str]
    body_text: str
    body_html: Optional[str]
    sent_date: datetime
    received_date: datetime
    is_read: bool
    labels: List[str]
    ai_category: Optional[str]
    ai_importance_score: Optional[float]
    ai_sentiment: Optional[str]
    ai_summary: Optional[str]
    ai_action_items: List[dict]

@router.post("/accounts")
async def add_email_account(
    account_data: EmailAccountCreate,
    current_user: User = Depends(check_subscription_limits),
    db: AsyncSession = Depends(get_db)
):
    """Add a new email account"""
    new_account = EmailAccount(
        user_id=current_user.id,
        provider=account_data.provider,
        email_address=account_data.email_address,
        display_name=account_data.display_name,
        access_token=account_data.access_token,
        refresh_token=account_data.refresh_token
    )
    
    db.add(new_account)
    await db.commit()
    await db.refresh(new_account)
    
    return {"message": "Email account added successfully", "account_id": new_account.id}

@router.get("/accounts")
async def get_email_accounts(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's email accounts"""
    result = await db.execute(
        select(EmailAccount).where(EmailAccount.user_id == current_user.id)
    )
    accounts = result.scalars().all()
    return accounts

@router.get("/", response_model=List[EmailResponse])
async def get_emails(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, le=100),
    category: Optional[str] = Query(None),
    importance_min: Optional[float] = Query(None, ge=0, le=1),
    unread_only: bool = Query(False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's emails with filtering"""
    query = select(Email).join(EmailAccount).where(
        EmailAccount.user_id == current_user.id
    )
    
    # Apply filters
    if category:
        query = query.where(Email.ai_category == category)
    
    if importance_min:
        query = query.where(Email.ai_importance_score >= importance_min)
    
    if unread_only:
        query = query.where(Email.is_read == False)
    
    # Order by received date (newest first)
    query = query.order_by(desc(Email.received_date)).offset(skip).limit(limit)
    
    result = await db.execute(query)
    emails = result.scalars().all()
    
    return [EmailResponse(
        id=email.id,
        subject=email.subject or "",
        sender_email=email.sender_email or "",
        sender_name=email.sender_name,
        snippet=email.snippet or "",
        sent_date=email.sent_date,
        is_read=email.is_read,
        ai_category=email.ai_category,
        ai_importance_score=email.ai_importance_score,
        ai_sentiment=email.ai_sentiment
    ) for email in emails]

@router.get("/{email_id}", response_model=EmailDetailResponse)
async def get_email_detail(
    email_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed email information"""
    result = await db.execute(
        select(Email)
        .join(EmailAccount)
        .where(
            and_(
                Email.id == email_id,
                EmailAccount.user_id == current_user.id
            )
        )
        .options(selectinload(Email.attachments))
    )
    email = result.scalar_one_or_none()
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )
    
    # Mark as read
    if not email.is_read:
        email.is_read = True
        await db.commit()
    
    return EmailDetailResponse(
        id=email.id,
        subject=email.subject or "",
        sender_email=email.sender_email or "",
        sender_name=email.sender_name,
        recipient_emails=email.recipient_emails or [],
        body_text=email.body_text or "",
        body_html=email.body_html,
        sent_date=email.sent_date,
        received_date=email.received_date,
        is_read=email.is_read,
        labels=email.labels or [],
        ai_category=email.ai_category,
        ai_importance_score=email.ai_importance_score,
        ai_sentiment=email.ai_sentiment,
        ai_summary=email.ai_summary,
        ai_action_items=email.ai_action_items or []
    )

@router.post("/{email_id}/actions/{action}")
async def perform_email_action(
    email_id: int,
    action: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Perform actions on email (archive, delete, mark as important)"""
    result = await db.execute(
        select(Email)
        .join(EmailAccount)
        .where(
            and_(
                Email.id == email_id,
                EmailAccount.user_id == current_user.id
            )
        )
    )
    email = result.scalar_one_or_none()
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )
    
    if action == "mark_read":
        email.is_read = True
    elif action == "mark_unread":
        email.is_read = False
    elif action == "mark_important":
        email.importance = "high"
    elif action == "archive":
        # Add archive logic here
        pass
    elif action == "delete":
        # Add delete logic here
        pass
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid action"
        )
    
    await db.commit()
    return {"message": f"Action '{action}' performed successfully"}

@router.get("/stats/overview")
async def get_email_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get email statistics overview"""
    # Total emails
    total_result = await db.execute(
        select(func.count(Email.id))
        .join(EmailAccount)
        .where(EmailAccount.user_id == current_user.id)
    )
    total_emails = total_result.scalar()
    
    # Unread emails
    unread_result = await db.execute(
        select(func.count(Email.id))
        .join(EmailAccount)
        .where(
            and_(
                EmailAccount.user_id == current_user.id,
                Email.is_read == False
            )
        )
    )
    unread_emails = unread_result.scalar()
    
    # This week's emails
    week_ago = datetime.utcnow() - timedelta(days=7)
    week_result = await db.execute(
        select(func.count(Email.id))
        .join(EmailAccount)
        .where(
            and_(
                EmailAccount.user_id == current_user.id,
                Email.received_date >= week_ago
            )
        )
    )
    this_week_emails = week_result.scalar()
    
    return {
        "total_emails": total_emails,
        "unread_emails": unread_emails,
        "this_week_emails": this_week_emails,
        "read_rate": (total_emails - unread_emails) / max(total_emails, 1) * 100
    }
