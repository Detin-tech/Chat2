import os
import secrets
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from open_webui.models.auths import Auths
from open_webui.models.groups import Groups
from open_webui.models.users import Users
from open_webui.utils.auth import get_password_hash

router = APIRouter()

OWUI_AUTH_TOKEN = os.getenv("OWUI_AUTH_TOKEN")
DEFAULT_GROUP_NAME = os.getenv("OWUI_DEFAULT_GROUP", "Student")


def _normalize_token(value: str) -> str:
    value = (value or "").strip()
    return value.split(" ", 1)[1].strip() if value.lower().startswith("bearer ") else value


@router.post("/upsert-users")
async def upsert_users(payload: Dict[str, List[Dict[str, Any]]], request: Request):
    auth = _normalize_token(request.headers.get("Authorization"))
    expected = _normalize_token(OWUI_AUTH_TOKEN)

    if auth != expected:
        if os.getenv("OWUI_AUTH_DEBUG"):
            masked_expected = f"{expected[:4]}...{expected[-4:]}" if expected else "None"
            masked_auth = f"{auth[:4]}...{auth[-4:]}" if auth else "None"
            print(f"Auth mismatch expected={masked_expected} got={masked_auth}")
        raise HTTPException(status_code=401, detail="Invalid token")

    users = payload.get("users")
    if not isinstance(users, list):
        raise HTTPException(status_code=400, detail="Invalid payload")

    received = len(users)
    created = 0
    updated = 0
    failed = 0
    results = []

    default_group = Groups.get_group_by_name(DEFAULT_GROUP_NAME)

    for item in users:
        email = (item.get("email") or "").strip().lower()
        if not email:
            failed += 1
            results.append({"email": None, "status": "missing-email"})
            continue

        name = (item.get("name") or email.split("@")[0]).strip()
        role = (item.get("role") or "user").strip()
        group_name = (item.get("group") or "").strip()

        group = Groups.get_group_by_name(group_name) if group_name else None
        if not group:
            group = default_group

        try:
            existing = Users.get_user_by_email(email)
            if existing:
                Users.update_user_by_id(existing.id, {"name": name, "email": email, "role": role})
                if group:
                    Groups.sync_groups_by_group_ids(existing.id, [group.id])
                updated += 1
                results.append({"email": email, "status": "updated"})
            else:
                password = secrets.token_urlsafe(12)
                hashed = get_password_hash(password)
                new_user = Auths.insert_new_auth(
                    email=email,
                    password=hashed,
                    name=name,
                    role=role,
                )
                if new_user and group:
                    Groups.sync_groups_by_group_ids(new_user.id, [group.id])
                created += 1
                results.append({"email": email, "status": "created"})
        except Exception as e:  # pragma: no cover - unexpected errors
            failed += 1
            results.append({"email": email, "status": "failed", "error": str(e)})

    return {
        "received": received,
        "created": created,
        "updated": updated,
        "failed": failed,
        "results": results,
    }
