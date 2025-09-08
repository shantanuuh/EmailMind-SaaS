
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from ..dependencies import get_current_user, get_db
from ..models.user import User
from ..models.subscription import Subscription
from ..services.payment_service import payment_service
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

class SubscriptionCreate(BaseModel):
    plan_type: str  # starter, professional, enterprise
    billing_cycle: str = "monthly"  # monthly, yearly

class PaymentMethodCreate(BaseModel):
    token: str
    type: str = "card"

class BillingAddressUpdate(BaseModel):
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str

@router.get("/plans")
async def get_subscription_plans():
    """Get available subscription plans"""
    return {
        "plans": [
            {
                "id": "starter",
                "name": "Starter",
                "description": "Perfect for individuals getting started with email analytics",
                "price_monthly": 9.00,
                "price_yearly": 90.00,
                "features": [
                    "10,000 emails per month",
                    "Basic analytics",
                    "Email categorization",
                    "Sentiment analysis",
                    "Email support"
                ],
                "limits": {
                    "emails_per_month": 10000,
                    "ai_insights": 5,
                    "export_formats": ["CSV"],
                    "api_calls": 1000
                }
            },
            {
                "id": "professional",
                "name": "Professional", 
                "description": "For professionals who need advanced insights and automation",
                "price_monthly": 29.00,
                "price_yearly": 290.00,
                "features": [
                    "100,000 emails per month",
                    "Advanced AI insights",
                    "Importance scoring",
                    "Smart unsubscribe recommendations",
                    "Executive summaries",
                    "Priority support"
                ],
                "limits": {
                    "emails_per_month": 100000,
                    "ai_insights": 50,
                    "export_formats": ["CSV", "JSON", "PDF"],
                    "api_calls": 10000
                }
            },
            {
                "id": "enterprise",
                "name": "Enterprise",
                "description": "For teams and organizations requiring unlimited access",
                "price_monthly": 99.00,
                "price_yearly": 990.00,
                "features": [
                    "Unlimited emails",
                    "Custom AI models",
                    "Advanced analytics",
                    "Team collaboration",
                    "White-label options",
                    "Dedicated support"
                ],
                "limits": {
                    "emails_per_month": -1,  # Unlimited
                    "ai_insights": -1,
                    "export_formats": ["CSV", "JSON", "PDF", "Excel"],
                    "api_calls": -1
                }
            }
        ]
    }

@router.get("/current")
async def get_current_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's subscription details"""
    try:
        subscription = db.query(Subscription).filter(
            Subscription.user_id == current_user.id,
            Subscription.status == "active"
        ).first()
        
        if not subscription:
            return {
                "subscription": None,
                "plan": "free",
                "status": "inactive"
            }
        
        return {
            "subscription": {
                "id": subscription.id,
                "plan_type": subscription.plan_type,
                "status": subscription.status,
                "billing_cycle": subscription.billing_cycle,
                "current_period_start": subscription.current_period_start.isoformat(),
                "current_period_end": subscription.current_period_end.isoformat(),
                "cancel_at_period_end": subscription.cancel_at_period_end
            },
            "usage": await payment_service.get_usage_stats(current_user.id),
            "plan": subscription.plan_type,
            "status": subscription.status
        }
        
    except Exception as e:
        logger.error(f"Failed to get subscription: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve subscription")

@router.post("/create")
async def create_subscription(
    subscription_data: SubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new subscription"""
    try:
        # Check if user already has active subscription
        existing = db.query(Subscription).filter(
            Subscription.user_id == current_user.id,
            Subscription.status == "active"
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400, 
                detail="User already has an active subscription"
            )
        
        # Create subscription through payment service
        result = await payment_service.create_subscription(
            user_id=current_user.id,
            plan_type=subscription_data.plan_type,
            billing_cycle=subscription_data.billing_cycle
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to create subscription")
            )
        
        return {
            "success": True,
            "subscription": result["subscription"],
            "client_secret": result.get("client_secret"),
            "message": "Subscription created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Subscription creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create subscription")

@router.post("/payment-method")
async def add_payment_method(
    payment_data: PaymentMethodCreate,
    current_user: User = Depends(get_current_user)
):
    """Add payment method for user"""
    try:
        result = await payment_service.add_payment_method(
            user_id=current_user.id,
            payment_token=payment_data.token,
            payment_type=payment_data.type
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to add payment method")
            )
        
        return {
            "success": True,
            "payment_method": result["payment_method"],
            "message": "Payment method added successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Adding payment method failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to add payment method")

@router.put("/change-plan")
async def change_subscription_plan(
    plan_data: SubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change subscription plan"""
    try:
        subscription = db.query(Subscription).filter(
            Subscription.user_id == current_user.id,
            Subscription.status == "active"
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="No active subscription found"
            )
        
        result = await payment_service.change_subscription_plan(
            subscription_id=subscription.id,
            new_plan=plan_data.plan_type,
            billing_cycle=plan_data.billing_cycle
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to change plan")
            )
        
        return {
            "success": True,
            "subscription": result["subscription"],
            "message": "Plan changed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Plan change failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to change plan")

@router.post("/cancel")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel subscription"""
    try:
        subscription = db.query(Subscription).filter(
            Subscription.user_id == current_user.id,
            Subscription.status == "active"
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="No active subscription found"
            )
        
        result = await payment_service.cancel_subscription(subscription.id)
        
        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to cancel subscription")
            )
        
        return {
            "success": True,
            "message": "Subscription will be canceled at the end of current period",
            "cancellation_date": result.get("cancellation_date")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Subscription cancellation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel subscription")

@router.post("/reactivate")
async def reactivate_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reactivate canceled subscription"""
    try:
        subscription = db.query(Subscription).filter(
            Subscription.user_id == current_user.id,
            Subscription.cancel_at_period_end == True
        ).first()
        
        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="No canceled subscription found"
            )
        
        result = await payment_service.reactivate_subscription(subscription.id)
        
        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to reactivate subscription")
            )
        
        return {
            "success": True,
            "subscription": result["subscription"],
            "message": "Subscription reactivated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Subscription reactivation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to reactivate subscription")

@router.get("/usage")
async def get_usage_stats(
    current_user: User = Depends(get_current_user)
):
    """Get current usage statistics"""
    try:
        usage = await payment_service.get_usage_stats(current_user.id)
        return {
            "success": True,
            "usage": usage
        }
        
    except Exception as e:
        logger.error(f"Failed to get usage stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve usage statistics")

@router.get("/billing-history")
async def get_billing_history(
    current_user: User = Depends(get_current_user),
    limit: int = 10
):
    """Get billing history"""
    try:
        history = await payment_service.get_billing_history(current_user.id, limit)
        return {
            "success": True,
            "billing_history": history
        }
        
    except Exception as e:
        logger.error(f"Failed to get billing history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve billing history")

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhooks"""
    try:
        payload = await request.body()
        sig_header = request.headers.get('stripe-signature')
        
        result = await payment_service.handle_webhook(payload, sig_header)
        
        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Webhook processing failed")
            )
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")

@router.put("/billing-address")
async def update_billing_address(
    address_data: BillingAddressUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update billing address"""
    try:
        result = await payment_service.update_billing_address(
            current_user.id,
            address_data.dict()
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to update billing address")
            )
        
        return {
            "success": True,
            "message": "Billing address updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Billing address update failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to update billing address")
