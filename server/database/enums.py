import enum

class StatusOrder(enum.Enum):
    IN_PROGRESS = "in_progress"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    EXPIRED = "expired"

class CategoryForDishes(enum.Enum):
    First = "Первое"
    Second = "Второе"
    Drink = "Напитки"
    Dessert = "Десерт"
    Snacks = "Снеки"

class UserRoles(enum.Enum):
    STUDENT = "student"
    PROVIDER = "provider"
    OPERATOR = "operator"