from pydantic import BaseModel, ConfigDict


class OkResponse(BaseModel):
    """Базовый ответ. Имена полей (Ok, Orders, Student_ID...) - часть контракта с фронтендом, не менять."""

    Ok: bool = True


class OrmModel(BaseModel):
    """Базовый класс для моделей ответа, которые собираются прямо из ORM-объектов."""

    model_config = ConfigDict(from_attributes=True)
