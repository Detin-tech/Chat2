import logging
import time
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text

from open_webui.internal.db import Base, JSONField, get_db

log = logging.getLogger(__name__)


class PendingGroupGrant(Base):
    __tablename__ = "pending_group_grant"

    email = Column(Text, primary_key=True, unique=True)
    group_ids = Column(JSONField)
    sync_mode = Column(String, default="replace")
    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


class PendingGroupGrantModel(BaseModel):
    email: str
    group_ids: list[str]
    sync_mode: str = "replace"
    created_at: int
    updated_at: int

    model_config = ConfigDict(from_attributes=True)


class PendingGroupGrantForm(BaseModel):
    email: str
    group_ids: list[str]
    sync_mode: str = "replace"


class PendingGroupGrantsTable:
    def upsert_grant(
        self, email: str, group_ids: list[str], sync_mode: str = "replace"
    ) -> Optional[PendingGroupGrantModel]:
        try:
            with get_db() as db:
                grant = db.query(PendingGroupGrant).filter_by(email=email.lower()).first()
                timestamp = int(time.time())
                if grant:
                    grant.group_ids = group_ids
                    grant.sync_mode = sync_mode
                    grant.updated_at = timestamp
                else:
                    grant = PendingGroupGrant(
                        email=email.lower(),
                        group_ids=group_ids,
                        sync_mode=sync_mode,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    db.add(grant)
                db.commit()
                db.refresh(grant)
                return PendingGroupGrantModel.model_validate(grant)
        except Exception as e:
            log.exception(e)
            return None

    def get_grant_by_email(self, email: str) -> Optional[PendingGroupGrantModel]:
        try:
            with get_db() as db:
                grant = db.query(PendingGroupGrant).filter_by(email=email.lower()).first()
                return PendingGroupGrantModel.model_validate(grant) if grant else None
        except Exception as e:
            log.exception(e)
            return None

    def delete_grant_by_email(self, email: str) -> bool:
        try:
            with get_db() as db:
                grant = db.query(PendingGroupGrant).filter_by(email=email.lower()).first()
                if not grant:
                    return False
                db.delete(grant)
                db.commit()
                return True
        except Exception as e:
            log.exception(e)
            return False

    def get_grants(self) -> list[PendingGroupGrantModel]:
        try:
            with get_db() as db:
                grants = db.query(PendingGroupGrant).all()
                return [PendingGroupGrantModel.model_validate(g) for g in grants]
        except Exception as e:
            log.exception(e)
            return []


PendingGroupGrants = PendingGroupGrantsTable()
