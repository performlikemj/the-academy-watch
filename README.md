# The Academy Watch

Football academy tracking platform that monitors academy players on loan, generates AI-powered newsletters, and provides career journey analytics across European football.

## Tech Stack

- **Frontend**: React 19 + Vite 6 + Tailwind CSS 4 + Radix UI
- **Backend**: Flask 3.1 + SQLAlchemy 2.0 + Alembic
- **Database**: PostgreSQL
- **Deployment**: Azure Container Apps (backend) + Azure Static Web App (frontend)
- **Integrations**: API-Football, Mailgun, Stripe Connect, OpenAI

## Getting Started

### Backend

```bash
cd loan-army-backend

# Create and activate virtual environment
python -m venv ../.loan
source ../.loan/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env template and configure
cp env.template .env

# Run database migrations
flask db upgrade

# Start dev server (port 5001)
python src/main.py
```

### Frontend

```bash
cd loan-army-frontend

pnpm install       # Install dependencies
pnpm dev           # Dev server (port 5173, proxies /api to :5001)
pnpm build         # Production build
pnpm lint          # ESLint
```

## Testing

```bash
cd loan-army-frontend

pnpm test:e2e                                          # All Playwright E2E tests
pnpm exec playwright test tests/admin-teams.test.mjs   # Single test file
pnpm exec playwright test --ui                          # Interactive UI mode
```

## Deployment

```bash
# Full deployment to Azure Container Apps + Static Web App
./deploy_aca.sh
```

See `.github/workflows/deploy.yml` for CI/CD configuration.

## Project Structure

```
loan-army-backend/src/
├── routes/          # API endpoints
├── models/          # SQLAlchemy models
├── services/        # Business logic (email, reddit, analytics)
├── agents/          # AI newsletter generation
└── templates/       # Email & web newsletter templates

loan-army-frontend/src/
├── pages/admin/     # Admin dashboard
├── pages/writer/    # Writer interface
├── components/      # React components
└── lib/api.js       # API service wrapper
```

## Architecture

For detailed architecture, API-Football integration, data model relationships, caching strategy, and deployment topology, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Contributing

1. Read `AGENTS.md` for operating principles
2. Check `CONTINUITY.md` for current project state
3. Follow the ledger protocol for non-trivial changes
