from datetime import UTC, datetime

import pytest

from app.utils.datetime import constant_datetime, convert_datetime


@pytest.mark.parametrize(
    ("raw_date", "expected"),
    [
        (
            "Wed, 09 Sep 2026 12:00:00 +0300",
            datetime(2026, 9, 9, 9, tzinfo=UTC),
        ),
        (
            "Wed, 09 Sep 2026 12:00:00 -0400",
            datetime(2026, 9, 9, 16, tzinfo=UTC),
        ),
        (
            "Wed, 09 Sep 2026 12:00:00 +0000",
            datetime(2026, 9, 9, 12, tzinfo=UTC),
        ),
        (
            "2026-09-09 12:00:00",
            datetime(2026, 9, 9, 12, tzinfo=UTC),
        ),
    ],
)
def test_convert_datetime_preserves_the_instant(
    raw_date: str, expected: datetime
) -> None:
    assert convert_datetime(raw_date) == expected


def test_convert_datetime_uses_fallback_for_invalid_input() -> None:
    assert convert_datetime("not a date") == constant_datetime
