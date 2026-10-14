from fastapi import Request
from fastapi.responses import JSONResponse

class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400,
                 retryable: bool = False, details: dict | None = None):
        self.code, self.message, self.status = code, message, status
        self.retryable, self.details = retryable, details or {}

async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"error": {
        "code": exc.code, "message": exc.message,
        "retryable": exc.retryable, "details": exc.details}})