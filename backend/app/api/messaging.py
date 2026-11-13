from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from backend.app.api.auth import AuthService
from backend.app.api.schemas import ApiModel, ErrorResponse
from backend.app.services.message_samples import MessageSamples, MessageSnapshot
from backend.app.services.messaging import MessagingService, MessagingSummary, MessagingUnavailable


class MessagingResponse(ApiModel):
    success: Literal[True] = True
    data: MessagingSummary


class MessageSamplesResponse(ApiModel):
    success: Literal[True] = True
    data: MessageSnapshot


def create_messaging_router(
    auth: AuthService, service: MessagingService | None, samples: MessageSamples | None = None,
) -> APIRouter:
    router = APIRouter(prefix='/api/v3', tags=['Messaging'])

    def unavailable():
        return JSONResponse(status_code=503, headers={'Cache-Control': 'no-store'}, content={
            'success': False,
            'error': {'code': 'DEPENDENCY_UNAVAILABLE',
                      'message': 'Não foi possível consultar a mensageria agora.'},
            'meta': {'request_id': str(uuid4())},
        })

    @router.get('/messaging/messages', response_model=MessageSamplesResponse, responses={
        code: {'model': ErrorResponse} for code in (401, 403, 503)
    })
    def messages(response: Response, actor: UUID = Depends(auth.require_admin)):
        response.headers['Cache-Control'] = 'no-store'
        try:
            snapshot = samples.snapshot(actor) if samples is not None else MessageSnapshot(
                sampled_at=datetime.now(UTC), connected=False, last_observed_at=None,
                stale=True, messages=(), dead_letters=(),
            )
            return MessageSamplesResponse(data=snapshot)
        except MessagingUnavailable:
            return unavailable()

    @router.get('/messaging', response_model=MessagingResponse, responses={
        code: {'model': ErrorResponse} for code in (401, 403, 503)
    })
    def messaging(response: Response, _actor: UUID = Depends(auth.require_admin)):
        response.headers['Cache-Control'] = 'no-store'
        try:
            if service is None:
                return unavailable()
            return MessagingResponse(data=service.summary())
        except MessagingUnavailable:
            return unavailable()

    return router
