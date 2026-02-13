from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
import stripe
from typing import Optional

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User, UserTier
from app.security.auth import require_user
from app.services.usage_tracker import UsageTracker

router = APIRouter()
stripe.api_key = settings.STRIPE_SECRET_KEY


# Tier pricing mapping
TIER_PRICING = {
    "professional": {
        "price": 19.99,
        "executions": 100,
        "stripe_price_id": settings.STRIPE_PRICE_PROFESSIONAL
    },
    "government": {
        "price": 49.99,
        "executions": 500,
        "stripe_price_id": settings.STRIPE_PRICE_GOVERNMENT
    },
    "enterprise": {
        "price": 99.99,
        "executions": "unlimited",
        "stripe_price_id": settings.STRIPE_PRICE_ENTERPRISE
    }
}


class CreateCheckoutSessionRequest(BaseModel):
    tier: str  # "professional", "government", "enterprise"


class CreateCheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


class ManageSubscriptionResponse(BaseModel):
    portal_url: str


@router.post("/create-checkout-session", response_model=CreateCheckoutSessionResponse)
async def create_checkout_session(
    request: CreateCheckoutSessionRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Create a Stripe checkout session for upgrading to a paid tier"""

    # Validate tier
    if request.tier not in TIER_PRICING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Choose from: {', '.join(TIER_PRICING.keys())}"
        )

    # Check if employee
    if current_user.tier == UserTier.EMPLOYEE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employees get unlimited access - no payment required"
        )

    # Check if already subscribed
    if current_user.stripe_subscription_id and current_user.subscription_status == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an active subscription. Use the customer portal to manage it.",
            headers={"X-Portal-URL": "/api/v1/payments/customer-portal"}
        )

    tier_info = TIER_PRICING[request.tier]

    # Check if Stripe price ID is configured
    if not tier_info["stripe_price_id"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe integration not fully configured. Please run stripe_setup.py"
        )

    try:
        # Create or retrieve Stripe customer
        if current_user.stripe_customer_id:
            customer_id = current_user.stripe_customer_id
        else:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={
                    "user_id": current_user.id,
                    "tier": request.tier
                }
            )
            customer_id = customer.id

            # Save customer ID
            current_user.stripe_customer_id = customer_id
            db.commit()

        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=['card'],
            line_items=[
                {
                    'price': tier_info["stripe_price_id"],
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url='https://mockfactory.io/account?payment=success&session_id={CHECKOUT_SESSION_ID}',
            cancel_url='https://mockfactory.io/pricing?payment=cancelled',
            metadata={
                'user_id': current_user.id,
                'tier': request.tier
            },
            subscription_data={
                'metadata': {
                    'user_id': current_user.id,
                    'tier': request.tier
                }
            }
        )

        return CreateCheckoutSessionResponse(
            checkout_url=checkout_session.url,
            session_id=checkout_session.id
        )

    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment system error: {str(e)}"
        )


@router.get("/customer-portal", response_model=ManageSubscriptionResponse)
async def customer_portal(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Create a Stripe customer portal session for managing subscription"""

    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No subscription found"
        )

    try:
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url='https://mockfactory.io/account'
        )

        return ManageSubscriptionResponse(portal_url=session.url)

    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create portal session: {str(e)}"
        )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle Stripe webhook events"""

    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle different event types
    event_type = event['type']
    data_object = event['data']['object']

    if event_type == 'checkout.session.completed':
        # Payment successful, subscription created
        user_id = data_object.get('metadata', {}).get('user_id')
        tier = data_object.get('metadata', {}).get('tier')
        subscription_id = data_object.get('subscription')

        if user_id and tier:
            user = db.query(User).filter(User.id == int(user_id)).first()
            if user:
                user.tier = UserTier(tier.upper())
                user.stripe_subscription_id = subscription_id
                user.subscription_status = "active"

                # Reset usage for new billing period
                usage_tracker = UsageTracker(db)
                usage_tracker.reset_monthly_usage(user)

                db.commit()

    elif event_type == 'customer.subscription.updated':
        # Subscription status changed
        subscription_id = data_object.get('id')
        status_str = data_object.get('status')

        user = db.query(User).filter(User.stripe_subscription_id == subscription_id).first()
        if user:
            user.subscription_status = status_str

            # If subscription canceled/past_due, downgrade to beginner
            if status_str in ['canceled', 'unpaid', 'past_due']:
                user.tier = UserTier.BEGINNER

            db.commit()

    elif event_type == 'customer.subscription.deleted':
        # Subscription canceled
        subscription_id = data_object.get('id')

        user = db.query(User).filter(User.stripe_subscription_id == subscription_id).first()
        if user:
            user.tier = UserTier.BEGINNER
            user.subscription_status = "canceled"
            db.commit()

    elif event_type == 'invoice.payment_succeeded':
        # Monthly payment successful - reset usage
        subscription_id = data_object.get('subscription')

        user = db.query(User).filter(User.stripe_subscription_id == subscription_id).first()
        if user:
            usage_tracker = UsageTracker(db)
            usage_tracker.reset_monthly_usage(user)

    elif event_type == 'invoice.payment_failed':
        # Payment failed
        subscription_id = data_object.get('subscription')

        user = db.query(User).filter(User.stripe_subscription_id == subscription_id).first()
        if user:
            user.subscription_status = "past_due"
            db.commit()

    return {"status": "success"}


@router.get("/pricing")
async def get_pricing():
    """Get pricing information for all tiers"""
    return {
        "tiers": [
            {
                "id": "anonymous",
                "name": "Anonymous",
                "price": "Free",
                "price_monthly": 0,
                "runs": 5,
                "features": [
                    "5 code executions",
                    "All languages supported",
                    "No account required"
                ],
                "cta": "Try Now"
            },
            {
                "id": "beginner",
                "name": "Beginner",
                "price": "Free",
                "price_monthly": 0,
                "runs": 10,
                "features": [
                    "10 code executions per month",
                    "All languages supported",
                    "Save execution history",
                    "Basic support"
                ],
                "cta": "Sign Up Free"
            },
            {
                "id": "student",
                "name": "Student",
                "price": "Free",
                "price_monthly": 0,
                "runs": 25,
                "features": [
                    "25 code executions per month",
                    "All languages supported",
                    "Perfect for coursework",
                    "Save execution history",
                    "Educational resources",
                    "Priority student support"
                ],
                "cta": "Verify Student Status",
                "note": "Requires student email or verification"
            },
            {
                "id": "professional",
                "name": "Professional",
                "price": "$19.99/month",
                "price_monthly": 19.99,
                "runs": 100,
                "features": [
                    "100 code executions per month",
                    "All languages supported",
                    "Priority support",
                    "Extended execution time (60s)",
                    "Increased memory (512MB)",
                    "API access",
                    "Execution history",
                    "Cancel anytime"
                ],
                "cta": "Start Free Trial",
                "popular": True
            },
            {
                "id": "government",
                "name": "Government",
                "price": "$49.99/month",
                "price_monthly": 49.99,
                "runs": 500,
                "features": [
                    "500 code executions per month",
                    "All languages supported",
                    "Dedicated support",
                    "Extended execution time (120s)",
                    "Increased memory (1GB)",
                    "API access",
                    "Compliance reporting",
                    "SLA guarantee",
                    "Priority processing"
                ],
                "cta": "Contact Sales"
            },
            {
                "id": "enterprise",
                "name": "Enterprise",
                "price": "$99.99/month",
                "price_monthly": 99.99,
                "runs": "Unlimited",
                "features": [
                    "Unlimited code executions",
                    "All languages supported",
                    "24/7 premium support",
                    "Extended execution time (300s)",
                    "Increased memory (2GB)",
                    "API access",
                    "Compliance reporting",
                    "SLA guarantee",
                    "Custom integrations",
                    "Dedicated account manager"
                ],
                "cta": "Contact Sales"
            },
            {
                "id": "custom",
                "name": "Custom",
                "price": "Contact Us",
                "price_monthly": None,
                "runs": "Custom",
                "features": [
                    "Custom execution limits",
                    "All languages supported",
                    "White-label options",
                    "Custom deployment",
                    "Dedicated infrastructure",
                    "Custom SLA",
                    "24/7 premium support",
                    "On-premise options",
                    "Tailored to your needs"
                ],
                "cta": "Contact Sales"
            },
            {
                "id": "employee",
                "name": "After Dark Employee",
                "price": "Free",
                "price_monthly": 0,
                "runs": "Unlimited",
                "features": [
                    "Unlimited executions",
                    "All languages supported",
                    "Premium support",
                    "Extended resources",
                    "Priority processing"
                ],
                "cta": "SSO Login",
                "note": "For After Dark Systems employees only"
            }
        ]
    }


@router.get("/my-subscription")
async def get_my_subscription(
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Get current user's subscription information"""

    usage_tracker = UsageTracker(db)
    usage_info = usage_tracker.get_remaining_runs(current_user, "")

    subscription_info = {
        "tier": current_user.tier.value,
        "usage": usage_info,
        "has_subscription": bool(current_user.stripe_subscription_id),
        "subscription_status": current_user.subscription_status,
    }

    # Get Stripe subscription details if exists
    if current_user.stripe_subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(current_user.stripe_subscription_id)
            subscription_info["current_period_end"] = subscription.current_period_end
            subscription_info["cancel_at_period_end"] = subscription.cancel_at_period_end
        except:
            pass

    return subscription_info
