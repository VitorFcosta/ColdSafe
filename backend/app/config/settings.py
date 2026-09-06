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

    influxdb_url: str = Field(min_length=1)
    influxdb_org: str = Field(min_length=1)
    influxdb_bucket: str = Field(min_length=1)
    influxdb_token: SecretStr = Field(min_length=1)
