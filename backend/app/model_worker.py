"""Run the private model activation consumer with the inference credential."""
import argparse
import logging
import signal
from threading import Event

import psycopg
from pydantic import ValidationError

from backend.app.amqp.models import ModelWorker
from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import initialize_schema
from backend.app.services.models import ModelService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = RuntimeSettings()
    password = settings.rabbitmq_inference_password
    if password is None:
        parser.error('RABBITMQ_INFERENCE_PASSWORD is required')
    initialize_schema(settings)
    service = ModelService(settings, artifact_root=settings.training_artifact_root)
    worker = ModelWorker(service, host=settings.rabbitmq_host, port=settings.rabbitmq_port,
                         password=password.get_secret_value())
    shutdown = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: shutdown.set())
    worker.run(shutdown)


if __name__ == '__main__':
    try:
        main()
    except (psycopg.Error, ValidationError, OSError) as error:
        logging.getLogger(__name__).error('Model worker startup failed: type=%s', type(error).__name__)
        raise SystemExit(1) from None
