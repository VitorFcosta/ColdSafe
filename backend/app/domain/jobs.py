"""Shared validation for private job requests, including non-HTTP producers."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter, field_validator

from backend.app.api.schemas import ApiModel

SensorType = Literal['ambient_temperature_c', 'humidity_percent', 'light_percent',
                     'vibration_rms_mm_s', 'motor_current_a', 'motor_temperature_c']
SENSOR_TYPES = ('ambient_temperature_c', 'humidity_percent', 'light_percent',
                'vibration_rms_mm_s', 'motor_current_a', 'motor_temperature_c')


class GenerationInput(ApiModel):
    job_type: Literal['generation']
    total_units: int = Field(strict=True, ge=1_000_000, le=2_000_000)
    seed: int = Field(default=42, strict=True, ge=0, le=2**32 - 1)
    environment_id: UUID | None = None
    equipment_count: int = Field(default=100, strict=True, ge=1, le=10_000)
    days: float = Field(default=30, strict=True, gt=0, le=3650, allow_inf_nan=False)
    sensor_types: list[SensorType] = Field(default_factory=lambda: list(SENSOR_TYPES), min_length=1, max_length=6)
    failure_fraction: float = Field(default=0.6, strict=True, ge=0, le=1, allow_inf_nan=False)
    failure_modes: list[Literal['bearing_wear', 'imbalance']] = Field(
        default_factory=lambda: ['bearing_wear', 'imbalance'], min_length=1, max_length=2)
    operating_modes: list[Literal['normal', 'heavy', 'cycling']] = Field(
        default_factory=lambda: ['normal', 'heavy', 'cycling'], min_length=1, max_length=3)
    noise_scale: float = Field(default=1, strict=True, ge=0, le=10, allow_inf_nan=False)
    missing_rate: float = Field(default=0.01, strict=True, ge=0, le=1, allow_inf_nan=False)
    outlier_rate: float = Field(default=0.002, strict=True, ge=0, le=1, allow_inf_nan=False)

    @field_validator('sensor_types', 'failure_modes', 'operating_modes')
    @classmethod
    def unique_choices(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError('Choices must be distinct')
        return values


class TrainingInput(ApiModel):
    job_type: Literal['training']
    dataset_id: UUID
    environment_id: UUID | None = None


JobInput = Annotated[GenerationInput | TrainingInput, Field(discriminator='job_type')]
JOB_REQUEST = TypeAdapter(JobInput)
