from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import OkResponse


class LoginCodeRequested(OkResponse):
    user_id: int
    tmp_code_id: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str | None = None


class LoginCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class LoginCodeConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int = Field(gt=0)
    temporary_code_id: int = Field(gt=0)
    code: str = Field(pattern=r"^\d{6}$", min_length=6, max_length=6)
