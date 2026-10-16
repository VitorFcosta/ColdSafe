from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from backend.app.api.auth import AuthService
from backend.app.api.schemas import ApiModel, ErrorResponse
from backend.app.services.messaging import MessagingService, MessagingSummary, MessagingUnavailable


class MessagingResponse(ApiModel):
    success: Literal[True] = True
    data: MessagingSummary


def create_messaging_router(auth: AuthService, service: MessagingService) -> APIRouter:
    router = APIRouter(prefix='/api/v3', tags=['Messaging'])

    @router.get('/messaging', response_model=MessagingResponse, responses={
        code: {'model': ErrorResponse} for code in (401, 403, 503)
    })
    def messaging(response: Response, _actor: UUID = Depends(auth.require_admin)):
        response.headers['Cache-Control'] = 'no-store'
        try:
            return MessagingResponse(data=service.summary())
        except MessagingUnavailable:
            return JSONResponse(status_code=503, headers={'Cache-Control': 'no-store'}, content={
                'success': False,
                'error': {'code': 'DEPENDENCY_UNAVAILABLE',
                          'message': 'Não foi possível consultar a mensageria agora.'},
                'meta': {'request_id': str(uuid4())},
            })

    return router
