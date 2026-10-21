from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Response
from database.repository import UsersRepository, TemporaryCodeRepository, StudentBasketRepository
from libs.generator import generate_numeric_code, verify_password
from libs.sender import send_code_to_email
from schemas import Token, UniversalStudent
from security.auth import create_access_token


router = APIRouter(
    prefix="/auth",
    tags=["Эндпоинты для авторизации/выхода из аккаунта"],
)

@router.post("/generate", response_model=UniversalStudent)
async def generate_sms_code(email: str):
    existing_user = await UsersRepository.get_user(email=email)
    if not existing_user:
        raise HTTPException(status_code=404, detail="There is no such email")
    tmp_code = await TemporaryCodeRepository.get_temporary_code(existing_user.id)
    if not tmp_code:
        code = generate_numeric_code()
        send_code_to_email(existing_user.email, code)
        tmp_code = await TemporaryCodeRepository.set_temporary_code(existing_user.id, code)
    elif tmp_code.attempts >= 3:
        raise HTTPException(status_code=401, detail=
        f"Exceeded the number of requests. Try again after {str(tmp_code.expires_at - datetime.now()).split('.')[0].zfill(8)[-5:]}"
                            )
    elif tmp_code.expires_at - datetime.now() < timedelta(minutes=2):
        await TemporaryCodeRepository.extend_expires_at(tmp_code.id)
    print(existing_user.id)
    print(tmp_code.id)
    print({"Ok": True, "user_id": existing_user.id, "tmp_code_id": tmp_code.id})
    return {"Ok": True, "user_id": existing_user.id, "tmp_code_id": tmp_code.id}

@router.post("/confirm", response_model=Token)
async def confirm(user_id: int, temporary_code_id: int, code: str, response: Response = None):
    existing_user = await UsersRepository.get_user(user_id=user_id)
    if not existing_user:
        raise HTTPException(status_code=400, detail="There is no such id")

    tmp_code = await TemporaryCodeRepository.get_temporary_code(user_id, temporary_code_id)
    if not tmp_code:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if tmp_code.attempts >= 3:
        raise HTTPException(status_code=401, detail=
        f"Exceeded the number of requests. Try again after {str(tmp_code.expires_at - datetime.now()).split('.')[0].zfill(8)[-5:]}"
                            )

    if tmp_code.expires_at < datetime.now():
        raise HTTPException(status_code=401, detail="Code expired")

    if tmp_code.used_at is not None:
        raise HTTPException(status_code=400, detail="Code already used")

    if tmp_code.user_id != user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not verify_password(code, tmp_code.code_hash):
        await TemporaryCodeRepository.increment_attempts(tmp_code.id)
        raise HTTPException(status_code=401, detail="Incorrect code")

    await TemporaryCodeRepository.mark_code_as_used(tmp_code.id)

    if existing_user.role == "student":
        student = await UsersRepository.get_student(user_id=existing_user.id)

        if not student:
            raise HTTPException(status_code=400, detail="Your data has not been verified, please contact the administrator")

        basket = await StudentBasketRepository.get_basket_by_student_id(student.id)

        if basket is None:
            await StudentBasketRepository.create_student_basket(student.id)

    access_token = create_access_token(
        data={"sub": str(existing_user.id),
              "role": str(existing_user.role),
              },
    )

    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=True,
        samesite="lax",
    )

    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Successfully logged out"}
