"""Private model versions and durable administrator activation requests."""
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
import psycopg

from backend.app.api.auth import AuthService
from backend.app.api.schemas import ApiModel, ErrorResponse
from backend.app.services.training_results import TrainingResultUnavailable

if TYPE_CHECKING:
    from backend.app.services.models import ModelService


class ActivationInput(ApiModel):
    model_id: UUID


def create_models_router(auth: AuthService, service: 'ModelService') -> APIRouter:
    router = APIRouter(prefix='/api/v3', tags=['Models'], responses={
        code: {'model': ErrorResponse} for code in (401, 403, 404, 409, 422, 500, 503)
    })

    def model_data(response: Response, operation: Callable[..., dict | list[dict] | None],
                   *args: UUID) -> dict:
        response.headers['Cache-Control'] = 'no-store'
        try:
            return {'success': True, 'data': operation(*args), 'meta': {'schema_version': 3}}
        except psycopg.Error:
            raise HTTPException(503, 'DEPENDENCY_UNAVAILABLE') from None
        except TrainingResultUnavailable:
            raise HTTPException(503, 'TRAINING_RESULT_UNAVAILABLE') from None

    @router.post('/model-activations', status_code=202)
    def request_activation(body: ActivationInput, response: Response,
                           owner: UUID = Depends(auth.require_admin)) -> dict:
        return model_data(response, service.request, owner, body.model_id)

    @router.get('/model-activations/{activation_id}')
    def get_activation(activation_id: UUID, response: Response,
                       owner: UUID = Depends(auth.require_user)) -> dict:
        result = model_data(response, service.get, owner, activation_id)
        if result['data'] is None:
            raise HTTPException(404, 'MODEL_ACTIVATION_NOT_FOUND')
        return result

    @router.get('/models/active')
    def active_model(response: Response, owner: UUID = Depends(auth.require_user)) -> dict:
        return model_data(response, service.active, owner)

    @router.get('/models')
    def list_models(response: Response, owner: UUID = Depends(auth.require_user)) -> dict:
        return model_data(response, service.list_models, owner)

    return router
