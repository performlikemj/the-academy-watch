# Stripe Subscription - Quick Start

## 🚀 5-Minute Setup

### 1. Install Dependencies

```bash
# Backend
cd loan-army-backend
pip install -r requirements.txt

# Frontend (from the repository root)
./scripts/setup_frontend.sh
```

### 2. Get Stripe Keys

1. Sign up at https://stripe.com
2. Go to https://dashboard.stripe.com/apikeys
3. Copy your **Publishable key** (`pk_test_...`)
4. Copy your **Secret key** (`sk_test_...`)

### 3. Configure Environment

**Backend** (`loan-army-backend/.env`):
```env
STRIPE_SECRET_KEY=sk_test_your_key_here
STRIPE_PUBLISHABLE_KEY=pk_test_your_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret
STRIPE_PLATFORM_FEE_PERCENT=10
```

**Frontend** (create `loan-army-frontend/.env.local`):
```env
VITE_STRIPE_PUBLISHABLE_KEY=pk_test_your_key_here
VITE_API_URL=http://localhost:5001/api
VITE_ADMIN_API_KEY=your_admin_api_key
```

### 4. Run Migrations

```bash
cd loan-army-backend
flask db upgrade
```

### 5. Set Up Webhooks (Local Development)

```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe

# Login
stripe login

# Forward webhooks
stripe listen --forward-to localhost:5001/api/stripe/webhook
```

Copy the webhook secret (starts with `whsec_`) to your `.env` file.

### 6. Start the Application

Terminal 1 (Backend):
```bash
cd loan-army-backend
python src/main.py
```

Terminal 2 (Frontend):
```bash
cd loan-army-frontend
pnpm dev
```

Terminal 3 (Stripe CLI):
```bash
stripe listen --forward-to localhost:5001/api/stripe/webhook
```

## 🧪 Test the Flow

### A. Set Up as Journalist

1. Mark your user as journalist in database or admin panel
2. Go to http://localhost:5173/journalist/stripe-setup
3. Click "Create Stripe Account"
4. Complete Stripe onboarding (use test data)
5. Return to app
6. Go to http://localhost:5173/journalist/pricing
7. Set price (e.g., $9.99)

### B. Subscribe as User

1. Create or log in as a different user
2. Go to journalist profile
3. Click "Subscribe Now"
4. Use test card: `4242 4242 4242 4242`
5. Complete checkout
6. View subscription at http://localhost:5173/subscriptions

### C. View Admin Dashboard

1. Go to http://localhost:5173/admin/revenue
2. View platform fees and revenue charts

## 📚 Full Documentation

- **Complete Guide**: See `STRIPE_SETUP_GUIDE.md`
- **Implementation Details**: See `STRIPE_IMPLEMENTATION_SUMMARY.md`

## 🔑 Test Card Numbers

- **Success**: `4242 4242 4242 4242`
- **Decline**: `4000 0000 0000 0002`
- **Requires Auth**: `4000 0025 0000 3155`

Use any future expiry and any 3-digit CVC.

## 🆘 Troubleshooting

**"Stripe not configured"**: Check that all Stripe keys are set in `.env`

**Webhook errors**: Make sure Stripe CLI is running and webhook secret is correct

**Database errors**: Run `flask db upgrade` to create tables

## 🎯 API Endpoints

### Journalist
- `/api/stripe/journalist/onboard` - Create account
- `/api/stripe/journalist/account-status` - Check status
- `/api/stripe/journalist/create-price` - Set price

### Subscriber
- `/api/stripe/subscribe/:journalist_id` - Subscribe
- `/api/stripe/my-subscriptions` - List subscriptions
- `/api/stripe/cancel-subscription/:id` - Cancel

### Admin
- `/api/admin/revenue/summary` - Revenue summary
- `/api/admin/revenue/trends` - Revenue charts

## ✅ What's Implemented

- ✅ Stripe Connect Express for journalists
- ✅ Subscription creation and management
- ✅ Automatic 90/10 revenue split
- ✅ Webhook handling for real-time updates
- ✅ Admin revenue dashboard
- ✅ Cancel/reactivate subscriptions
- ✅ Full error handling
- ✅ Production-ready security

## 📝 Key Features

1. **Journalists**:
   - Create Stripe Connect account
   - Set own subscription prices
   - Receive 90% of revenue
   - Access Stripe dashboard for earnings

2. **Subscribers**:
   - Subscribe with Stripe Checkout
   - Manage subscriptions
   - Cancel anytime (access until period end)
   - Secure payment processing

3. **Platform**:
   - Automatic 10% fee collection
   - Revenue tracking and analytics
   - Transparent admin dashboard
   - Webhook-driven updates

## 🔐 Security

- ✅ Webhook signature verification
- ✅ Authentication required
- ✅ Environment variable configuration
- ✅ No API keys in code
- ✅ Proper authorization checks

## 🚀 Go Live

When ready for production:

1. Get live Stripe keys (replace `sk_test_` with `sk_live_`)
2. Create production webhook endpoint
3. Update all environment variables
4. Test with small real payment
5. Monitor webhook logs

---

**Need Help?**
- Stripe Docs: https://stripe.com/docs
- Stripe Support: https://support.stripe.com
- Test Mode: https://stripe.com/docs/testing
