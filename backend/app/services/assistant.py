"""Owner-only assistant orchestration; inference shares the heavy-job memory slot."""
import asyncio
from contextlib import aclosing
import hashlib
import json
import logging
from uuid import uuid4

import anyio
import psycopg
from psycopg.types.json import Jsonb

from backend.app.repositories.postgres import connect
from backend.app.services.assistant_context import AssistantContext
from backend.app.services.assistant_transport import AssistantTransport, GENERATION_TIMEOUT
from backend.app.services.jobs import HEAVY_JOB_LOCK
from backend.app.services.llm import MODEL, OllamaClient, OllamaUnavailable

LOGGER = logging.getLogger(__name__)


class AssistantError(Exception):
    def __init__(self, code: str, status: int = 503):
        self.code, self.status = code, status


def sse(event: str, data: dict) -> str:
    return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'


class AssistantService:
    def __init__(self, settings):
        self.settings = settings
        self.context = AssistantContext(settings)
        self.transport = AssistantTransport(settings.ollama_url) if settings.ollama_url else None

    def _audit(self, connection, owner, event, details):
        connection.execute(
            'INSERT INTO audit_events(actor_user_id,event_type,details) VALUES(%s,%s,%s)',
            (owner, event, Jsonb(details)),
        )

    def _admit(self, owner, question, request_id):
        # Serialize by owner across API processes, without a new rate-limit store.
        with connect(self.settings) as connection:
            connection.execute("SET LOCAL statement_timeout='3s'")
            connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 31))', (str(owner),))
            count = connection.execute(
                "SELECT count(*) FROM (SELECT 1 FROM audit_events WHERE actor_user_id=%s "
                "AND event_type='assistant.requested' AND occurred_at>clock_timestamp()-interval '1 minute' "
                'LIMIT 5) recent', (owner,),
            ).fetchone()[0]
            limited = count >= 5
            self._audit(connection, owner, 'assistant.limited' if limited else 'assistant.requested', {
                'request_id': request_id,
                **({'question_sha256': hashlib.sha256(question.encode()).hexdigest()} if limited
                   else {'question': question, 'model': MODEL}),
            })
        if limited:
            raise AssistantError('RATE_LIMITED', 429)

    def open(self, owner, question):
        identifier = str(uuid4())
        try:
            self._admit(owner, question, identifier)
        except psycopg.Error:
            raise AssistantError('LLM_UNAVAILABLE') from None
        connection = None
        try:
            if self.transport is None:
                raise AssistantError('LLM_DISABLED')
            connection = connect(self.settings)
            connection.autocommit = True
            connection.execute("SET statement_timeout='3s'")
            free = connection.execute('SELECT pg_try_advisory_lock(%s)', (HEAVY_JOB_LOCK,)).fetchone()[0]
            if not free:
                raise AssistantError('LLM_BUSY')
            if connection.execute("SELECT EXISTS(SELECT 1 FROM jobs WHERE status='running') "
                                  'OR EXISTS(SELECT 1 FROM llm_memory_guard)').fetchone()[0]:
                raise AssistantError('LLM_BUSY')
            client = OllamaClient(self.settings.ollama_url)
            if not client.ready(client.loaded()):
                raise AssistantError('LLM_NOT_READY')
            context = self.context.build(owner)
            # Keep a durable barrier if HTTP generation outlives its database session.
            connection.execute('INSERT INTO llm_memory_guard(id) VALUES(1)')
            return AssistantLease(self, connection, owner, identifier, question, context)
        except (AssistantError, OllamaUnavailable, psycopg.Error) as error:
            if connection is not None:
                connection.close()
            code = error.code if isinstance(error, AssistantError) else 'LLM_UNAVAILABLE'
            try:
                self.record(owner, identifier, code)
            except psycopg.Error:
                LOGGER.error('Assistant preflight outcome audit unavailable')
            raise AssistantError(code) from None
        except BaseException:
            if connection is not None:
                connection.close()
            raise

    def record(self, owner, identifier, outcome):
        with connect(self.settings) as connection:
            connection.execute("SET LOCAL statement_timeout='3s'")
            self._audit(connection, owner, 'assistant.finished', {'request_id': identifier, 'outcome': outcome})

    async def events(self, lease, authorized):
        outcome, completed = 'cancelled', False
        try:
            async with asyncio.timeout(GENERATION_TIMEOUT):
                async with aclosing(self.transport.stream(lease.question, lease.context)) as output:
                    async for delta in output:
                        await anyio.to_thread.run_sync(lease.check)
                        if not await anyio.to_thread.run_sync(authorized):
                            raise AssistantError('UNAUTHORIZED', 401)
                        yield sse('delta', {'text': delta})
                await anyio.to_thread.run_sync(lease.check)
                if not await anyio.to_thread.run_sync(authorized):
                    raise AssistantError('UNAUTHORIZED', 401)
                completed, outcome = True, 'completed'
        except TimeoutError:
            outcome = 'LLM_TIMEOUT'
        except (OllamaUnavailable, psycopg.Error):
            outcome = 'LLM_UNAVAILABLE'
        except AssistantError as error:
            outcome = error.code
        finally:
            with anyio.CancelScope(shield=True):
                cleaned = await self.close(lease, completed, outcome)
        if completed and cleaned:
            yield sse('done', {'request_id': lease.identifier})
        else:
            yield sse('error', {'code': outcome if outcome != 'completed' else 'LLM_UNAVAILABLE'})

    async def close(self, lease, completed=False, outcome='cancelled'):
        if lease.closed:
            return True
        safe = completed
        try:
            if not safe:
                try:
                    async with asyncio.timeout(12):
                        await self.transport.unload()
                        safe = True
                except (TimeoutError, OllamaUnavailable):
                    LOGGER.error('Assistant unload unconfirmed; durable memory guard retained')
            await anyio.to_thread.run_sync(lease.finish, safe, outcome)
            return safe
        except psycopg.Error:
            LOGGER.error('Assistant cleanup failed; durable memory guard retained')
            try:
                await anyio.to_thread.run_sync(self.record, lease.owner, lease.identifier, outcome)
            except psycopg.Error:
                LOGGER.error('Assistant terminal outcome audit unavailable')
            return False
        finally:
            lease.connection.close()
            lease.closed = True


class AssistantLease:
    def __init__(self, service, connection, owner, identifier, question, context):
        self.service, self.connection, self.owner = service, connection, owner
        self.identifier, self.question, self.context = identifier, question, context
        self.closed = False

    def check(self):
        self.connection.execute('SELECT 1')

    def finish(self, safe, outcome):
        # Only the original live lock session may clear its own generation barrier.
        self.check()
        with self.connection.transaction():
            self.service._audit(self.connection, self.owner, 'assistant.finished', {
                'request_id': self.identifier, 'outcome': outcome,
            })
            if safe:
                self.connection.execute('DELETE FROM llm_memory_guard WHERE id=1')
