"""Conservative exchange-session availability policies."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import exchange_calendars as xcals


class DailyTradabilityPolicy:
    """Map publication to the earliest conservative daily outcome interval."""

    version = "sec-daily-v0.1"

    def __init__(
        self,
        *,
        processing_latency: timedelta,
        calendar_name: str = "XNYS",
    ) -> None:
        if processing_latency < timedelta(0):
            raise ValueError("processing_latency cannot be negative")
        self.processing_latency = processing_latency
        self.calendar = xcals.get_calendar(calendar_name)
        self.market_timezone = ZoneInfo("America/New_York")

    def tradable_at(
        self,
        source_published_at: datetime,
        *,
        trading_resumed_at: datetime | None = None,
    ) -> datetime:
        published = _aware_utc(source_published_at, "source_published_at")
        eligible = self._next_daily_interval(published)
        if trading_resumed_at is not None:
            resumed = _aware_utc(trading_resumed_at, "trading_resumed_at")
            if resumed > eligible:
                eligible = self._next_daily_interval(resumed)
        return eligible

    def _next_daily_interval(self, instant: datetime) -> datetime:
        local_date = instant.astimezone(self.market_timezone).date()
        session = self.calendar.date_to_session(local_date, direction="next")
        session_open = self.calendar.session_open(session).to_pydatetime()
        session_close = self.calendar.session_close(session).to_pydatetime()

        if instant < session_open:
            return (session_open + self.processing_latency).astimezone(timezone.utc)
        if instant < session_close:
            next_session = self.calendar.next_session(session)
            return self.calendar.session_open(next_session).to_pydatetime().astimezone(
                timezone.utc
            )
        next_session = self.calendar.next_session(session)
        return (
            self.calendar.session_open(next_session).to_pydatetime()
            + self.processing_latency
        ).astimezone(timezone.utc)


def _aware_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)
