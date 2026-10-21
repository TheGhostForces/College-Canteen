import os
from dotenv import load_dotenv
from uvicorn.config import LOGGING_CONFIG


CUSTOM_LOGGING_CONFIG = LOGGING_CONFIG.copy()

CUSTOM_LOGGING_CONFIG["formatters"]["access"]["fmt"] = (
    '%(asctime)s | %(levelname)-8s | %(client_addr)s | '
    '"%(request_line)s" | %(status_code)s'
)

CUSTOM_LOGGING_CONFIG["formatters"]["default"]["fmt"] = (
    '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
)

load_dotenv()


ALGORITHM = "HS256"
engine = os.getenv("ENGINE")
SECRET_KEY = os.getenv("SECRET_KEY")
API_FOR_SENDER = os.getenv("API_FOR_SENDER")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")