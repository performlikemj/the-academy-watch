# Stripe Subscription Setup Guide

This guide walks you through setting up and testing the Stripe subscription system for The Academy Watch.

## Overview

The system uses **Stripe Connect Express** to enable journalists to receive subscription payments directly. The Academy Watch acts as the platform and takes a 10% fee for maintenance and operational costs.

## Architecture

- **Platform Account**: The Academy Watch's main Stripe account
- **Connected Accounts**: Each journalist gets a Stripe Express account
- **Revenue Split**: 90% to journalist, 10% to The Academy Watch
- **Pricing**: Journalists set their own subscription prices (free-form)

## Setup Steps

### 1. Create Stripe Account

1. Go to https://stripe.com and create an account
2. This will be the **Platform Account** for The Academy Watch
3. Complete business verification (required for Connect)

### 2. Get API Keys

1. Go to https://dashboard.stripe.com/apikeys
2. Copy your **Publishable key** (starts with `pk_test_`)
3. Copy your **Secret key** (starts with `sk_test_`)
4. Keep these secure!

### 3. Configure Backend

1. Copy `.env.stripe.template` to your `.env` file:
   ```bash
   cd loan-army-backend
   cat .env.stripe.template >> .env
   ```

2. Fill in the Stripe keys:
   ```env
   STRIPE_SECRET_KEY=sk_test_your_key_here
   STRIPE_PUBLISHABLE_KEY=pk_test_your_key_here
   STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret
   STRIPE_PLATFORM_FEE_PERCENT=10
   ```

### 4. Configure Frontend

1. Create/update `.env.local`:
   ```bash
   cd loan-army-frontend
   cat .env.stripe.template >> .env.local
   ```

2. Fill in the publishable key:
   ```env
   VITE_STRIPE_PUBLISHABLE_KEY=pk_test_your_key_here
   VITE_API_URL=http://localhost:5001/api
   ```

### 5. Run Database Migration

```bash
cd loan-army-backend
flask db upgrade
```

This creates the necessary Stripe tables:
- `stripe_connected_accounts`
- `stripe_subscription_plans`
- `stripe_subscriptions`
- `stripe_platform_revenue`

### 6. Install Dependencies

Backend:
```bash
cd loan-army-backend
pip install -r requirements.txt
```

Frontend:
```bash
# From the repository root: scans first and restores only when needed
./scripts/setup_frontend.sh
```

### 7. Set Up Webhooks

Webhooks are essential for syncing Stripe events with your database.

#### For Local Development (using Stripe CLI):

1. Install Stripe CLI: https://stripe.com/docs/stripe-cli
2. Login to Stripe:
   ```bash
   stripe login
   ```
3. Forward webhooks to your local server:
   ```bash
   stripe listen --forward-to localhost:5001/api/stripe/webhook
   ```
4. Copy the webhook signing secret (starts with `whsec_`) to your `.env` file

#### For Production:

1. Go to https://dashboard.stripe.com/webhooks
2. Click "Add endpoint"
3. Enter your webhook URL: `https://your-domain.com/api/stripe/webhook`
4. Select events to listen for:
   - `account.updated`
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
5. Copy the webhook signing secret to your `.env` file

### 8. Start the Application

Backend:
```bash
cd loan-army-backend
python src/main.py
```

Frontend:
```bash
cd loan-army-frontend
pnpm dev
```

## Testing the Flow

### A. Journalist Onboarding

1. **Create a journalist account**:
   - Use the admin panel or API to mark a user as a journalist
   - Set `is_journalist=True` for the user

2. **Access Stripe setup**:
   - Navigate to `/journalist/stripe-setup`
   - Click "Create Stripe Account"
   - Complete the Stripe Connect onboarding form
   - Return to the app

3. **Verify onboarding**:
   - Check that all statuses show green checkmarks
   - Click "Open Stripe Dashboard" to view the Express dashboard

### B. Setting Subscription Price

1. **Navigate to pricing page**:
   - Go to `/journalist/pricing`
   - Enter a monthly price (e.g., $9.99)
   - Review the revenue breakdown showing the 90/10 split
   - Click "Set Price"

2. **Verify price creation**:
   - Refresh the page to see the current price
   - Check Stripe dashboard for the created product/price

### C. Subscriber Flow

1. **Subscribe to a journalist**:
   - Navigate to `/journalists/{id}` (journalist profile)
   - Click "Subscribe Now"
   - You'll be redirected to Stripe Checkout
   - Enter test card: `4242 4242 4242 4242`
   - Use any future expiry date and any CVC
   - Complete the checkout

2. **Verify subscription**:
   - You'll be redirected back to `/subscriptions?success=true`
   - See your active subscription listed
   - Check Stripe dashboard for the subscription

### D. Testing Stripe Test Cards

Use these test cards for different scenarios:

- **Success**: `4242 4242 4242 4242`
- **Decline**: `4000 0000 0000 0002`
- **Requires authentication**: `4000 0025 0000 3155`
- **Insufficient funds**: `4000 0000 0000 9995`

More test cards: https://stripe.com/docs/testing

### E. Subscription Management

1. **Cancel subscription**:
   - Go to `/subscriptions`
   - Click "Cancel Subscription"
   - Verify it's set to cancel at period end

2. **Reactivate subscription**:
   - Click "Reactivate Subscription"
   - Verify the cancellation is removed

### F. Admin Revenue Dashboard

1. **Access the dashboard**:
   - Navigate to `/admin/revenue`
   - Requires admin API key

2. **View metrics**:
   - All-time platform fees collected
   - Monthly revenue breakdown
   - Active subscription count
   - Revenue trends charts

## Webhook Testing

### Test Webhook Locally

1. Trigger a test event:
   ```bash
   stripe trigger checkout.session.completed
   ```

2. Check your backend logs to verify the webhook was received
3. Check the database to see if the subscription was created

### Monitor Webhooks

View webhook logs in:
- Stripe Dashboard > Developers > Webhooks > [Your endpoint]
- See all events, successes, and failures

## API Endpoints

### Journalist Routes

- `POST /api/stripe/journalist/onboard` - Create Stripe Connect account
- `GET /api/stripe/journalist/account-status` - Check onboarding status
- `POST /api/stripe/journalist/create-price` - Set subscription price
- `GET /api/stripe/journalist/my-price` - Get current price
- `PUT /api/stripe/journalist/update-price` - Update price
- `POST /api/stripe/journalist/dashboard-link` - Get Stripe dashboard link

### Subscriber Routes

- `POST /api/stripe/subscribe/:journalist_id` - Create checkout session
- `GET /api/stripe/my-subscriptions` - List user's subscriptions
- `POST /api/stripe/cancel-subscription/:id` - Cancel subscription
- `POST /api/stripe/reactivate-subscription/:id` - Reactivate subscription

### Webhook Route

- `POST /api/stripe/webhook` - Handle Stripe events

### Admin Routes

- `GET /api/admin/revenue/summary` - Revenue summary
- `GET /api/admin/revenue/breakdown` - Revenue by period
- `GET /api/admin/revenue/trends` - Revenue trends for charts
- `GET /api/admin/revenue/current-period` - Current month revenue

## Troubleshooting

### "Stripe not configured" error

- Verify `STRIPE_SECRET_KEY` is set in backend `.env`
- Verify `STRIPE_PUBLISHABLE_KEY` is set in both backend and frontend
- Check that keys start with `sk_test_` and `pk_test_` (or `sk_live_`/`pk_live_` for production)

### Webhook signature verification failed

- Verify `STRIPE_WEBHOOK_SECRET` matches the one from Stripe
- For local dev, make sure Stripe CLI is running: `stripe listen --forward-to localhost:5001/api/stripe/webhook`
- Check webhook endpoint in Stripe dashboard

### Onboarding link doesn't work

- Clear browser cache
- Try generating a new onboarding link
- Check Stripe dashboard for the Connect account status

### Payment fails

- Use valid test cards from https://stripe.com/docs/testing
- Ensure Stripe account has charges enabled
- Check webhook logs for errors

### Database errors

- Run migrations: `flask db upgrade`
- Check that all Stripe models are imported in `main.py`

## Security Best Practices

1. **Never commit API keys** to version control
2. **Use environment variables** for all sensitive data
3. **Verify webhook signatures** (already implemented)
4. **Use HTTPS in production** (required by Stripe)
5. **Implement rate limiting** on API endpoints (already in place)
6. **Validate all user input** before creating Stripe objects

## Going to Production

1. **Switch to live keys**:
   - Get live keys from https://dashboard.stripe.com/apikeys
   - Replace `sk_test_` with `sk_live_`
   - Replace `pk_test_` with `pk_live_`

2. **Update webhook endpoint**:
   - Create new webhook in Stripe dashboard with production URL
   - Update `STRIPE_WEBHOOK_SECRET` with live webhook secret

3. **Complete platform verification**:
   - Stripe will review your platform before allowing live payments
   - Provide business details and terms of service
   - Complete KYC requirements

4. **Test thoroughly**:
   - Test full flow with small real payment
   - Verify webhooks are working
   - Check journalist payouts

5. **Monitor**:
   - Set up Stripe email notifications
   - Monitor webhook logs
   - Check revenue dashboard regularly

## Support

- **Stripe Documentation**: https://stripe.com/docs/connect
- **Stripe Support**: https://support.stripe.com
- **Test your integration**: https://stripe.com/docs/testing

## Architecture Diagrams

### Subscription Flow

```
User → Subscribe Button → Checkout Session (with 10% fee) → Stripe
  ↓
Webhook → Backend → Database
  ↓
Journalist's Stripe Account (90%) + Platform Account (10%)
```

### Revenue Tracking

```
Invoice Payment Succeeded (webhook)
  ↓
Calculate Platform Fee (10%)
  ↓
Update StripePlatformRevenue table
  ↓
Admin Dashboard displays aggregated data
```

## Platform Fee Transparency

The 10% platform fee is used for:
- Server hosting and infrastructure
- Payment processing (Stripe fees)
- Platform maintenance and updates
- Customer support
- Security and compliance

All fees are tracked in the `stripe_platform_revenue` table and displayed transparently in the admin dashboard.
