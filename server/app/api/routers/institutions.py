from fastapi import APIRouter

from app.api.deps import InstitutionsRepo, Provider
from app.schemas.institutions import InstitutionsResponse

router = APIRouter(prefix="/institution", tags=["Учебные заведения"])


@router.get("/institutions", response_model=InstitutionsResponse, summary="Список заведений (поставщик)")
async def get_institutions(provider: Provider, institutions: InstitutionsRepo):
    return InstitutionsResponse(Institutions=await institutions.get_all())
