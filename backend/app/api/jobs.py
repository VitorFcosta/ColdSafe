"""Private durable job submission, recovery and authenticated progress streams."""
import asyncio
from datetime import datetime
import json
from typing import Annotated, Literal, TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import psycopg
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from backend.app.api.auth import AuthService
from backend.app.api.schemas import ApiModel, ErrorResponse
from backend.app.domain.jobs import GenerationInput, TrainingInput
from backend.app.services.datasets import DatasetUnavailable, read_dataset
from backend.app.services.training_results import TrainingResultUnavailable, read_training_result

if TYPE_CHECKING:
    from backend.app.services.jobs import JobService


class JobData(ApiModel):
    id: UUID
    owner_user_id: UUID
    config: dict
    job_type: Literal['generation', 'training']
    status: Literal['queued', 'running', 'completed', 'failed', 'cancelled']
    completed_units: int = Field(ge=0)
    total_units: int = Field(gt=0)
    result_id: UUID | None
    error_code: str | None
    environment_id: UUID | None
    dataset_id: UUID | None
    created_at: datetime
    updated_at: datetime


class JobMeta(ApiModel):
    schema_version: Literal[3] = 3


class JobResponse(ApiModel):
    success: Literal[True] = True
    data: JobData
    meta: JobMeta = JobMeta()


_bearer = HTTPBearer(auto_error=False)


def create_jobs_router(auth: AuthService, service: 'JobService') -> APIRouter:
    router = APIRouter(prefix='/api/v3', tags=['Jobs'], responses={
        code: {'model': ErrorResponse} for code in (401, 403, 404, 422, 500, 503)
    })

    def owned_job(owner: UUID, job_id: UUID) -> dict:
        try:
            job = service.get(owner, job_id)
        except psycopg.Error:
            raise HTTPException(503, 'DEPENDENCY_UNAVAILABLE') from None
        if job is None:
            raise HTTPException(404, 'JOB_NOT_FOUND')
        return job

    def dataset_data(owner: UUID, dataset_id: UUID, *, sample: bool) -> dict:
        try:
            dataset = service.repository.get_dataset(owner, dataset_id)
            if dataset is None or dataset['owner_user_id'] != owner or not dataset['generation_job_id']:
                raise HTTPException(404, 'DATASET_NOT_FOUND')
            job = service.get(owner, dataset['generation_job_id'])
            if (job is None or job['owner_user_id'] != owner or job['job_type'] != 'generation' or
                    job['status'] != 'completed' or job['result_id'] != dataset_id):
                raise HTTPException(404, 'DATASET_NOT_FOUND')
            summary, rows = read_dataset(service.artifact_root, dataset, job)
            return {'success': True, 'data': rows if sample else summary, 'meta': {'schema_version': 3}}
        except psycopg.Error:
            raise HTTPException(503, 'DEPENDENCY_UNAVAILABLE') from None
        except DatasetUnavailable:
            raise HTTPException(503, 'DATASET_UNAVAILABLE') from None

    @router.get('/datasets')
    def list_datasets(response: Response, owner: UUID = Depends(auth.require_user)) -> dict:
        response.headers['Cache-Control'] = 'no-store'
        try:
            rows = service.repository.list_datasets(owner)
            return {'success': True, 'data': rows, 'meta': {'schema_version': 3}}
        except psycopg.Error:
            raise HTTPException(503, 'DEPENDENCY_UNAVAILABLE') from None

    @router.get('/datasets/{dataset_id}')
    def get_dataset(dataset_id: UUID, response: Response,
                    owner: UUID = Depends(auth.require_user)) -> dict:
        response.headers['Cache-Control'] = 'no-store'
        return dataset_data(owner, dataset_id, sample=False)

    @router.get('/datasets/{dataset_id}/sample')
    def get_dataset_sample(dataset_id: UUID, response: Response,
                           owner: UUID = Depends(auth.require_user)) -> dict:
        response.headers['Cache-Control'] = 'no-store'
        return dataset_data(owner, dataset_id, sample=True)

    @router.post('/jobs', status_code=202, response_model=JobResponse)
    def create_job(
        body: Annotated[GenerationInput | TrainingInput, Body(discriminator='job_type')],
        response: Response, owner: UUID = Depends(auth.require_admin),
    ) -> JobResponse:
        response.headers['Cache-Control'] = 'no-store'
        try:
            return JobResponse(data=service.create(owner, body.model_dump()))
        except psycopg.Error:
            raise HTTPException(503, 'DEPENDENCY_UNAVAILABLE') from None

    @router.get('/jobs/{job_id}', response_model=JobResponse)
    def get_job(job_id: UUID, response: Response,
                owner: UUID = Depends(auth.require_user)) -> JobResponse:
        response.headers['Cache-Control'] = 'no-store'
        return JobResponse(data=owned_job(owner, job_id))

    @router.get('/jobs/{job_id}/result')
    def get_training_result(job_id: UUID, response: Response,
                            owner: UUID = Depends(auth.require_user)) -> dict:
        response.headers['Cache-Control'] = 'no-store'
        job = owned_job(owner, job_id)
        if job['job_type'] != 'training':
            raise HTTPException(404, 'JOB_NOT_FOUND')
        if job['status'] != 'completed':
            raise HTTPException(409, 'TRAINING_NOT_READY')
        try:
            model = service.repository.get_model(owner, job['result_id'])
            dataset = service.repository.get_dataset(owner, job['dataset_id'])
            if (model is None or dataset is None or model['owner_user_id'] != owner or
                    dataset['owner_user_id'] != owner or model['training_job_id'] != job_id or
                    model['dataset_id'] != dataset['id'] or dataset['id'] != job['dataset_id']):
                raise HTTPException(404, 'JOB_NOT_FOUND')
            data = read_training_result(service.training_artifact_root, model, job, dataset)
            return {'success': True, 'data': data, 'meta': {'schema_version': 3}}
        except psycopg.Error:
            raise HTTPException(503, 'DEPENDENCY_UNAVAILABLE') from None
        except TrainingResultUnavailable:
            raise HTTPException(503, 'TRAINING_RESULT_UNAVAILABLE') from None

    @router.get('/jobs/{job_id}/events', response_class=StreamingResponse)
    def job_events(
        job_id: UUID, request: Request, owner: UUID = Depends(auth.require_user),
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> StreamingResponse:
        if credentials is None:
            raise HTTPException(401, 'UNAUTHORIZED')
        owned_job(owner, job_id)

        async def events():
            previous_update = None
            idle_ticks = 0
            while not await request.is_disconnected():
                try:
                    principal = await run_in_threadpool(auth.session_for_token, credentials.credentials)
                    if principal is None or principal.user_id != owner:
                        return
                    job = await run_in_threadpool(service.get, owner, job_id)
                    if job is None:
                        return
                    data = JobData.model_validate(job)
                    if data.updated_at != previous_update:
                        yield 'event: job_progress\ndata: ' + json.dumps(jsonable_encoder(
                            JobResponse(data=data),
                        ), separators=(',', ':')) + '\n\n'
                        previous_update = data.updated_at
                    if data.status in ('completed', 'failed', 'cancelled'):
                        return
                    idle_ticks += 1
                    if idle_ticks == 15:
                        yield ': keep-alive\n\n'
                        idle_ticks = 0
                except psycopg.Error:
                    yield ('event: error\ndata: {"code":"DEPENDENCY_UNAVAILABLE",'
                           '"message":"Não foi possível consultar o progresso agora."}\n\n')
                    return
                await asyncio.sleep(1)

        return StreamingResponse(events(), media_type='text/event-stream', headers={
            'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no',
        })

    return router
