from pydantic import Field, SecretStr
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

    influxdb_url: str = Field(min_length=1)
    influxdb_org: str = Field(min_length=1)
    influxdb_bucket: str = Field(min_length=1)
    influxdb_token: SecretStr = Field(min_length=1)

    @property
    def allowed_cors_origins(self) -> tuple[str, ...]:
        return tuple(
            origin.strip().rstrip("/")
            for origin in self.cors_origins.split(",")
            if origin.strip()
        )
