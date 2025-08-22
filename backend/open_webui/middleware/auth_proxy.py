import os
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

from open_webui.models.users import Users
from open_webui.models.auths import Auths
from open_webui.utils.auth import get_password_hash

# Env flags
ENABLED = os.getenv("AUTH_PROXY_ENABLED", "0").lower() in ("1", "true", "yes")
HEADER_EMAIL = os.getenv("AUTH_PROXY_HEADER_EMAIL", "CF-Access-Authenticated-User-Email")

class AuthProxyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # If disabled or header not present, continue normally
        if not ENABLED:
            return await call_next(request)

        # If session already present, no-op
        try:
            # Starlette SessionMiddleware exposes request.session (dict-like)
            if hasattr(request, "session") and request.session.get("user_id"):
                return await call_next(request)
        except Exception:
            pass

        # Pull email from Cloudflare Access header
        email = (request.headers.get(HEADER_EMAIL) or "").strip().lower()
        if not email:
            return await call_next(request)

        # Ensure user exists (create if missing)
        user = Users.get_user_by_email(email)
        if not user:
            # Create minimal auth record with random password (never used)
            tmp_pw_hash = get_password_hash(os.urandom(16).hex())
            _ = Auths.insert_new_auth(
                email=email,
                password=tmp_pw_hash,
                name=email.split("@")[0],
                role="user",
            )
            user = Users.get_user_by_email(email)

        # Establish OWUI session so downstream sees user as logged in
        # Many OWUI builds use Starlette sessions: request.session["user_id"] = <id>
        # If session middleware is not available for some reason, we simply continue;
        # the next request after login will have a session cookie set by OWUI.
        if user and hasattr(request, "session"):
            try:
                request.session["user_id"] = user.id
            except Exception:
                # If sessions aren’t available, we just pass through.
                pass

        return await call_next(request)
