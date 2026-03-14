# API Security Setup

The loan management API now has secure authentication for admin endpoints while keeping public data access open.

## 🔑 Quick Setup

### 1. Generate API Key
```bash
cd loan-army-backend
python generate_api_key.py
```

### 2. Configure Environment
Add the generated key to your `.env` file:
```env
ADMIN_API_KEY=your_generated_api_key_here
```

### 3. Restart Application
```bash
python src/main.py
```

## 🔒 Security Model

### **Secured Endpoints** (require API key)
- `POST /api/players` - Create players
- `POST /api/loans` - Create loans  
- `POST /api/loans/bulk-upload` - Bulk upload via CSV
- `PUT /api/loans/<id>/performance` - Update performance
- `POST /api/loans/<id>/terminate` - Terminate loans
- `POST /api/sync-leagues` - Sync leagues from API-Football
- `POST /api/sync-teams` - Sync teams from API-Football  
- `POST /api/sync-loans` - Sync loans from API-Football

### **Public Endpoints** (no authentication needed)
- `GET /api/loans/csv-template` - Download CSV template
- All `GET` endpoints - View data (teams, players, loans, etc.)
- Newsletter endpoints - Public access to newsletters

## 🛠️ Using Secured Endpoints

### Option 1: X-API-Key Header
```bash
curl -X POST http://localhost:5001/api/loans \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_here" \
  -d '{"player_id": 1001, "parent_team_id": 33, ...}'
```

### Option 2: Authorization Header (Bearer)
```bash
curl -X POST http://localhost:5001/api/loans \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key_here" \
  -d '{"player_id": 1001, "parent_team_id": 33, ...}'
```

### Option 3: Authorization Header (ApiKey)
```bash
curl -X POST http://localhost:5001/api/loans \
  -H "Content-Type: application/json" \
  -H "Authorization: ApiKey your_api_key_here" \
  -d '{"player_id": 1001, "parent_team_id": 33, ...}'
```

## 📋 CSV Upload with Authentication

```bash
curl -X POST http://localhost:5001/api/loans/bulk-upload \
  -H "X-API-Key: your_api_key_here" \
  -F "file=@your_loans.csv"
```

## 🔍 Check Authentication Status

```bash
curl http://localhost:5001/api/auth/status
```

## ⚠️ Error Responses

### Missing API Key
```json
{
  "error": "API key required",
  "message": "Provide API key in X-API-Key header or Authorization header"
}
```

### Invalid API Key
```json
{
  "error": "Invalid API key", 
  "message": "Access denied"
}
```

### API Key Not Configured
```json
{
  "error": "API authentication not configured",
  "message": "Contact administrator"
}
```

## 🔄 Frontend Integration

When building a frontend admin panel, store the API key securely and include it in requests:

```javascript
// JavaScript example
const apiKey = 'your_api_key_here';

fetch('/api/loans', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': apiKey
  },
  body: JSON.stringify({
    player_id: 1001,
    parent_team_id: 33,
    loan_team_id: 532,
    loan_start_date: '2024-08-15',
    loan_season: '2024-25'
  })
});
```

## 💡 Why This Approach?

- **Simple**: No user accounts or complex authentication
- **Secure**: API key protects data modification endpoints  
- **Flexible**: Public read access for newsletters and data viewing
- **Admin-friendly**: Easy to generate new keys and revoke access
- **Integration-ready**: Works with any HTTP client or frontend framework

## 🔐 Security Best Practices

1. **Keep API keys secret** - Don't commit to version control
2. **Use environment variables** - Store in `.env` file
3. **Rotate keys periodically** - Generate new keys regularly
4. **Monitor access logs** - Check for unauthorized attempts
5. **Use HTTPS in production** - Never send API keys over HTTP