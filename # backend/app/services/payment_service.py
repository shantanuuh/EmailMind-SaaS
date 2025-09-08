"""
Payment Service - Stripe Integration for Subscription Management
"""
from typing import Dict, List, Optional, Any
import stripe
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.core.config import settings
from app.models.user import User
from app.models.subscription import Subscription, SubscriptionTier, PaymentStatus
from app.core.database import get_db

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

class PaymentService:
    def __init__(self, db: Session):
        self.db = db
    
    async def create_customer(self, user: User, email: str) -> str:
        """Create a Stripe customer for the user"""
        try:
            customer = stripe.Customer.create(
                email=email,
                name=f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else email,
                metadata={
                    'user_id': str(user.id),
                    'created_via': 'emailmind_saas'
                }
            )
            
            # Update user with Stripe customer ID
            user.stripe_customer_id = customer.id
            self.db.commit()
            
            return customer.id
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Failed to create customer: {str(e)}")
    
    async def create_subscription(
        self, 
        user: User, 
        tier: SubscriptionTier, 
        payment_method_id: str
    ) -> Dict[str, Any]:
        """Create a new subscription"""
        try:
            # Ensure user has a Stripe customer ID
            if not user.stripe_customer_id:
                await self.create_customer(user, user.email)
            
            # Get price ID for the tier
            price_id = self._get_price_id_for_tier(tier)
            
            # Attach payment method to customer
            stripe.PaymentMethod.attach(
                payment_method_id,
                customer=user.stripe_customer_id,
            )
            
            # Set as default payment method
            stripe.Customer.modify(
                user.stripe_customer_id,
                invoice_settings={
                    'default_payment_method': payment_method_id,
                },
            )
            
            # Create subscription
            subscription = stripe.Subscription.create(
                customer=user.stripe_customer_id,
                items=[{'price': price_id}],
                payment_behavior='default_incomplete',
                payment_settings={'save_default_payment_method': 'on_subscription'},
                expand=['latest_invoice.payment_intent'],
                metadata={
                    'user_id': str(user.id),
                    'tier': tier.value
                }
            )
            
            # Create local subscription record
            local_subscription = Subscription(
                user_id=user.id,
                stripe_subscription_id=subscription.id,
                tier=tier,
                status=PaymentStatus.INCOMPLETE,
                current_period_start=datetime.fromtimestamp(
                    subscription.current_period_start, tz=timezone.utc
                ),
                current_period_end=datetime.fromtimestamp(
                    subscription.current_period_end, tz=timezone.utc
                ),
                created_at=datetime.now(timezone.utc)
            )
            
            self.db.add(local_subscription)
            self.db.commit()
            
            return {
                'subscription_id': subscription.id,
                'client_secret': subscription.latest_invoice.payment_intent.client_secret,
                'status': subscription.status
            }
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Failed to create subscription: {str(e)}")
    
    async def update_subscription_tier(
        self, 
        subscription: Subscription, 
        new_tier: SubscriptionTier
    ) -> Dict[str, Any]:
        """Update subscription to a different tier"""
        try:
            stripe_subscription = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
            
            # Get new price ID
            new_price_id = self._get_price_id_for_tier(new_tier)
            
            # Update subscription
            updated_subscription = stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                items=[{
                    'id': stripe_subscription['items']['data'][0].id,
                    'price': new_price_id,
                }],
                proration_behavior='immediate_with_remaining_time'
            )
            
            # Update local record
            subscription.tier = new_tier
            subscription.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            
            return {
                'subscription_id': updated_subscription.id,
                'status': updated_subscription.status,
                'tier': new_tier.value
            }
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Failed to update subscription: {str(e)}")
    
    async def cancel_subscription(self, subscription: Subscription) -> Dict[str, Any]:
        """Cancel a subscription"""
        try:
            # Cancel at period end to allow user to continue until billing cycle ends
            canceled_subscription = stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=True
            )
            
            # Update local record
            subscription.status = PaymentStatus.CANCELED
            subscription.cancel_at_period_end = True
            subscription.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            
            return {
                'subscription_id': canceled_subscription.id,
                'status': 'canceled',
                'cancel_at_period_end': canceled_subscription.cancel_at_period_end,
                'current_period_end': canceled_subscription.current_period_end
            }
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Failed to cancel subscription: {str(e)}")
    
    async def reactivate_subscription(self, subscription: Subscription) -> Dict[str, Any]:
        """Reactivate a canceled subscription"""
        try:
            reactivated_subscription = stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=False
            )
            
            # Update local record
            subscription.status = PaymentStatus.ACTIVE
            subscription.cancel_at_period_end = False
            subscription.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            
            return {
                'subscription_id': reactivated_subscription.id,
                'status': 'active'
            }
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Failed to reactivate subscription: {str(e)}")
    
    async def get_payment_methods(self, user: User) -> List[Dict[str, Any]]:
        """Get customer's payment methods"""
        try:
            if not user.stripe_customer_id:
                return []
            
            payment_methods = stripe.PaymentMethod.list(
                customer=user.stripe_customer_id,
                type="card",
            )
            
            return [
                {
                    'id': pm.id,
                    'brand': pm.card.brand,
                    'last4': pm.card.last4,
                    'exp_month': pm.card.exp_month,
                    'exp_year': pm.card.exp_year
                }
                for pm in payment_methods.data
            ]
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Failed to retrieve payment methods: {str(e)}")
    
    async def add_payment_method(
        self, 
        user: User, 
        payment_method_id: str, 
        set_default: bool = False
    ) -> Dict[str, Any]:
        """Add a new payment method"""
        try:
            if not user.stripe_customer_id:
                await self.create_customer(user, user.email)
            
            # Attach payment method
            stripe.PaymentMethod.attach(
                payment_method_id,
                customer=user.stripe_customer_id,
            )
            
            # Set as default if requested
            if set_default:
                stripe.Customer.modify(
                    user.stripe_customer_id,
                    invoice_settings={
                        'default_payment_method': payment_method_id,
                    },
                )
            
            # Retrieve payment method details
            payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
            
            return {
                'id': payment_method.id,
                'brand': payment_method.card.brand,
                'last4': payment_method.card.last4,
                'exp_month': payment_method.card.exp_month,
                'exp_year': payment_method.card.exp_year
            }
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Failed to add payment method: {str(e)}")
    
    async def remove_payment_method(self, payment_method_id: str) -> bool:
        """Remove a payment method"""
        try:
            stripe.PaymentMethod.detach(payment_method_id)
            return True
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Failed to remove payment method: {str(e)}")
    
    async def get_billing_history(self, user: User, limit: int = 10) -> List[Dict[str, Any]]:
        """Get billing history for a customer"""
        try:
            if not user.stripe_customer_id:
                return []
            
            invoices = stripe.Invoice.list(
                customer=user.stripe_customer_id,
                limit=limit
            )
            
            return [
                {
                    'id': invoice.id,
                    'amount_paid': invoice.amount_paid / 100,  # Convert from cents
                    'currency': invoice.currency,
                    'status': invoice.status,
                    'created': datetime.fromtimestamp(invoice.created, tz=timezone.utc),
                    'period_start': datetime.fromtimestamp(invoice.period_start, tz=timezone.utc) if invoice.period_start else None,
                    'period_end': datetime.fromtimestamp(invoice.period_end, tz=timezone.utc) if invoice.period_end else None,
                    'invoice_pdf': invoice.invoice_pdf
                }
                for invoice in invoices.data
            ]
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Failed to retrieve billing history: {str(e)}")
    
    async def handle_webhook_event(self, event: Dict[str, Any]) -> bool:
        """Handle Stripe webhook events"""
        try:
            event_type = event['type']
            data = event['data']['object']
            
            if event_type == 'customer.subscription.updated':
                await self._handle_subscription_updated(data)
            elif event_type == 'customer.subscription.deleted':
                await self._handle_subscription_deleted(data)
            elif event_type == 'invoice.payment_succeeded':
                await self._handle_payment_succeeded(data)
            elif event_type == 'invoice.payment_failed':
                await self._handle_payment_failed(data)
            
            return True
            
        except Exception as e:
            print(f"Webhook handling error: {str(e)}")
            return False
    
    def _get_price_id_for_tier(self, tier: SubscriptionTier) -> str:
        """Get Stripe price ID for subscription tier"""
        price_mapping = {
            SubscriptionTier.STARTER: settings.STRIPE_STARTER_PRICE_ID,
            SubscriptionTier.PROFESSIONAL: settings.STRIPE_PROFESSIONAL_PRICE_ID,
            SubscriptionTier.ENTERPRISE: settings.STRIPE_ENTERPRISE_PRICE_ID
        }
        return price_mapping.get(tier)
    
    async def _handle_subscription_updated(self, subscription_data: Dict[str, Any]):
        """Handle subscription update webhook"""
        subscription = self.db.query(Subscription).filter(
            Subscription.stripe_subscription_id == subscription_data['id']
        ).first()
        
        if subscription:
            subscription.status = PaymentStatus(subscription_data['status'])
            subscription.current_period_start = datetime.fromtimestamp(
                subscription_data['current_period_start'], tz=timezone.utc
            )
            subscription.current_period_end = datetime.fromtimestamp(
                subscription_data['current_period_end'], tz=timezone.utc
            )
            subscription.updated_at = datetime.now(timezone.utc)
            self.db.commit()
    
    async def _handle_subscription_deleted(self, subscription_data: Dict[str, Any]):
        """Handle subscription deletion webhook"""
        subscription = self.db.query(Subscription).filter(
            Subscription.stripe_subscription_id == subscription_data['id']
        ).first()
        
        if subscription:
            subscription.status = PaymentStatus.CANCELED
            subscription.canceled_at = datetime.now(timezone.utc)
            self.db.commit()
    
    async def _handle_payment_succeeded(self, invoice_data: Dict[str, Any]):
        """Handle successful payment webhook"""
        if invoice_data.get('subscription'):
            subscription = self.db.query(Subscription).filter(
                Subscription.stripe_subscription_id == invoice_data['subscription']
            ).first()
            
            if subscription:
                subscription.status = PaymentStatus.ACTIVE
                subscription.updated_at = datetime.now(timezone.utc)
                self.db.commit()
    
    async def _handle_payment_failed(self, invoice_data: Dict[str, Any]):
        """Handle failed payment webhook"""
        if invoice_data.get('subscription'):
            subscription = self.db.query(Subscription).filter(
                Subscription.stripe_subscription_id == invoice_data['subscription']
            ).first()
            
            if subscription:
                subscription.status = PaymentStatus.PAST_DUE
                subscription.updated_at = datetime.now(timezone.utc)
                self.db.commit()


def get_payment_service(db: Session = None) -> PaymentService:
    """Dependency to get payment service instance"""
    if db is None:
        db = next(get_db())
    return PaymentService(db)
