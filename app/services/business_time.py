from datetime import datetime
from zoneinfo import ZoneInfo


BUSINESS_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def business_now() -> datetime:
    """Return business wall time as naive local time for legacy SQL columns."""
    return datetime.now(BUSINESS_TIMEZONE).replace(tzinfo=None)
