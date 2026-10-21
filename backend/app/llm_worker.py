"""Preload the local CPU model while no heavy generation/training job holds memory."""
import argparse
import logging
import signal
from threading import Event

from pydantic import ValidationError

from backend.app.config.settings import RuntimeSettings
from backend.app.services.llm import LlmService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = RuntimeSettings()
    if settings.ollama_url is None:
        parser.error('OLLAMA_URL is required')
    shutdown = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: shutdown.set())
    LlmService(settings).run(shutdown)


if __name__ == '__main__':
    try:
        main()
    except (ValidationError, OSError, ValueError) as error:
        logging.getLogger(__name__).error('Local model coordinator failed: type=%s', type(error).__name__)
        raise SystemExit(1) from None
