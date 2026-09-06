"""Construction and lifecycle of the real InfluxDB repository client."""

from contextlib import suppress
from dataclasses import dataclass, field
from urllib.parse import urlparse

from influxdb_client import InfluxDBClient
from influxdb_client.client.exceptions import InfluxDBError
from influxdb_client.client.write_api import SYNCHRONOUS
from urllib3.exceptions import HTTPError

from backend.app.repositories.influxdb import InfluxReadingRepository


@dataclass(frozen=True, slots=True)
class InfluxSettings:
    """Validated connection settings with a redacted authentication token."""

    url: str
    org: str
    bucket: str
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("url", "org", "bucket", "token"):
            value = getattr(self, name).strip()
            if not value:
                raise ValueError(f"{name} must not be empty")
            object.__setattr__(self, name, value)

        parsed_url = urlparse(self.url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("url must use http or https")
        if parsed_url.username is not None or parsed_url.password is not None:
            raise ValueError("url must not contain credentials")
        if parsed_url.query or parsed_url.fragment:
            raise ValueError("url must not contain query or fragment")


@dataclass(frozen=True, slots=True)
class InfluxRepositoryResources:
    """Repository plus the resources that must be closed at application shutdown."""

    repository: InfluxReadingRepository
    write_api: object = field(repr=False)
    client: object = field(repr=False)

    def is_ready(self) -> bool:
        """Return a safe readiness signal without exposing connection details."""

        try:
            return bool(self.client.ping())
        except (InfluxDBError, HTTPError, OSError):
            return False

    def close(self) -> None:
        """Close the write API before its owning client, even if flushing fails."""

        try:
            self.write_api.close()
        finally:
            self.client.close()


def create_influx_repository(settings: InfluxSettings) -> InfluxRepositoryResources:
    """Build an InfluxDB-backed repository using synchronous writes."""

    client = InfluxDBClient(
        url=settings.url,
        token=settings.token,
        org=settings.org,
    )
    write_api = None
    try:
        write_api = client.write_api(write_options=SYNCHRONOUS)
        query_api = client.query_api()
    except Exception:
        if write_api is not None:
            with suppress(Exception):
                write_api.close()
        with suppress(Exception):
            client.close()
        raise

    repository = InfluxReadingRepository(
        write_api=write_api,
        query_api=query_api,
        bucket=settings.bucket,
        org=settings.org,
    )
    return InfluxRepositoryResources(
        repository=repository,
        write_api=write_api,
        client=client,
    )
