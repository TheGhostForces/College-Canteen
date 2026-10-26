from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EducationInstitutionOrm


class InstitutionsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> Sequence[EducationInstitutionOrm]:
        return (await self.session.execute(select(EducationInstitutionOrm))).scalars().all()
