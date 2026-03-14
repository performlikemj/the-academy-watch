"""Stripe configuration and initialization"""
import os
import stripe
import dotenv
from typing import Optional

dotenv.load_dotenv(dotenv.find_dotenv())

# Load Stripe API keys from environment
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

# Platform fee percentage (10% for The Academy Watch maintenance and operational costs)
PLATFORM_FEE_PERCENT = int(os.getenv('STRIPE_PLATFORM_FEE_PERCENT', '10'))

# Initialize Stripe
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    print("WARNING: STRIPE_SECRET_KEY not set in environment variables")


def get_stripe_keys() -> dict:
    """Get Stripe API keys"""
    return {
        'secret_key': STRIPE_SECRET_KEY,
        'publishable_key': STRIPE_PUBLISHABLE_KEY,
        'webhook_secret': STRIPE_WEBHOOK_SECRET,
        'platform_fee_percent': PLATFORM_FEE_PERCENT
    }


def calculate_platform_fee(amount_cents: int) -> int:
    """Calculate platform fee based on subscription amount
    
    Args:
        amount_cents: Subscription amount in cents
        
    Returns:
        Platform fee in cents (10% of amount)
    """
    return int(amount_cents * PLATFORM_FEE_PERCENT / 100)


def validate_stripe_config() -> tuple[bool, Optional[str]]:
    """Validate that Stripe is properly configured
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not STRIPE_SECRET_KEY:
        return False, "STRIPE_SECRET_KEY not configured"
    
    if not STRIPE_PUBLISHABLE_KEY:
        return False, "STRIPE_PUBLISHABLE_KEY not configured"
    
    if not STRIPE_WEBHOOK_SECRET:
        return False, "STRIPE_WEBHOOK_SECRET not configured (required for webhook verification)"
    
    # Test API key validity
    try:
        stripe.Account.retrieve()
        return True, None
    except stripe.error.AuthenticationError:
        return False, "Invalid Stripe API key"
    except Exception as e:
        return False, f"Error validating Stripe configuration: {str(e)}"
