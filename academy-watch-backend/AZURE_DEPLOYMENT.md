# Azure Container App Deployment Guide

## 🚀 Docker + Azure Container App Setup

### Prerequisites
- Docker installed locally
- Azure CLI installed
- Azure subscription with Container Apps enabled

## 🔑 API Key Generation (Local Only)

You can generate a secure API key using any method:

```bash
# Option 1: Use the provided script (locally)
python generate_api_key.py

# Option 2: Use openssl (if available)
openssl rand -base64 32

# Option 3: Use Python one-liner
python -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32)))"
```

## 🐳 Docker Build & Test

### Build the Container
```bash
cd loan-army-backend
docker build -t loan-army-backend .
```

### Test Locally
```bash
docker run -p 5001:5001 \
  -e ADMIN_API_KEY=your_test_key_here \
  -e DB_HOST=your_db_host \
  -e DB_USER=your_db_user \
  -e DB_PASSWORD=your_db_password \
  -e DB_NAME=your_db_name \
  loan-army-backend
```

### Verify Security
```bash
# Check auth status
curl http://localhost:5001/api/auth/status

# Test protected endpoint (should fail)
curl -X POST http://localhost:5001/api/loans

# Test with key (should work)
curl -X POST http://localhost:5001/api/loans \
  -H "X-API-Key: your_test_key_here" \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

## ☁️ Azure Container App Deployment

### 1. Push to Azure Container Registry
```bash
# Create ACR (if needed)
az acr create --resource-group myResourceGroup --name myacr --sku Basic

# Login to ACR
az acr login --name myacr

# Tag and push image
docker tag loan-army-backend myacr.azurecr.io/loan-army-backend:latest
docker push myacr.azurecr.io/loan-army-backend:latest
```

### 2. Create Container App Environment
```bash
az containerapp env create \
  --name myContainerAppEnv \
  --resource-group myResourceGroup \
  --location eastus
```

### 3. Deploy Container App with Environment Variables
```bash
az containerapp create \
  --name loan-army-backend \
  --resource-group myResourceGroup \
  --environment myContainerAppEnv \
  --image myacr.azurecr.io/loan-army-backend:latest \
  --target-port 5001 \
  --ingress external \
  --env-vars \
    ADMIN_API_KEY=your_secure_production_key_here \
    DB_HOST=your_production_db_host \
    DB_USER=your_production_db_user \
    DB_PASSWORD=your_production_db_password \
    DB_NAME=your_production_db_name \
    ADMIN_IP_WHITELIST=your.admin.ip.here
```

### 4. Update Environment Variables (as needed)
```bash
az containerapp update \
  --name loan-army-backend \
  --resource-group myResourceGroup \
  --set-env-vars ADMIN_API_KEY=new_key_here
```

## 🔒 Production Security Checklist

### ✅ Before Deployment
- [ ] Generate secure API key locally
- [ ] Set up Azure Database (PostgreSQL/MySQL)
- [ ] Configure network security groups if needed
- [ ] Plan your IP whitelist (optional)

### ✅ During Deployment
- [ ] Set all environment variables via Azure CLI
- [ ] Enable HTTPS ingress
- [ ] Verify container builds without sensitive files
- [ ] Test authentication endpoints

### ✅ After Deployment
- [ ] Test API key protection works
- [ ] Verify public endpoints accessible
- [ ] Test CSV upload with authentication
- [ ] Set up monitoring/logging

## 📊 Monitoring & Management

### View Logs
```bash
az containerapp logs show \
  --name loan-army-backend \
  --resource-group myResourceGroup
```

### Scale Container App
```bash
az containerapp update \
  --name loan-army-backend \
  --resource-group myResourceGroup \
  --min-replicas 1 \
  --max-replicas 3
```

### Update Image
```bash
# Build new image
docker build -t loan-army-backend .
docker tag loan-army-backend myacr.azurecr.io/loan-army-backend:v2
docker push myacr.azurecr.io/loan-army-backend:v2

# Update container app
az containerapp update \
  --name loan-army-backend \
  --resource-group myResourceGroup \
  --image myacr.azurecr.io/loan-army-backend:v2
```

## 🔐 Security Best Practices

1. **Environment Variables**: Store ALL secrets as environment variables
2. **Network Security**: Use Azure's network security groups
3. **HTTPS Only**: Enable HTTPS ingress in Container Apps
4. **Regular Updates**: Keep base images and dependencies updated
5. **Monitoring**: Enable Azure Monitor for the container app
6. **Key Rotation**: Update ADMIN_API_KEY periodically

## 🌐 Custom Domain (Optional)

```bash
# Add custom domain
az containerapp hostname add \
  --name loan-army-backend \
  --resource-group myResourceGroup \
  --hostname api.yourdomain.com
```

## 💡 Environment Variable Summary

Required for production:
```bash
ADMIN_API_KEY=your_32_character_secure_key
DB_HOST=your_azure_db_host
DB_USER=your_db_user  
DB_PASSWORD=your_secure_db_password
DB_NAME=loan_army_production
```

Optional for enhanced security:
```bash
ADMIN_IP_WHITELIST=192.168.1.100,203.0.113.50
API_FOOTBALL_KEY=your_api_football_key
```

Your Docker + Azure Container App setup is production-ready and secure! 🚀