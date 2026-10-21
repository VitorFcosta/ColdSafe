"""Local CPU model lifecycle; jobs and preloading share PostgreSQL coordination."""
import json
import logging
from http.client import HTTPException
from threading import Event
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import psycopg

from backend.app.repositories.postgres import connect
from backend.app.services.jobs import HEAVY_JOB_LOCK

LOGGER = logging.getLogger(__name__)
MODEL = 'llama3.2:1b-instruct-q4_K_M'
LOADING_LOCK = 2026103001


class OllamaUnavailable(OSError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        raise HTTPError(request.full_url if request else '', code, 'Redirect refused', headers, response)


class OllamaClient:
    def __init__(self, url: str):
        self.url = url.rstrip('/')
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path: str, payload: dict | None = None, *, timeout: int = 2) -> dict:
        request = Request(self.url + path,
                          data=json.dumps(payload).encode() if payload is not None else None,
                          headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                body = response.read(65_537)
                if len(body) > 65_536:
                    raise ValueError('Oversized Ollama response')
                result = json.loads(body)
            if not isinstance(result, dict) or 'error' in result:
                raise ValueError('Invalid Ollama response')
            return result
        except (OSError, URLError, HTTPException, ValueError, RecursionError):
            raise OllamaUnavailable('Local model service unavailable') from None

    def loaded(self) -> list[dict]:
        models = self.request('/api/ps').get('models')
        if (not isinstance(models, list) or len(models) > 16 or any(
                not isinstance(row, dict) or not isinstance(row.get('name'), str) or not row['name']
                for row in models)):
            raise OllamaUnavailable('Invalid local model state')
        return models

    @staticmethod
    def ready(models: list[dict]) -> bool:
        return (len(models) == 1 and models[0]['name'] == MODEL
                and models[0].get('size_vram') == 0 and models[0].get('context_length') == 1024)

    def preload(self) -> None:
        self.request('/api/generate', {
            'model': MODEL, 'prompt': '', 'stream': False, 'keep_alive': -1,
            'options': {'num_ctx': 1024, 'num_gpu': 0, 'num_thread': 2},
        }, timeout=180)
        if not self.ready(self.loaded()):
            raise OllamaUnavailable('Local CPU model not ready')

    def unload(self) -> None:
        models = self.loaded()
        if not models:
            return
        for row in models:
            result = self.request('/api/generate', {
                'model': row['name'], 'prompt': '', 'stream': False, 'keep_alive': 0,
            }, timeout=180)
            if result.get('done_reason') != 'unload' or result.get('done') is not True:
                raise OllamaUnavailable('Local model unload unconfirmed')
        if self.loaded():
            raise OllamaUnavailable('Local model still resident')

    def installed(self) -> bool:
        models = self.request('/api/tags').get('models')
        if not isinstance(models, list) or any(not isinstance(row, dict) for row in models):
            raise OllamaUnavailable('Invalid local model inventory')
        return any(row.get('name') == MODEL for row in models)


class LlmService:
    def __init__(self, settings):
        self.settings = settings
        self.client = OllamaClient(settings.ollama_url) if settings.ollama_url is not None else None

    def status(self) -> dict:
        state = 'disabled'
        if self.client is not None:
            try:
                with connect(self.settings) as connection:
                    connection.autocommit = True
                    loading_free = connection.execute('SELECT pg_try_advisory_lock(%s)', (LOADING_LOCK,)).fetchone()[0]
                    if loading_free:
                        connection.execute('SELECT pg_advisory_unlock(%s)', (LOADING_LOCK,))
                    heavy_free = loading_free and connection.execute(
                        'SELECT pg_try_advisory_lock(%s)', (HEAVY_JOB_LOCK,),
                    ).fetchone()[0]
                    if heavy_free:
                        connection.execute('SELECT pg_advisory_unlock(%s)', (HEAVY_JOB_LOCK,))
                    if not loading_free:
                        state = 'loading'
                    elif not heavy_free:
                        state = 'paused'
                    elif connection.execute("SELECT EXISTS(SELECT 1 FROM jobs WHERE status='running')").fetchone()[0]:
                        state = 'paused'
                    elif connection.execute('SELECT EXISTS(SELECT 1 FROM llm_memory_guard)').fetchone()[0]:
                        state = 'unavailable'
                    elif self.client.ready(self.client.loaded()):
                        state = 'ready'
                    else:
                        state = 'loading' if self.client.installed() else 'model_missing'
            except (psycopg.Error, OllamaUnavailable):
                state = 'unavailable'
        return {'state': state, 'model': MODEL}

    def tick(self) -> bool:
        if self.client is None:
            return False
        with connect(self.settings) as connection:
            connection.autocommit = True
            if not connection.execute('SELECT pg_try_advisory_lock(%s)', (HEAVY_JOB_LOCK,)).fetchone()[0]:
                return False
            # A lost job session releases its lock before a surviving executor notices.
            if connection.execute("SELECT EXISTS(SELECT 1 FROM jobs WHERE status='running')").fetchone()[0]:
                return False
            if connection.execute('SELECT EXISTS(SELECT 1 FROM llm_memory_guard)').fetchone()[0]:
                return False
            if self.client.ready(self.client.loaded()):
                return True
            if not connection.execute('SELECT pg_try_advisory_lock(%s)', (LOADING_LOCK,)).fetchone()[0]:
                return False
            if not self.client.installed():
                return False
            self.client.unload()
            # Persist before HTTP: /api/ps can omit a loader still allocating memory.
            connection.execute('INSERT INTO llm_memory_guard(id) VALUES(1)')
            self.client.preload()
            # Only the original live session may clear this guard after confirmed completion.
            connection.execute('DELETE FROM llm_memory_guard WHERE id=1')
            return True

    def run(self, shutdown: Event) -> None:
        while not shutdown.is_set():
            try:
                self.tick()
            except (psycopg.Error, OllamaUnavailable) as error:
                LOGGER.warning('Local model preparation failed: type=%s', type(error).__name__)
            shutdown.wait(2)
