import asyncio
import logging
from datetime import timedelta

from fastapi import APIRouter, Response

from app.api.deps import BasketRepo, LoginCodesRepo, UsersRepo
from app.core.config import get_settings
from app.core.exceptions import BadGatewayError, BadRequestError, NotFoundError, TooManyRequestsError, UnauthorizedError
from app.core.security import create_access_token, generate_login_code, verify_login_code
from app.core.timeutils import now_local
from app.schemas.auth import LoginCodeConfirm, LoginCodeRequest, LoginCodeRequested, TokenResponse
from app.services.mailer import send_login_code

logger = logging.getLogger("canteen.auth")
router = APIRouter(prefix="/auth", tags=["Авторизация"])


def _too_many_attempts(expires_at) -> TooManyRequestsError:
    remaining = max(expires_at - now_local(), timedelta(0))
    minutes, seconds = divmod(int(remaining.total_seconds()), 60)
    return TooManyRequestsError(f"Exceeded the number of requests. Try again after {minutes:02d}:{seconds:02d}")


@router.post("/generate", response_model=LoginCodeRequested, summary="Отправить код входа на почту")
async def request_login_code(body: LoginCodeRequest, users: UsersRepo, codes: LoginCodesRepo):
    settings = get_settings()
    user = await users.get_by_email(str(body.email))
    if user is None:
        raise NotFoundError("There is no such email")

    login_code = await codes.get_latest(user.id)
    if login_code is None:
        code = generate_login_code()
        login_code = await codes.create(user.id, code)
        try:
            # resend - синхронная библиотека, поэтому в отдельном потоке (не блокируем event loop)
            await asyncio.to_thread(send_login_code, user.email, code)
        except Exception:
            logger.error("Не удалось отправить код входа")
            await codes.mark_used(login_code.id)
            raise BadGatewayError("Failed to send the code, try again later") from None
    elif login_code.attempts >= settings.login_code_max_attempts:
        raise _too_many_attempts(login_code.expires_at)
    elif login_code.expires_at - now_local() < timedelta(minutes=2):
        await codes.extend(login_code.id)

    return LoginCodeRequested(user_id=user.id, tmp_code_id=login_code.id)


@router.post("/confirm", response_model=TokenResponse, summary="Подтвердить код и войти")
async def confirm_login_code(
    body: LoginCodeConfirm,
    response: Response,
    users: UsersRepo,
    codes: LoginCodesRepo,
    baskets: BasketRepo,
):
    settings = get_settings()
    user = await users.get_by_id(body.user_id)
    login_code = await codes.get_latest(body.user_id, body.temporary_code_id, only_active=False)
    if user is None or login_code is None:
        raise UnauthorizedError("Unauthorized")
    if login_code.used_at is not None:
        raise BadRequestError("Code already used")
    if login_code.expires_at < now_local():
        raise UnauthorizedError("Code expired")

    # попытка списывается атомарно ДО проверки кода: параллельными запросами лимит не обойти
    if not await codes.consume_attempt(login_code.id):
        raise _too_many_attempts(login_code.expires_at)
    if not verify_login_code(body.code, login_code.code_hash):
        raise UnauthorizedError("Incorrect code")

    student = None
    if user.role == "student":
        student = await users.get_student_by_user_id(user.id)
        if student is None:
            raise BadRequestError("Your data has not been verified, please contact the administrator")

    if not await codes.mark_used(login_code.id):
        raise BadRequestError("Code already used")

    if student is not None and await baskets.get_by_student(student.id) is None:
        await baskets.create_for_student(student.id)

    token = create_access_token(user.id, user.role)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.access_token_ttl_days * 24 * 3600,
    )
    return TokenResponse(access_token=token, token_type="bearer", role=user.role)


@router.post("/logout", summary="Выйти из аккаунта")
async def logout(response: Response):
    settings = get_settings()
    response.delete_cookie("access_token", secure=settings.cookie_secure, httponly=True, samesite="lax")
    return {"message": "Successfully logged out"}
