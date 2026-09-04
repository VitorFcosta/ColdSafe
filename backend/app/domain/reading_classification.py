"""Pure domain rules for reading classification and freshness."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ReadingStatus(StrEnum):
    """Status values shared by persistence and the HTTP contract."""

    NORMAL = "normal"
    ATTENTION = "attention"
    CRITICAL = "critical"
    NO_DATA = "no_data"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class TemperatureThresholds:
    """Configurable demonstrative temperature thresholds."""

    min_c: float = 2.0
    max_c: float = 8.0
    attention_margin_c: float = 0.5


@dataclass(frozen=True, slots=True)
class Freshness:
    """Age of a reading at the instant it was assessed."""

    is_stale: bool
    age_seconds: float


@dataclass(frozen=True, slots=True)
class ReadingAssessment:
    """Classification result for a valid reading or absence of data."""

    status: ReadingStatus
    freshness: Freshness | None


DEFAULT_THRESHOLDS = TemperatureThresholds()
DEFAULT_STALE_AFTER_SECONDS = 30.0


def assess_reading(
    *,
    temperature_c: float | None,
    received_at: datetime | None,
    now: datetime,
    thresholds: TemperatureThresholds = DEFAULT_THRESHOLDS,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> ReadingAssessment:
    """Apply no-data, freshness, and temperature rules in precedence order."""

    if temperature_c is None and received_at is None:
        return ReadingAssessment(status=ReadingStatus.NO_DATA, freshness=None)
    if temperature_c is None or received_at is None:
        raise ValueError("temperature_c and received_at must be provided together")
    if received_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("received_at and now must be timezone-aware")

    age_seconds = (now - received_at).total_seconds()
    if age_seconds < 0:
        raise ValueError("received_at cannot be in the future")

    freshness = Freshness(
        is_stale=age_seconds > stale_after_seconds,
        age_seconds=age_seconds,
    )
    if freshness.is_stale:
        return ReadingAssessment(status=ReadingStatus.STALE, freshness=freshness)

    status = _classify_temperature(temperature_c, thresholds)
    return ReadingAssessment(status=status, freshness=freshness)


def _classify_temperature(
    temperature_c: float,
    thresholds: TemperatureThresholds,
) -> ReadingStatus:
    if temperature_c < thresholds.min_c or temperature_c > thresholds.max_c:
        return ReadingStatus.CRITICAL
    if (
        temperature_c <= thresholds.min_c + thresholds.attention_margin_c
        or temperature_c >= thresholds.max_c - thresholds.attention_margin_c
    ):
        return ReadingStatus.ATTENTION
    return ReadingStatus.NORMAL
