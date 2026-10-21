from fastapi import APIRouter, Depends
from database.repository import InstitutionRepository
from schemas import InstitutionsUniversal
from security.auth import require_role

router = APIRouter(
    prefix="/institution",
    tags=["Эндпоинты для учебных заведений"],
)

@router.get("/institutions", tags=["Поставщик"], response_model=InstitutionsUniversal)
async def get_institutions(provider = Depends(require_role("provider"))):
    institutions = await InstitutionRepository.get_institutions()
    return {"Ok": True, "Institutions": institutions}