import hashlib
import secrets
import string
from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_numeric_code(length=6):
    numbers = string.digits
    return ''.join(secrets.choice(numbers) for _ in range(length))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password