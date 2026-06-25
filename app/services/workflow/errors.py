"""Excepciones del motor de workflow."""
from __future__ import annotations

from fastapi import HTTPException, status


class WorkflowError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
