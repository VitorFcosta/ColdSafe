"""Run one private AMQP consumer; generation and training are offline."""
import argparse
import logging
import signal
from threading import Event

import psycopg
from pydantic import ValidationError

from backend.app.amqp.jobs import JobWorker
from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import initialize_schema
from backend.app.services.jobs import JobService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', required=True, choices=('generation', 'training'))
    role = parser.parse_args().role
    logging.basicConfig(level=logging.INFO)
    settings = RuntimeSettings()
    password = getattr(settings, f'rabbitmq_{role}_password')
    if password is None:
        parser.error(f'RABBITMQ_{role.upper()}_PASSWORD is required')
    initialize_schema(settings)
    handler = None
    if role == 'generation':
        from backend.app.services.generation import GenerationHandler
        handler = GenerationHandler(settings, artifact_root=settings.job_artifact_root)
    else:
        from backend.app.services.training import TrainingHandler
        handler = TrainingHandler(settings, artifact_root=settings.job_artifact_root,
                                  training_artifact_root=settings.training_artifact_root)
    worker = JobWorker(JobService(settings, artifact_root=settings.job_artifact_root,
                                 training_artifact_root=settings.training_artifact_root), role,
                       host=settings.rabbitmq_host, port=settings.rabbitmq_port,
                       password=password.get_secret_value(), handler=handler)
    shutdown = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: shutdown.set())
    worker.run(shutdown)


if __name__ == '__main__':
    try:
        main()
    except (psycopg.Error, ValidationError, OSError) as error:
        logging.getLogger(__name__).error('Job worker startup failed: type=%s', type(error).__name__)
        raise SystemExit(1) from None
