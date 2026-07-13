from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from jose import JWTError, jwt
from starlette.config import Config

from app.config import settings
from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.utils.auth_utils import (
    create_access_token,
    create_refresh_token,
    hash_token,
    set_auth_cookies,
)
from app.dependencies.auth import get_current_user
from loguru import logger

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Configure OAuth
config = Config(environ={
    "GOOGLE_CLIENT_ID": settings.google_client_id,
    "GOOGLE_CLIENT_SECRET": settings.google_client_secret,
})
oauth = OAuth(config)
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/google/login")
async def google_login(request: Request):
    """Redirect to Google OAuth consent screen."""
    redirect_uri = settings.google_redirect_uri
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback, create/find user, issue JWT cookies."""
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get("userinfo")
        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")

        google_id = user_info["sub"]
        email = user_info["email"]
        full_name = user_info.get("name")
        avatar_url = user_info.get("picture")

        # Find or create user
        result = await db.execute(
            select(User).where(User.google_id == google_id)
        )
        user = result.scalar_one_or_none()

        is_first_login = False
        if not user:
            # Check if email exists without google_id
            result2 = await db.execute(select(User).where(User.email == email))
            user = result2.scalar_one_or_none()

            if user:
                user.google_id = google_id
                user.avatar_url = avatar_url
            else:
                is_first_login = True
                user = User(
                    email=email,
                    full_name=full_name,
                    avatar_url=avatar_url,
                    google_id=google_id,
                    role=UserRole.analyst,  # Default role
                    status=UserStatus.active,
                    is_first_login=True,
                )
                db.add(user)

        user.last_login = datetime.now(timezone.utc)
        if not is_first_login:
            user.is_first_login = False

        await db.commit()
        await db.refresh(user)

        # Create tokens
        access_token = create_access_token(user.id, user.role.value)
        refresh_token = create_refresh_token(user.id)

        # Store hashed refresh token
        user.refresh_token_hash = hash_token(refresh_token)
        await db.commit()

        logger.info(f"User logged in: {email} | role: {user.role}")

        # Set cookies and redirect to frontend
        redirect_response = RedirectResponse(
            url=f"http://localhost:3000/dashboard",
            status_code=302,
        )
        set_auth_cookies(redirect_response, access_token, refresh_token)
        return redirect_response

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token cookie."""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    try:
        payload = jwt.decode(
            refresh_token, settings.secret_key, algorithms=[settings.algorithm]
        )
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user_id = payload.get("sub")
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user or user.refresh_token_hash != hash_token(refresh_token):
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        new_access_token = create_access_token(user.id, user.role.value)
        new_refresh_token = create_refresh_token(user.id)

        user.refresh_token_hash = hash_token(new_refresh_token)
        await db.commit()

        resp = JSONResponse({"message": "Token refreshed"})
        set_auth_cookies(resp, new_access_token, new_refresh_token)
        return resp

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")


@router.post("/logout")
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clear auth cookies and invalidate refresh token."""
    current_user.refresh_token_hash = None
    await db.commit()

    resp = JSONResponse({"message": "Logged out successfully"})
    resp.delete_cookie("access_token")
    resp.delete_cookie("refresh_token")
    return resp


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return current logged-in user info."""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "avatar_url": current_user.avatar_url,
        "role": current_user.role,
        "status": current_user.status,
        "is_first_login": current_user.is_first_login,
        "last_login": current_user.last_login,
    }