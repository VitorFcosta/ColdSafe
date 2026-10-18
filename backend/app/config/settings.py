from pathlib import Path
from typing import Self
from uuid import UUID

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    mqtt_host: str = Field(min_length=1)
    mqtt_port: int = Field(ge=1, le=65_535)
    mqtt_topic: str = Field(min_length=1)
    mqtt_qos: int = Field(ge=1, le=1)
    mqtt_client_id: str = Field(min_length=1)
    mqtt_backend_username: str = Field(min_length=1)
    mqtt_backend_password: SecretStr = Field(min_length=1)

    cors_origins: str = ""
    auth_jwt_secret: SecretStr = Field(min_length=32)

    influxdb_url: str = Field(min_length=1)
    influxdb_org: str = Field(min_length=1)
    influxdb_bucket: str = Field(min_length=1)
    influxdb_token: SecretStr = Field(min_length=1)

    postgres_host: str = Field(min_length=1)
    postgres_port: int = Field(ge=1, le=65_535)
    postgres_db: str = Field(min_length=1)
    postgres_user: str = Field(min_length=1)
    postgres_password: SecretStr = Field(min_length=1)

    aiot_enabled: bool = False
    aiot_catalog_path: Path | None = None
    aiot_owner_user_id: UUID | None = None
    rabbitmq_host: str = Field(default="rabbitmq", min_length=1)
    rabbitmq_port: int = Field(default=5672, ge=1, le=65_535)
    rabbitmq_management_port: int = Field(default=15672, ge=1, le=65_535)
    rabbitmq_monitor_password: SecretStr | None = Field(default=None, min_length=1)
    rabbitmq_observability_password: SecretStr | None = Field(default=None, min_length=1)
    rabbitmq_commands_password: SecretStr | None = Field(default=None, min_length=1)
    rabbitmq_delivery_password: SecretStr | None = Field(default=None, min_length=1)
    rabbitmq_api_password: SecretStr | None = Field(default=None, min_length=1)
    rabbitmq_generation_password: SecretStr | None = Field(default=None, min_length=1)
    rabbitmq_training_password: SecretStr | None = Field(default=None, min_length=1)
    job_artifact_root: Path = Path('/app/artifacts')
    training_artifact_root: Path = Path('/app/training-artifacts')

    @model_validator(mode="after")
    def require_aiot_configuration(self) -> Self:
        if self.aiot_enabled and any(value is None for value in (
            self.aiot_catalog_path, self.aiot_owner_user_id,
            self.rabbitmq_commands_password, self.rabbitmq_delivery_password,
        )):
            raise ValueError("AIoT requires catalog, owner and private AMQP credentials")
        return self

    @property
    def allowed_cors_origins(self) -> tuple[str, ...]:
        return tuple(
            origin.strip().rstrip("/")
            for origin in self.cors_origins.split(",")
            if origin.strip()
        )
