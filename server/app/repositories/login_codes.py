"""Одноразовые коды входа (отправляются на почту)."""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_login_code
from app.core.timeutils import now_local
from app.db.models import TemporaryCodeOrm


class LoginCodesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    async def create(self, user_id: int, code: str) -> TemporaryCodeOrm:
        now = now_local()
        login_code = TemporaryCodeOrm(
            code_hash=hash_login_code(code),
            attempts=0,
            created_at=now,
            expires_at=now + timedelta(minutes=self.settings.login_code_ttl_minutes),
            used_at=None,
            user_id=user_id,
        )
        self.session.add(login_code)
        await self.session.commit()
        return login_code

    async def get_latest(
        self, user_id: int, code_id: int | None = None, only_active: bool = True
    ) -> TemporaryCodeOrm | None:
        query = select(TemporaryCodeOrm).where(TemporaryCodeOrm.user_id == user_id)
        if only_active:
            query = query.where(TemporaryCodeOrm.expires_at > now_local(), TemporaryCodeOrm.used_at.is_(None))
        if code_id is not None:
            query = query.where(TemporaryCodeOrm.id == code_id)
        query = query.order_by(TemporaryCodeOrm.created_at.desc()).limit(1)
        return (await self.session.execute(query)).scalars().first()

    async def extend(self, code_id: int, minutes: int = 2) -> None:
        await self.session.execute(
            update(TemporaryCodeOrm)
            .where(TemporaryCodeOrm.id == code_id)
            .values(expires_at=now_local() + timedelta(minutes=minutes))
        )
        await self.session.commit()

    async def consume_attempt(self, code_id: int) -> bool:
        """Атомарно списывает попытку. False - лимит исчерпан (параллельными запросами его не обойти)."""
        result = await self.session.execute(
            update(TemporaryCodeOrm)
            .where(
                TemporaryCodeOrm.id == code_id,
                TemporaryCodeOrm.attempts < self.settings.login_code_max_attempts,
                TemporaryCodeOrm.used_at.is_(None),
            )
            .values(attempts=TemporaryCodeOrm.attempts + 1)
        )
        await self.session.commit()
        return result.rowcount == 1

    async def mark_used(self, code_id: int) -> bool:
        result = await self.session.execute(
            update(TemporaryCodeOrm)
            .where(TemporaryCodeOrm.id == code_id, TemporaryCodeOrm.used_at.is_(None))
            .values(used_at=now_local())
        )
        await self.session.commit()
        return result.rowcount == 1
