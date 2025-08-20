from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from open_webui.models.users import Users
from open_webui.models.groups import Groups

router = APIRouter()


class UserImportRequest(BaseModel):
    email: str
    groups: List[str]


@router.post("/lemon-import")
async def lemon_import(users: List[UserImportRequest]):
    for user in users:
        existing_user = Users.get_user_by_email(user.email)
        if not existing_user:
            raise HTTPException(status_code=404, detail=f"User {user.email} not found")
        Groups.sync_groups_by_group_names(existing_user.id, user.groups)
    return {"status": "ok", "imported": len(users)}
