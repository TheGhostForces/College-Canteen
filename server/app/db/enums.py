import enum


class OrderStatus(enum.Enum):
    IN_PROGRESS = "in_progress"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    EXPIRED = "expired"


class UserRole(enum.Enum):
    STUDENT = "student"
    PROVIDER = "provider"
    OPERATOR = "operator"
    ADMIN = "admin"
