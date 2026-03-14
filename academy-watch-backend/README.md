# The Academy Watch Backend

A secure API for managing football player loans with automated data fetching and CSV bulk upload capabilities.

## 🚀 Quick Start (Docker + Azure Container App)

### 1. Generate API Key
```bash
# Use any secure method to generate a 32-character key:
python -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32)))"
```

### 2. Build & Test Locally
```bash
docker build -t loan-army-backend .

docker run -p 5001:5001 \
  -e ADMIN_API_KEY=your_test_key_here \
  -e DB_HOST=localhost \
  -e DB_USER=your_user \
  -e DB_PASSWORD=your_password \
  -e DB_NAME=loan_army \
  loan-army-backend
```

### 3. Deploy to Azure Container App
```bash
# Push to Azure Container Registry
az acr login --name myacr
docker tag loan-army-backend myacr.azurecr.io/loan-army-backend:latest
docker push myacr.azurecr.io/loan-army-backend:latest

# Deploy with environment variables
az containerapp create \
  --name loan-army-backend \
  --resource-group myResourceGroup \
  --environment myContainerAppEnv \
  --image myacr.azurecr.io/loan-army-backend:latest \
  --target-port 5001 \
  --ingress external \
  --env-vars \
    ADMIN_API_KEY=your_secure_production_key \
    DB_HOST=your_azure_db_host \
    DB_USER=your_db_user \
    DB_PASSWORD=your_db_password \
    DB_NAME=loan_army_production
```

## 🔒 API Security

### Protected Endpoints (require API key)
- `POST /api/players` - Create players
- `POST /api/loans` - Create loans (auto-fetches player data)
- `POST /api/loans/bulk-upload` - CSV bulk upload
- `PUT /api/loans/<id>/performance` - Update performance stats
- `POST /api/loans/<id>/terminate` - Terminate loans early

### Public Endpoints (no auth needed)
- `GET /api/loans/csv-template` - Download CSV template
- All `GET` endpoints - View teams, players, loans, newsletters

### Usage
```bash
# Include API key in requests
curl -X POST https://your-app.azurecontainerapps.io/api/loans \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{"player_id": 1001, "parent_team_id": 33, "loan_team_id": 532, "loan_start_date": "2024-08-15", "loan_season": "2024-25"}'
```

## 📊 Features

### Auto-Fetch Player Data
Just provide a player ID - the system automatically fetches and creates player records from API-Football.

### CSV Bulk Upload
Download template, fill with loan data, upload to create multiple loans at once.

### Newsletter Generation
AI-powered loan update newsletters for teams based on their loan activity.

### Multiple Loans Per Season
Players can have multiple loans in the same season (to different teams).

## 🎯 Optimized Loan Detection System

### League-Level Player Crawling
The system now uses efficient league-level player detection that reduces API calls by ~90%:

```bash
# Detect loan candidates across Top-5 European leagues for specific transfer window
curl -X POST https://your-app.azurecontainerapps.io/api/detect-loan-candidates \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{"window_key": "2024-25::SUMMER", "league_ids": [39, 140, 78, 135, 61]}'
```

**Key Improvements:**
- **League-level crawl**: One API call per league page instead of per team
- **Multi-club detection**: Automatically detects players appearing in multiple teams within the same season
- **Smart rate limiting**: Respects `X-RateLimit-Remaining` headers automatically
- **Coverage gate**: Skips leagues without player coverage to avoid unnecessary API calls
- **Loan confirmation**: Only hits `/transfers` endpoint for multi-team candidates

### Environment Configuration

```bash
# Set your API-Football key for enhanced loan detection
export API_FOOTBALL_KEY=your_api_football_key_here
```

### Usage Examples

#### Transfer Window-Based API
```bash
# Export loan candidates for specific transfer window
curl "https://your-app.azurecontainerapps.io/api/export-loan-candidates/csv?window_key=2024-25::WINTER&confidence_threshold=0.5" \
  -H "X-API-Key: your_api_key_here"

# Get loan candidates for summer transfer window
curl "https://your-app.azurecontainerapps.io/api/export-loan-candidates/csv?window_key=2023-24::SUMMER" \
  -H "X-API-Key: your_api_key_here"

# Get loan candidates for full season (both summer + winter windows)
curl "https://your-app.azurecontainerapps.io/api/export-loan-candidates/csv?window_key=2022-23::FULL" \
  -H "X-API-Key: your_api_key_here"

# Analyze specific player transfers with window filtering
curl "https://your-app.azurecontainerapps.io/api/analyze-player-transfers/1001?window_key=2024-25::SUMMER" \
  -H "X-API-Key: your_api_key_here"

# Analyze team loan patterns for specific window
curl "https://your-app.azurecontainerapps.io/api/teams/33/analyze-loans?window_key=2023-24::WINTER" \
  -H "X-API-Key: your_api_key_here"
```

#### Window Key Format
The `window_key` parameter uses the format: `<YYYY-YY>::<SUMMER|WINTER|FULL>`

- **SUMMER**: Summer transfer window only
- **WINTER**: Winter/January transfer window only  
- **FULL**: Union of both summer and winter windows for the season

**Supported Seasons**: 2022-23, 2023-24, 2024-25, 2025-26

**Transfer Window Dates**:
- **2022-23**: Summer (2022-07-01 to 2022-09-01), Winter (2023-01-01 to 2023-01-31)
- **2023-24**: Summer (2023-07-01 to 2023-09-01), Winter (2024-01-01 to 2024-02-01)
- **2024-25**: Summer (2024-06-14 to 2024-08-30), Winter (2025-01-01 to 2025-02-03)
- **2025-26**: Summer (2025-06-16 to 2025-09-01), Winter (2026-01-01 to 2026-02-03)

#### Enhanced CSV Export with Team Names

The CSV export now includes human-readable team names alongside team IDs for easier manual review:

**New CSV columns:**
- `primary_team_name`: Human-readable name of the first team (e.g., "Chelsea")
- `loan_team_name`: Human-readable name of the second team (e.g., "Tottenham")

**Example CSV output:**
```csv
player_id,player_name,team_ids,primary_team_name,loan_team_name,loan_confidence...
739,Reguilón,"530,47",Atlético Madrid,Tottenham,1.0,...
263,L. Kurzawa,"36,85",Paris Saint Germain,AC Milan,1.0,...
```

**Team Name Resolution:**
- Names are automatically cached for performance (no additional API calls)
- Falls back gracefully to "Team {ID}" if name lookup fails
- Uses season-specific team data for accurate historical names

### Performance Benefits
- **~90% fewer API requests** compared to team-by-team crawling
- **Accurate loan classification** using transfer type confirmation
- **Automatic pagination** handling with proper rate limiting
- **Efficient pre-computation** eliminates redundant multi-team checks

## 📁 Key Files

- `Dockerfile` - Production container configuration
- `AZURE_DEPLOYMENT.md` - Complete Azure deployment guide
- `src/routes/api.py` - Main API endpoints
- `src/models/league.py` - Database models
- `generate_api_key.py` - Optional key generator (local use only)

## 🔍 Security Verification

```bash
# Check auth status
curl https://your-app.azurecontainerapps.io/api/auth/status

# Test protection works
curl -X POST https://your-app.azurecontainerapps.io/api/loans
# Should return: {"error": "API key required"}
```

## 📚 Documentation

- **AZURE_DEPLOYMENT.md** - Step-by-step Azure deployment
- **API_SECURITY.md** - Security implementation details
- **PRODUCTION_SECURITY.md** - Production security best practices

---

**Security Note**: The system is secure because only the `ADMIN_API_KEY` environment variable you set will work. No one can generate valid keys without access to your environment configuration.