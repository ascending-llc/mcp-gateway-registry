from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def format_validation_error(exc: Any) -> str:
    """
    Format validation error for fastapi
    """
    errors = exc.errors() if hasattr(exc, "errors") else []
    messages: list[str] = []
    for err in errors:
        msg = err.get("msg", "")
        loc = err.get("loc", [])
        field = loc[-1] if isinstance(loc, (list, tuple)) and loc else ""
        field_str = str(field) if field is not None else ""
        if msg:
            if field_str:
                messages.append(f"{field_str}: {msg}")
            else:
                messages.append(msg)

    message = " | ".join(messages) if messages else "Invalid request"
    if len(message) > 50:
        message = f"{message[:50]}..."
    return message


def register_validation_exception_handler(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": format_validation_error(exc)})
