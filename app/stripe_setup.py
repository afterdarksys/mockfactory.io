"""
Stripe Product and Price Setup for MockFactory
Run this script once to create products and prices in Stripe
"""
import stripe
from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


def setup_stripe_products():
    """Create all MockFactory tier products and prices in Stripe"""

    tiers = [
        {
            "name": "Beginner",
            "description": "Perfect for trying out MockFactory",
            "executions": 10,
            "price_monthly": 0,  # Free
            "features": [
                "10 code executions per month",
                "All languages supported",
                "Basic support",
                "Save execution history"
            ]
        },
        {
            "name": "Student",
            "description": "Ideal for students and coursework",
            "executions": 25,
            "price_monthly": 0,  # Free with verification
            "features": [
                "25 code executions per month",
                "All languages supported",
                "Priority student support",
                "Save execution history",
                "Educational resources"
            ]
        },
        {
            "name": "Professional",
            "description": "For developers and small teams",
            "executions": 100,
            "price_monthly": 19.99,
            "features": [
                "100 code executions per month",
                "All languages supported",
                "Priority support",
                "Extended execution time (60s)",
                "Increased memory (512MB)",
                "API access"
            ]
        },
        {
            "name": "Government",
            "description": "For government agencies and public sector",
            "executions": 500,
            "price_monthly": 49.99,
            "features": [
                "500 code executions per month",
                "All languages supported",
                "Dedicated support",
                "Extended execution time (120s)",
                "Increased memory (1GB)",
                "API access",
                "Compliance reporting",
                "SLA guarantee"
            ]
        },
        {
            "name": "Enterprise",
            "description": "For large organizations",
            "executions": -1,  # Unlimited
            "price_monthly": 99.99,
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
            ]
        },
        {
            "name": "Custom",
            "description": "Tailored solutions for specific needs",
            "executions": -1,  # Custom
            "price_monthly": None,  # Contact sales
            "features": [
                "Custom execution limits",
                "All languages supported",
                "White-label options",
                "Custom deployment",
                "Dedicated infrastructure",
                "Custom SLA",
                "24/7 premium support",
                "On-premise options"
            ]
        }
    ]

    created_products = []

    for tier in tiers:
        print(f"\n{'='*60}")
        print(f"Creating: {tier['name']}")
        print(f"{'='*60}")

        try:
            # Create product
            product = stripe.Product.create(
                name=f"MockFactory {tier['name']}",
                description=tier['description'],
                metadata={
                    "tier": tier['name'].lower(),
                    "executions": str(tier['executions']),
                    "features": "|".join(tier['features'])
                }
            )

            print(f"✓ Product created: {product.id}")

            # Create price (if not custom/contact sales)
            if tier['price_monthly'] is not None:
                if tier['price_monthly'] == 0:
                    # Free tier - no price needed in Stripe
                    print(f"✓ Free tier - no price object needed")
                    price_id = None
                else:
                    price = stripe.Price.create(
                        product=product.id,
                        unit_amount=int(tier['price_monthly'] * 100),  # Convert to cents
                        currency='usd',
                        recurring={
                            'interval': 'month',
                            'interval_count': 1
                        },
                        metadata={
                            "tier": tier['name'].lower(),
                            "executions": str(tier['executions'])
                        }
                    )
                    price_id = price.id
                    print(f"✓ Price created: {price_id} (${tier['price_monthly']}/month)")
            else:
                # Custom tier - contact sales
                print(f"✓ Custom tier - contact sales for pricing")
                price_id = None

            created_products.append({
                "tier": tier['name'],
                "product_id": product.id,
                "price_id": price_id,
                "amount": tier['price_monthly'],
                "executions": tier['executions']
            })

        except stripe.error.StripeError as e:
            print(f"✗ Error creating {tier['name']}: {str(e)}")

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY - Add these to your .env file:")
    print(f"{'='*60}\n")

    for product in created_products:
        tier_upper = product['tier'].upper()
        print(f"# {product['tier']}")
        print(f"STRIPE_PRODUCT_{tier_upper}={product['product_id']}")
        if product['price_id']:
            print(f"STRIPE_PRICE_{tier_upper}={product['price_id']}")
        print()

    return created_products


if __name__ == "__main__":
    print("MockFactory Stripe Setup")
    print("="*60)
    print("This will create products and prices in Stripe")
    print("Make sure STRIPE_SECRET_KEY is set in your .env file")
    print("="*60)

    response = input("\nContinue? (y/n): ")
    if response.lower() == 'y':
        results = setup_stripe_products()
        print(f"\n✓ Created {len(results)} products in Stripe")
    else:
        print("Cancelled")
