"""Run private live inference and model activation in the same worker."""
import argparse
import logging
import signal
from threading import Event

import psycopg
from jsonschema import ValidationError as SchemaError
from pydantic import ValidationError

from backend.app.amqp.inference import InferenceWorker
from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import initialize_schema
from backend.app.services.inference import InferenceService
from backend.app.services.models import ModelService
from gateway.bridge import PostgresScope
from simulator.model import strict_json, validate_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('pika').setLevel(logging.CRITICAL)
    settings = RuntimeSettings()
    if any(value is None for value in (settings.rabbitmq_inference_password,
                                       settings.aiot_catalog_path, settings.aiot_owner_user_id)):
        parser.error('Private inference credential, AIoT catalog and owner are required')
    catalog = strict_json(settings.aiot_catalog_path.read_bytes())
    validate_catalog(catalog)
    scope = PostgresScope({
        'host': settings.postgres_host, 'port': settings.postgres_port,
        'dbname': settings.postgres_db, 'user': settings.postgres_user,
        'password': settings.postgres_password.get_secret_value(),
    }, str(settings.aiot_owner_user_id))
    initialize_schema(settings)
    models = ModelService(settings, artifact_root=settings.training_artifact_root)
    models.sync_active(settings.aiot_owner_user_id)
    inference = InferenceService(settings, catalog, settings.aiot_owner_user_id, models)
    worker = InferenceWorker(models, inference, catalog, scope, host=settings.rabbitmq_host,
                             port=settings.rabbitmq_port,
                             password=settings.rabbitmq_inference_password.get_secret_value())
    shutdown = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: shutdown.set())
    worker.run(shutdown)


if __name__ == '__main__':
    try:
        main()
    except (psycopg.Error, ValidationError, SchemaError, OSError, ValueError, RuntimeError) as error:
        logging.getLogger(__name__).error('Inference worker stopped: type=%s', type(error).__name__)
        raise SystemExit(1) from None
