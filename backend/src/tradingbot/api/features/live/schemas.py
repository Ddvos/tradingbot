"""Response schemas for the live feature (Pydantic at the boundary)."""

from typing import Literal

from pydantic import BaseModel


class LiveStatus(BaseModel):
    state: Literal["offline"]
    """Only "offline" exists until the live runner lands in Slice 5."""

    detail: str
