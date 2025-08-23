import os
import time
import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
import jwt
from jwt import PyJWKClient

from open_webui.models.users import Users
from open_webui.models.auths import Auths
from open_webui.utils.auth import get_password_hash
from open_webui.models.groups import Groups
from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["OAUTH"])

MODE = (os.getenv("AUTH_MODE") or "").lower()  # "supabase" to enable
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "").strip()
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL", "").strip()
SUPABASE_JWT_AUD = os.getenv("SUPABASE_JWT_AUD", "").strip()  # e.g., "authenticated" or empty to skip

_jwk_client: Optional[PyJWKClient] = None
_last_jwk_init = 0


def _get_jwk_client() -> Optional[PyJWKClient]:
    global _jwk_client, _last_jwk_init
    now = int(time.time())
    if _jwk_client is None or (now - _last_jwk_init) > 300:
        if SUPABASE_JWKS_URL:
            _jwk_client = PyJWKClient(SUPABASE_JWKS_URL)
            _last_jwk_init = now
    return _jwk_client


def _extract_bearer_token(req: Request) -> Optional[str]:
    # Prefer Authorization header
    authz = req.headers.get("authorization") or req.headers.get("Authorization") or ""
    if authz.lower().startswith("bearer "):
        return authz.split(" ", 1)[1].strip()
    # Fallback: Supabase cookie (commonly "sb")
    cookie = req.headers.get("cookie") or req.headers.get("Cookie") or ""
    for part in cookie.split(";"):
        name, _, val = part.strip().partition("=")
        if name == "sb" and val:
            return val
    return None


def _verify_supabase_jwt(token: str) -> Optional[dict]:
    """
    Verify a Supabase JWT using HS256 (secret) or RS256/ES256 (JWKS).
    We verify 'aud' only if SUPABASE_JWT_AUD is set.
    """
    options = {"verify_aud": bool(SUPABASE_JWT_AUD)}
    audience = SUPABASE_JWT_AUD if SUPABASE_JWT_AUD else None

    # HS256 path
    if SUPABASE_JWT_SECRET:
        try:
            return jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience=audience,
                options=options,
            )
        except Exception:
            return None

    # JWKS (RS/ES) path
    jwk_client = _get_jwk_client()
    if not jwk_client:
        return None
    try:
        signing_key = jwk_client.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            signing_key,
            algorithms=["RS256", "ES256"],
            audience=audience,
            options=options,
        )
    except Exception:
        return None


class SupabaseAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only engage when explicitly enabled
        if MODE != "supabase":
            return await call_next(request)

        scope = getattr(request, "scope", {}) or {}
        sess = scope.get("session")
        if isinstance(sess, dict) and sess.get("user_id"):
            log.warning(f"Session already exists, skipping injection: {sess}")
            response = await call_next(request)
            log.warning(
                f"Final session state (pre-existing): {request.scope.get('session')}"
            )
            return response

        token = _extract_bearer_token(request)
        if not token:
            return await call_next(request)

        claims = _verify_supabase_jwt(token)
        if not claims:
            return await call_next(request)

        # Inject claims as a mock session so downstream middlewares work
        request.scope["session"] = {
            "user_id": claims.get("sub"),
            "email": claims.get("email"),
            "provider": claims.get("app_metadata", {}).get("provider", "email"),
            "role": claims.get("role", "authenticated"),
        }
        log.warning(f"Injected session: {request.scope.get('session')}")

        email = (claims.get("email") or "").strip().lower()
        if not email:
            return await call_next(request)

        log.warning(f"Looking up or creating user for email: {email}")
        user = Users.get_user_by_email(email)
        if not user:
            log.warning(f"User not found for {email}, creating...")
            tmp_pw_hash = get_password_hash(os.urandom(16).hex())
            _ = Auths.insert_new_auth(
                email=email,
                password=tmp_pw_hash,
                name=email.split("@")[0],
                role="user",
            )
            log.warning(f"Re-fetching user for {email} after insert")
            user = Users.get_user_by_email(email)
            log.warning(f"User lookup after insert: {user}")

        if user:
            default_name = os.getenv("OWUI_DEFAULT_GROUP", "").strip()
            if default_name:
                g = Groups.get_group_by_name(default_name)
                if g:
                    Groups.sync_groups_by_group_ids(user.id, [g.id])

        scope = getattr(request, "scope", {}) or {}
        if "session" in scope and user:
            try:
                original_id = scope["session"].get("user_id")
                scope["session"]["user_id"] = user.id
                log.warning(
                    f"Overwrote session user_id: {original_id} -> {user.id}"
                )
            except Exception as e:
                log.warning(f"Could not update session user_id: {e}")

        response = await call_next(request)
        log.warning(f"Final session state: {request.scope.get('session')}")
        return response
