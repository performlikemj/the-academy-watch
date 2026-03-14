# Production Dockerfile for The Academy Watch Backend - Azure Container App Ready
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (including curl for health checks)
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src/ src/
COPY migrations/ migrations/

# Create non-root user for security (Azure Container Apps recommendation)
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose port (Azure Container Apps will use this)
EXPOSE 5001

# Health check for Azure Container Apps health probes
# Increased start-period to 30s to allow for preloading on cold start
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5001/api/health || exit 1

# Run the application with Gunicorn (production-grade WSGI server)
# Optimized for cold start: fewer workers (2 vs 4), preload app code, longer timeout
CMD ["gunicorn", "-w", "2", "--threads", "2", "--preload", "--timeout", "120", "-b", "0.0.0.0:5001", "--access-logfile", "-", "--error-logfile", "-", "src.main:app"]

# Environment variables will be set by Azure Container Apps:
# ADMIN_API_KEY - Your secure admin API key
# DB_HOST, DB_USER, DB_PASSWORD, DB_NAME - Database connection
# ADMIN_IP_WHITELIST - Optional IP restrictions
# API_FOOTBALL_KEY - Optional for real API data
