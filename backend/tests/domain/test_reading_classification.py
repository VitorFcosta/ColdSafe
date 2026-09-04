from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from backend.app.domain.reading_classification import (
    ReadingStatus,
    assess_reading,
)


NOW = datetime(2026, 9, 4, 18, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("temperature_c", "expected_status"),
    [
        (1.999, ReadingStatus.CRITICAL),
        (8.001, ReadingStatus.CRITICAL),
        (2.0, ReadingStatus.ATTENTION),
        (2.5, ReadingStatus.ATTENTION),
        (7.5, ReadingStatus.ATTENTION),
        (8.0, ReadingStatus.ATTENTION),
        (2.501, ReadingStatus.NORMAL),
        (7.499, ReadingStatus.NORMAL),
    ],
)
def test_classifies_temperature_at_operational_boundaries(
    temperature_c,
    expected_status,
):
    assessment = assess_reading(
        temperature_c=temperature_c,
        received_at=NOW,
        now=NOW,
    )

    assert assessment.status is expected_status


def test_returns_no_data_when_no_valid_reading_exists():
    assessment = assess_reading(
        temperature_c=None,
        received_at=None,
        now=NOW,
    )

    assert assessment.status is ReadingStatus.NO_DATA
    assert assessment.freshness is None


@pytest.mark.parametrize(
    ("age", "expected_status", "expected_is_stale"),
    [
        (timedelta(seconds=30), ReadingStatus.CRITICAL, False),
        (timedelta(seconds=30, microseconds=1), ReadingStatus.STALE, True),
    ],
)
def test_stale_takes_precedence_only_after_thirty_seconds(
    age,
    expected_status,
    expected_is_stale,
):
    assessment = assess_reading(
        temperature_c=9.0,
        received_at=NOW - age,
        now=NOW,
    )

    assert assessment.status is expected_status
    assert assessment.freshness is not None
    assert assessment.freshness.is_stale is expected_is_stale
    assert assessment.freshness.age_seconds == age.total_seconds()


def test_assessment_and_freshness_are_immutable():
    assessment = assess_reading(
        temperature_c=5.0,
        received_at=NOW,
        now=NOW,
    )

    with pytest.raises(FrozenInstanceError):
        assessment.status = ReadingStatus.CRITICAL

    with pytest.raises(FrozenInstanceError):
        assessment.freshness.is_stale = True


@pytest.mark.parametrize(
    ("temperature_c", "received_at"),
    [(None, NOW), (5.0, None)],
)
def test_rejects_incomplete_readings(temperature_c, received_at):
    with pytest.raises(ValueError, match="together"):
        assess_reading(
            temperature_c=temperature_c,
            received_at=received_at,
            now=NOW,
        )


def test_rejects_naive_or_future_timestamps():
    with pytest.raises(ValueError, match="timezone-aware"):
        assess_reading(
            temperature_c=5.0,
            received_at=NOW.replace(tzinfo=None),
            now=NOW,
        )

    with pytest.raises(ValueError, match="future"):
        assess_reading(
            temperature_c=5.0,
            received_at=NOW + timedelta(microseconds=1),
            now=NOW,
        )
