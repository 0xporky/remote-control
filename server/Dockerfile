# Remote Control Server Dockerfile
# Multi-stage build for smaller production image

# ==============================================================================
# Stage 1: Builder - Install dependencies
# ==============================================================================
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies (if any native extensions needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies to user directory
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ==============================================================================
# Stage 2: Production - Minimal runtime image
# ==============================================================================
FROM python:3.11-slim

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash appuser

WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Add user's local bin to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application source code
COPY main.py .
COPY auth.py .
COPY config.py .
COPY signaling.py .
COPY messages.py .
COPY rate_limiter.py .
COPY routes/ ./routes/

# Set ownership to non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# ==============================================================================
# Environment Configuration
# ==============================================================================

# Server settings
ENV HOST=0.0.0.0
ENV PORT=8000

# Security defaults (OVERRIDE IN PRODUCTION!)
# ENV SECRET_KEY=change-this-in-production
# ENV AUTH_PASSWORD=admin

# SSL disabled by default
ENV SSL_ENABLED=false

# Rate limiting defaults
ENV RATE_LIMIT_LOGIN_MAX_ATTEMPTS=5
ENV RATE_LIMIT_LOGIN_WINDOW_SECONDS=60
ENV RATE_LIMIT_LOGIN_LOCKOUT_SECONDS=300

# WebSocket defaults
ENV WS_SESSION_TIMEOUT_SECONDS=3600
ENV WS_PING_INTERVAL_SECONDS=30
ENV WS_PING_TIMEOUT_SECONDS=10

# CORS defaults
ENV CORS_ORIGINS=*

# Static files (mount web client here if serving)
ENV WEB_CLIENT_PATH=/app/static

# ==============================================================================
# Container Configuration
# ==============================================================================

# Expose port
EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/api/health')" || exit 1

# Run the server
CMD ["python", "main.py"]
