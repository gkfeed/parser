from datetime import UTC, date, datetime, time, timedelta, timezone

from dateutil.parser import ParserError, parse

constant_datetime = datetime.combine(
    date(year=2023, month=1, day=21), time(hour=8), timezone(offset=timedelta(hours=0))
)


def parse_datetime(date: str) -> datetime:
    """Parse a supplied date as UTC, raising ValueError for invalid dates."""
    try:
        parsed_date = parse(date)
    except OverflowError as error:
        raise ValueError(f"Invalid date {date!r}: {error}") from error

    if parsed_date.tzinfo is None:
        # Feed dates without an offset are assumed to already be in UTC.
        return parsed_date.replace(tzinfo=UTC)
    return parsed_date.astimezone(UTC)


def convert_datetime(date: str) -> datetime:
    """Legacy fallback wrapper. Feed parsers must use parse_datetime instead."""
    try:
        return parse_datetime(date)
    except ParserError:
        return constant_datetime
