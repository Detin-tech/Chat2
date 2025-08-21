import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ValidationError

from open_webui.models.users import Users
from open_webui.models.auths import Auths
from open_webui.models.groups import Groups
from open_webui.utils.auth import get_password_hash

router = APIRouter()


class SyncUser(BaseModel):
    name: str
    email: str
    password: Optional[str] = None
    role: str = "user"
    group: Optional[str] = None


@router.post("/sync-users")
async def sync_users(
    request: Request, data: Dict[str, Any], authorization: Optional[str] = Header(None)
):
    token = getattr(request.app.state, "SYNC_USERS_TOKEN", None)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization"
        )
    if not token or authorization.split(" ", 1)[1] != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    users_payload = data.get("users") if isinstance(data, dict) else data
    if not isinstance(users_payload, list):
        raise HTTPException(status_code=400, detail="Invalid payload")

    results = []
    for raw_user in users_payload:
        try:
            user_data = SyncUser.model_validate(raw_user)
            existing = Users.get_user_by_email(user_data.email)
            if not existing:
                password = user_data.password or secrets.token_urlsafe(12)
                hashed = get_password_hash(password)
                created = Auths.insert_new_auth(
                    email=user_data.email,
                    password=hashed,
                    name=user_data.name,
                    role=user_data.role,
                )
                user_id = created.id if created else None
                status_msg = "created"
            else:
                update = {
                    "name": user_data.name,
                    "email": user_data.email,
                    "role": user_data.role,
                }
                Users.update_user_by_id(existing.id, update)
                if user_data.password:
                    Auths.update_user_password_by_id(
                        existing.id, get_password_hash(user_data.password)
                    )
                user_id = existing.id
                status_msg = "updated"

            if user_data.group and user_id:
                group = Groups.get_group_by_name(user_data.group)
                if group:
                    Groups.add_users_to_group(group.id, [user_id])

            results.append({"email": user_data.email, "status": status_msg, "success": True})
        except ValidationError as e:
            results.append({"email": raw_user.get("email"), "success": False, "error": e.errors()})
        except Exception as e:  # pragma: no cover - log unexpected
            results.append({"email": getattr(user_data, "email", None), "success": False, "error": str(e)})
    return {"results": results}
