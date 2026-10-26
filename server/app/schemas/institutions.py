from app.schemas.common import OkResponse, OrmModel


class InstitutionOut(OrmModel):
    id: int
    name: str


class InstitutionsResponse(OkResponse):
    Institutions: list[InstitutionOut]
