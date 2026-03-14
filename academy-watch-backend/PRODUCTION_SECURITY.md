# Production Security Guide

## 🚨 Security Architecture

### How It Actually Works
1. **The Security**: Only the key stored in `ADMIN_API_KEY` environment variable will work
2. **Key Generation**: You can generate keys locally using any secure method
3. **The Risk**: If someone gets server access, they could read environment variables

## 🔐 Production Deployment Strategy

### Secure Environment Variables
```bash
# 1. Generate key locally using any method:
python generate_api_key.py  # (optional convenience script)
# OR
openssl rand -base64 32
# OR  
python -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32)))"

# 2. Set in production environment
# Docker + Azure Container App:
az containerapp create --env-vars ADMIN_API_KEY=your_secure_key_here

# Docker locally:
docker run -e ADMIN_API_KEY=your_secure_key_here your_app
```

### Option 2: Secrets Management (Best for Enterprise)
```bash
# AWS Secrets Manager
aws secretsmanager create-secret --name loan-army-api-key --secret-string "your_key_here"

# Azure Key Vault
az keyvault secret set --vault-name your-vault --name api-key --value "your_key_here"

# HashiCorp Vault
vault kv put secret/loan-army api-key="your_key_here"
```

## 🛡️ Enhanced Security Measures

### 1. IP Whitelisting (Add this to your API)
```python
ALLOWED_ADMIN_IPS = os.getenv('ADMIN_IP_WHITELIST', '').split(',')

def require_api_key_and_ip(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check IP whitelist first
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        if ALLOWED_ADMIN_IPS and client_ip not in ALLOWED_ADMIN_IPS:
            return jsonify({'error': 'Access denied from this IP'}), 403
        
        # Then check API key
        return require_api_key(f)(*args, **kwargs)
    return decorated_function
```

### 2. Time-Limited Keys
```python
import jwt
from datetime import datetime, timedelta

def generate_time_limited_key(hours=24):
    payload = {
        'admin': True,
        'exp': datetime.utcnow() + timedelta(hours=hours)
    }
    return jwt.encode(payload, os.getenv('JWT_SECRET'), algorithm='HS256')
```

### 3. Request Rate Limiting
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@api_bp.route('/loans/bulk-upload', methods=['POST'])
@limiter.limit("5 per minute")  # Only 5 uploads per minute
@require_api_key
def bulk_upload_loans():
    # ... existing code
```

## 📁 Production File Structure

### What to Deploy
```
loan-army-backend/
├── src/                    ✅ Deploy
├── requirements.txt        ✅ Deploy
├── .env.example           ✅ Deploy (template only)
├── API_SECURITY.md        ✅ Deploy (documentation)
└── PRODUCTION_SECURITY.md ✅ Deploy (this file)
```

### What NOT to Deploy
```
loan-army-backend/
├── generate_api_key.py    ❌ DON'T Deploy (security risk)
├── .env                   ❌ DON'T Deploy (contains secrets)
└── *.log                  ❌ DON'T Deploy (may contain sensitive data)
```

## 🚀 Platform-Specific Deployment

### Heroku
```bash
# 1. Generate key locally
python generate_api_key.py

# 2. Set environment variable
heroku config:set ADMIN_API_KEY=your_key_here

# 3. Create .slugignore to exclude files
echo "generate_api_key.py" > .slugignore
echo ".env" >> .slugignore

# 4. Deploy
git push heroku main
```

### Railway
```bash
# 1. In Railway dashboard, set environment variable:
ADMIN_API_KEY=your_secure_key_here

# 2. Deploy normally
railway up
```

### Docker Production
```dockerfile
# Dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy source code only (not scripts)
COPY src/ src/
COPY API_SECURITY.md .
COPY PRODUCTION_SECURITY.md .

# DON'T COPY: generate_api_key.py, .env

CMD ["python", "src/main.py"]
```

```bash
# Build and run
docker build -t loan-army .
docker run -e ADMIN_API_KEY=your_secure_key_here -p 5001:5001 loan-army
```

## 🔍 Security Verification Checklist

### Before Deployment
- [ ] Generated API key locally (not on server)
- [ ] Set ADMIN_API_KEY in production environment variables
- [ ] Excluded generate_api_key.py from deployment
- [ ] Using HTTPS in production
- [ ] Environment variables are not in version control

### After Deployment
```bash
# Test security
curl https://your-domain.com/api/auth/status

# Verify protected endpoint blocks unauthorized access
curl -X POST https://your-domain.com/api/loans
# Should return: {"error": "API key required"}

# Verify authorized access works
curl -X POST https://your-domain.com/api/loans \
  -H "X-API-Key: your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

## 🚫 What Malicious Actors CAN'T Do

1. **Generate working keys**: Random strings won't match your environment variable
2. **Access data without key**: All write operations are protected
3. **Read environment variables**: Requires server-level access (bigger problem)

## ⚠️ What Malicious Actors COULD Do (and mitigations)

1. **Server compromise**: If they get server access, they can read environment variables
   - **Mitigation**: Use secrets management, IP whitelisting, monitoring
   
2. **Key exposure**: If API key leaks in logs or code
   - **Mitigation**: Regular key rotation, secure logging
   
3. **Brute force attacks**: Try random keys
   - **Mitigation**: Rate limiting, monitoring failed attempts

## 🔄 Key Rotation Strategy

```bash
# 1. Generate new key
python generate_api_key.py  # (locally)

# 2. Update production environment
heroku config:set ADMIN_API_KEY=new_key_here

# 3. Update your tools/scripts
# 4. Test endpoints
# 5. Monitor for any issues
```

## 📊 Monitoring & Alerting

Set up alerts for:
- Multiple failed API key attempts
- Unusual upload volumes
- Access from unexpected IPs
- Failed authentication patterns

This gives you a production-grade security setup that's both secure and manageable!