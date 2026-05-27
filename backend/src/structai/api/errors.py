"""RFC 9457 problem-details error responses."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    def __init__(self, *, status: int, title: str, detail: str, type_: str = "about:blank"):
        super().__init__(status_code=status, detail=detail)
        self.type_ = type_
        self.title = title


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": exc.type_,
            "title": exc.title,
            "status": exc.status_code,
            "detail": exc.detail,
            "instance": str(request.url.path),
        },
        media_type="application/problem+json",
    )
