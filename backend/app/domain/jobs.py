"""Shared validation for private job requests, including non-HTTP producers."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter

from backend.app.api.schemas import ApiModel


class GenerationInput(ApiModel):
    job_type: Literal['generation']
    total_units: int = Field(strict=True, ge=1_000_000, le=2_000_000)
    seed: int = Field(default=42, strict=True, ge=0, le=2**32 - 1)
    environment_id: UUID | None = None


class TrainingInput(ApiModel):
    job_type: Literal['training']
    dataset_id: UUID
    environment_id: UUID | None = None


JobInput = Annotated[GenerationInput | TrainingInput, Field(discriminator='job_type')]
JOB_REQUEST = TypeAdapter(JobInput)
