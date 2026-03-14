# 🚀 Production Deployment Checklist

## Pre-Deployment Security Setup

### ✅ API Key Generation
- [ ] Run `python generate_api_key.py` **locally** (not on server)
- [ ] Save the generated key securely
- [ ] **DO NOT** commit the key to version control

### ✅ Environment Configuration
- [ ] Set `ADMIN_API_KEY` in production environment variables
- [ ] Set `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` 
- [ ] Optional: Set `ADMIN_IP_WHITELIST` for IP restrictions
- [ ] Verify `API_FOOTBALL_KEY` is set if using real API data

### ✅ File Exclusions
- [ ] Verify `.gitignore` excludes sensitive files
- [ ] For Heroku: Verify `.slugignore` excludes `generate_api_key.py`
- [ ] For Docker: Verify `.dockerignore` excludes `generate_api_key.py`
- [ ] Ensure `.env` files are NOT in version control

## Platform-Specific Deployment

### Heroku
```bash
# Set environment variables
heroku config:set ADMIN_API_KEY=your_secure_key_here
heroku config:set DB_HOST=your_db_host
heroku config:set DB_USER=your_db_user
heroku config:set DB_PASSWORD=your_db_password
heroku config:set DB_NAME=your_db_name

# Optional: IP whitelist
heroku config:set ADMIN_IP_WHITELIST=192.168.1.100,10.0.0.50

# Deploy
git push heroku main
```

### Railway
```bash
# Set in Railway dashboard or CLI
railway variables set ADMIN_API_KEY your_secure_key_here
railway variables set DB_HOST your_db_host
# ... other variables

railway up
```

### Docker
```bash
# Build
docker build -t loan-army .

# Run with environment variables
docker run -p 5001:5001 \
  -e ADMIN_API_KEY=your_secure_key_here \
  -e DB_HOST=your_db_host \
  -e DB_USER=your_db_user \
  -e DB_PASSWORD=your_db_password \
  -e DB_NAME=your_db_name \
  loan-army
```

## Post-Deployment Verification

### ✅ Security Tests
```bash
# Test auth status
curl https://your-domain.com/api/auth/status

# Verify protection (should fail)
curl -X POST https://your-domain.com/api/loans
# Expected: {"error": "API key required"}

# Verify authorized access works
curl -X POST https://your-domain.com/api/loans \
  -H "X-API-Key: your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"test": "verification"}'
```

### ✅ IP Whitelist Test (if enabled)
```bash
# Should fail from non-whitelisted IP
curl -X POST https://your-domain.com/api/loans \
  -H "X-API-Key: your_key_here"
# Expected: {"error": "Access denied from this IP address"}
```

### ✅ Public Endpoints Test
```bash
# Should work without API key
curl https://your-domain.com/api/loans/csv-template
curl https://your-domain.com/api/teams
curl https://your-domain.com/api/loans
```

## Security Monitoring

### ✅ Log Monitoring
- [ ] Monitor for repeated invalid API key attempts
- [ ] Monitor for access from unexpected IPs
- [ ] Set up alerts for authentication failures

### ✅ Regular Maintenance
- [ ] Rotate API keys periodically (monthly/quarterly)
- [ ] Review IP whitelist regularly
- [ ] Update dependencies regularly
- [ ] Monitor for security vulnerabilities

## Emergency Procedures

### If API Key is Compromised
1. Generate new key locally: `python generate_api_key.py`
2. Update production environment variable immediately
3. Update your tools/scripts with new key
4. Monitor logs for suspicious activity
5. Consider temporary IP restrictions

### If Unauthorized Access Detected
1. Immediately rotate API key
2. Enable IP whitelist restrictions
3. Review access logs
4. Check for data modifications
5. Notify relevant stakeholders

## Production Checklist Summary

- [ ] API key generated locally ✨
- [ ] Environment variables set in production platform ✨
- [ ] Sensitive files excluded from deployment ✨
- [ ] HTTPS enabled ✨
- [ ] Security tests passed ✨
- [ ] Monitoring configured ✨
- [ ] Emergency procedures documented ✨

**🔒 Your admin endpoints are now production-ready and secure!**