from pydantic import BaseModel

from app.schemas.common import OkResponse


class LoginCodeRequested(OkResponse):
    user_id: int
    tmp_code_id: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str | None = None
