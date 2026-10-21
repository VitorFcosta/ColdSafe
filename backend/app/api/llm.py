"""Private local-model status and authenticated read-only assistant streaming."""
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Response, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import Field, field_validator

from backend.app.api.auth import AuthService
from backend.app.services.llm import LlmService
from backend.app.api.schemas import ApiModel, ErrorResponse
from backend.app.services.assistant import AssistantError


class AssistantInput(ApiModel):
    question: str = Field(strict=True, min_length=1, max_length=256)

    @field_validator('question')
    @classmethod
    def nonempty(cls, value):
        if not value.strip() or len(value.encode('utf-8')) > 256:
            raise ValueError('Question must contain 1 to 256 UTF-8 bytes')
        return value.strip()


class AssistantStream(StreamingResponse):
    def __init__(self, content, *, cleanup, **kwargs):
        super().__init__(content, **kwargs)
        self.cleanup = cleanup

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # ASGI send failures can bypass Starlette background tasks.
            with anyio.CancelScope(shield=True):
                try:
                    await self.body_iterator.aclose()
                finally:
                    await self.cleanup()


def create_llm_router(auth: AuthService, service: LlmService, assistant=None) -> APIRouter:
    router = APIRouter(prefix='/api/v3/llm', tags=['Local model'])

    @router.get('/status')
    def status(response: Response, _owner: UUID = Depends(auth.require_user)) -> dict:
        response.headers['Cache-Control'] = 'no-store'
        return {'success': True, 'data': service.status(), 'meta': {'schema_version': 3}}

    @router.post('/ask', response_class=StreamingResponse, responses={
        200: {'content': {'text/event-stream': {'schema': {'type': 'string'}}}},
        **{code: {'model': ErrorResponse} for code in (401, 422, 429, 503)},
    })
    async def ask(body: AssistantInput, request: Request, owner: UUID = Depends(auth.require_user)):
        if assistant is None:
            raise HTTPException(503, 'LLM_DISABLED')
        try:
            lease = await anyio.to_thread.run_sync(assistant.open, owner, body.question)
        except AssistantError as error:
            raise HTTPException(error.status, error.code,
                                headers={'Retry-After': '60'} if error.status == 429 else None) from None
        token = request.headers['authorization'].split(' ', 1)[1]
        return AssistantStream(
            assistant.events(lease, lambda: auth.current_user(token, statement_timeout_ms=3000) == owner),
            cleanup=lambda: assistant.close(lease),
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'},
        )

    return router
