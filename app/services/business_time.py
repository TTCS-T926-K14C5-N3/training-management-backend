from datetime import datetime
from zoneinfo import ZoneInfo


BUSINESS_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def business_now() -> datetime:
    return datetime.now(BUSINESS_TIMEZONE)


def business_now_naive() -> datetime:
    return business_now().replace(tzinfo=None)
