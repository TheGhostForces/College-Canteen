import enum


class OrderStatus(enum.Enum):
    IN_PROGRESS = "in_progress"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    EXPIRED = "expired"


class DishCategory(enum.Enum):
    FIRST = "Первое"
    SECOND = "Второе"
    DRINK = "Напитки"
    DESSERT = "Десерт"
    SNACKS = "Снеки"


class UserRole(enum.Enum):
    STUDENT = "student"
    PROVIDER = "provider"
    OPERATOR = "operator"
    ADMIN = "admin"
