"""Доменные ошибки.

Слой данных и бизнес-правила не знают про HTTP: они бросают эти исключения,
а в `app.main` они превращаются в ответ `{"detail": "..."}` с нужным статусом.
"""


class AppError(Exception):
    status_code = 500

    def __init__(self, detail: str | dict):
        super().__init__(detail)
        self.detail = detail


class BadRequestError(AppError):
    status_code = 400


class UnauthorizedError(AppError):
    status_code = 401


class ForbiddenError(AppError):
    status_code = 403


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class TooManyRequestsError(AppError):
    status_code = 429


class BadGatewayError(AppError):
    status_code = 502
