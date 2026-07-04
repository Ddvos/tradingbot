"""HTTP routes for the live feature — a stub until the runner exists.

Slice 5 replaces this with real state read from the DB flags the bot polls.
"""

from fastapi import APIRouter

from tradingbot.api.features.live.schemas import LiveStatus

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/status")
def get_live_status() -> LiveStatus:
    return LiveStatus(state="offline", detail="Live runner arrives in Slice 5")
