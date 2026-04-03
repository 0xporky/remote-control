import logging
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, status, Request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import config
from auth import (
    Token, LoginRequest, GoogleLoginRequest,
    create_access_token, authenticate,
    verify_google_token, is_google_user_allowed
)
from routes.websocket import router as websocket_router
from rate_limiter import login_rate_limiter, RateLimitConfig

# Configure rate limiter from config
login_rate_limiter.config = RateLimitConfig(
    max_attempts=config.RATE_LIMIT_LOGIN_MAX_ATTEMPTS,
    window_seconds=config.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
    lockout_seconds=config.RATE_LIMIT_LOGIN_LOCKOUT_SECONDS,
)

app = FastAPI(
    title="Remote Control Server",
    description="WebRTC signaling server for remote desktop control",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include WebSocket router
app.include_router(websocket_router)


def get_client_ip(request: Request) -> str:
    """Get the client IP address from the request."""
    # Check for forwarded header (behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # Check for real IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    # Fall back to direct client
    return request.client.host if request.client else "unknown"


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "message": "Server is running"}


@app.post("/api/auth/login", response_model=Token)
async def login(request: LoginRequest, req: Request):
    """Authenticate and return a JWT token."""
    client_ip = get_client_ip(req)

    # Check rate limit
    is_allowed, message = await login_rate_limiter.is_allowed(client_ip)
    if not is_allowed:
        logger.warning(f"Rate limited login attempt from {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=message,
        )

    if not authenticate(request.password):
        # Record failed attempt
        await login_rate_limiter.record_attempt(client_ip, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Record successful login (clears rate limit)
    await login_rate_limiter.record_attempt(client_ip, success=True)

    access_token_expires = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": "user"},
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token, token_type="bearer")


@app.post("/api/auth/google", response_model=Token)
async def google_login(request: GoogleLoginRequest, req: Request):
    """Authenticate using Google OAuth and return a JWT token."""
    client_ip = get_client_ip(req)

    # Check rate limit (shared with password login)
    is_allowed, message = await login_rate_limiter.is_allowed(client_ip)
    if not is_allowed:
        logger.warning(f"Rate limited Google login attempt from {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=message,
        )

    # Check if Google OAuth is configured
    if not config.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured",
        )

    # Verify Google token
    user_info = verify_google_token(request.credential)
    if not user_info:
        await login_rate_limiter.record_attempt(client_ip, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if email is verified
    if not user_info.get('email_verified'):
        await login_rate_limiter.record_attempt(client_ip, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google email not verified",
        )

    # Check if user is allowed
    if not is_google_user_allowed(user_info['email']):
        await login_rate_limiter.record_attempt(client_ip, success=False)
        logger.warning(f"Unauthorized Google login attempt: {user_info['email']}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not authorized",
        )

    # Record successful login (clears rate limit)
    await login_rate_limiter.record_attempt(client_ip, success=True)
    logger.info(f"Google login successful: {user_info['email']}")

    # Create JWT with Google user info
    access_token_expires = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user_info['email'],
            "auth_method": "google",
            "name": user_info.get('name', ''),
        },
        expires_delta=access_token_expires,
    )

    return Token(access_token=access_token, token_type="bearer")


@app.get("/api/generate-agent-token")
async def generate_agent_token():
    """Generate a new agent token (for admin use)."""
    token = config.generate_agent_token()
    return {
        "token": token,
        "message": "Add this token to AGENT_TOKENS environment variable",
    }


# Mount static files for web client
web_client_path = Path(__file__).parent / config.WEB_CLIENT_PATH
if web_client_path.exists():
    app.mount("/assets", StaticFiles(directory=str(web_client_path / "assets")), name="assets")

    @app.get("/")
    async def serve_index():
        """Serve the web client index.html."""
        index_path = web_client_path / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        raise HTTPException(status_code=404, detail="Web client not found")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        """Serve SPA - return index.html for all non-API routes."""
        # Don't serve index.html for API or WebSocket routes
        if path.startswith("api/") or path.startswith("ws/"):
            raise HTTPException(status_code=404, detail="Not found")

        # Check if file exists in static directory
        file_path = web_client_path / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))

        # Return index.html for SPA routing
        index_path = web_client_path / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        raise HTTPException(status_code=404, detail="Not found")


if __name__ == "__main__":
    import uvicorn

    # Build uvicorn config
    uvicorn_config = {
        "app": "main:app",
        "host": config.HOST,
        "port": config.PORT,
        "reload": True,
    }

    # Add SSL if enabled
    if config.SSL_ENABLED:
        if not config.SSL_KEYFILE or not config.SSL_CERTFILE:
            logger.error("SSL enabled but SSL_KEYFILE or SSL_CERTFILE not set")
            exit(1)
        uvicorn_config["ssl_keyfile"] = config.SSL_KEYFILE
        uvicorn_config["ssl_certfile"] = config.SSL_CERTFILE
        logger.info(f"Starting server with SSL on https://{config.HOST}:{config.PORT}")
    else:
        logger.info(f"Starting server on http://{config.HOST}:{config.PORT}")

    uvicorn.run(**uvicorn_config)
