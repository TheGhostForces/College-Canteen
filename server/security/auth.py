from fastapi import HTTPException, status, Request, Depends
from jose import jwt, JWTError
import settings
from database.repository import UsersRepository


def create_access_token(data: dict):
    to_encode = data.copy()
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt

async def get_current_student_from_token(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token = token.replace("Bearer ", "")

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=settings.ALGORITHM)
        user_id: int = int(payload.get("sub"))

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token data",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired or is invalid",
        )

    student = await UsersRepository.get_student(user_id=user_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return student

async def get_current_user_from_token(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token = token.replace("Bearer ", "")

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=settings.ALGORITHM)
        user_id: int = int(payload.get("sub"))
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token data",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired or is invalid",
        )

    user = await UsersRepository.get_user(user_id=user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user

def require_role(required_role: str):
    async def role_checker(current_user = Depends(get_current_user_from_token)):
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    return role_checker

def require_student_role():
    async def student_checker(
        current_user = Depends(get_current_user_from_token),
        current_student = Depends(get_current_student_from_token)
    ):
        if current_user.role != "student":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_student
    return student_checker