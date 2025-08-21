import os
import secrets
import requests
from fastapi import APIRouter, Request, HTTPException

from open_webui.models.users import Users
from open_webui.models.auths import Auths
from open_webui.models.groups import Groups
from open_webui.utils.auth import get_password_hash

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
OWUI_AUTH_TOKEN = os.getenv("OWUI_AUTH_TOKEN")
print("🧪 OWUI sees token as:", repr(OWUI_AUTH_TOKEN))

PLAN_GROUP_MAP = {
    "free": "1",
    "standard": "2",
    "pro": "3",
}


@router.post("/sync-users")
async def sync_users(request: Request):
    # Authorization check
    auth = request.headers.get("Authorization")
    if not auth or auth != OWUI_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Pull users from Supabase
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
    }

    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/users?select=email,plan", headers=headers
    )

    if res.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch from Supabase")

    supabase_users = res.json()

    created, updated = 0, 0
    for user in supabase_users:
        email = user.get("email", "").lower()
        plan = user.get("plan", "free").lower()
        group_id = PLAN_GROUP_MAP.get(plan, PLAN_GROUP_MAP["free"])

        payload = {
            "email": email,
            "group_id": group_id,
        }

        response = requests.post(
            "http://localhost:8080/api/internal/upsert-user",
            headers={"Authorization": OWUI_AUTH_TOKEN},
            json=payload,
        )

        if response.status_code == 200:
            result = response.json()
            if result["status"] == "created":
                created += 1
            elif result["status"] == "updated":
                updated += 1
            else:
                print(f"⚠️ Unknown status for {email}: {result}")
        else:
            print(
                f"❌ Failed to upsert {email}: {response.status_code} {response.text}"
            )

    return {
        "status": "ok",
        "fetched": len(supabase_users),
        "created": created,
        "updated": updated,
    }


@router.post("/internal/upsert-user")
async def upsert_user(payload: dict, request: Request):
    auth = request.headers.get("Authorization")
    if auth != OWUI_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

    email = payload.get("email")
    group_id = payload.get("group_id")

    if not email or not group_id:
        raise HTTPException(status_code=400, detail="Missing fields")

    existing = Users.get_user_by_email(email.lower())
    if existing:
        Groups.sync_groups_by_group_ids(existing.id, [str(group_id)])
        return {"status": "updated", "email": email}

    password = secrets.token_urlsafe(12)
    hashed = get_password_hash(password)
    new_user = Auths.insert_new_auth(
        email=email.lower(),
        password=hashed,
        name=email.split("@")[0],
        role="user",
    )
    if new_user:
        Groups.sync_groups_by_group_ids(new_user.id, [str(group_id)])
        return {"status": "created", "email": email}

    raise HTTPException(status_code=500, detail="Failed to upsert user")
