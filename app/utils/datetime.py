from datetime import UTC, date, datetime, time, timedelta, timezone

from dateutil.parser import ParserError, parse

constant_datetime = datetime.combine(
    date(year=2023, month=1, day=21), time(hour=8), timezone(offset=timedelta(hours=0))
)


def convert_datetime(date: str) -> datetime:
    try:
        parsed_date = parse(date)
        if parsed_date.tzinfo is None:
            # Feed dates without an offset are assumed to already be in UTC.
            return parsed_date.replace(tzinfo=UTC)
        return parsed_date.astimezone(UTC)
    except ParserError:
        # FIXME:
        return constant_datetime
