"""Private lifecycle state only; prompting belongs to the later assistant task."""
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from backend.app.api.auth import AuthService
from backend.app.services.llm import LlmService


def create_llm_router(auth: AuthService, service: LlmService) -> APIRouter:
    router = APIRouter(prefix='/api/v3/llm', tags=['Local model'])

    @router.get('/status')
    def status(response: Response, _owner: UUID = Depends(auth.require_user)) -> dict:
        response.headers['Cache-Control'] = 'no-store'
        return {'success': True, 'data': service.status(), 'meta': {'schema_version': 3}}

    return router
