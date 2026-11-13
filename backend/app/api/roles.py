from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends

from backend.app.api.auth import AuthService
from backend.app.api.schemas import ApiModel, ErrorResponse, SuccessMeta


class RoleInput(ApiModel):
    role: Literal["viewer", "operator", "admin"]


class RoleData(RoleInput):
    user_id: UUID


class RoleResponse(ApiModel):
    success: Literal[True] = True
    data: RoleData
    meta: SuccessMeta = SuccessMeta()


def create_roles_router(auth: AuthService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["Auth"], responses={
        code: {"model": ErrorResponse} for code in (401, 403, 404, 422)
    })

    @router.patch("/users/{user_id}/role", response_model=RoleResponse)
    def change_role(user_id: UUID, body: RoleInput, actor: UUID = Depends(auth.require_admin)) -> RoleResponse:
        auth.change_role(actor, user_id, body.role)
        return RoleResponse(data=RoleData(user_id=user_id, role=body.role))

    return router
