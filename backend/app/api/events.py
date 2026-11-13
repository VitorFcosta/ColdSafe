"""Owner-scoped WebSocket events bridged from MQTT's worker thread."""

import asyncio
import json
import re
from collections import defaultdict
from contextlib import suppress
from datetime import datetime
from threading import Lock
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import Field

from backend.app.api.auth import AuthService, _bearer
from backend.app.api.catalog import CatalogService
from backend.app.api.schemas import ApiModel, ErrorResponse, SuccessMeta


DEVICE_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")


class WsTicketPayload(ApiModel):
    device_id: str = Field(strict=True, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")


class WsTicketData(ApiModel):
    ticket: str
    expires_at: datetime


class WsTicketResponse(ApiModel):
    success: Literal[True] = True
    data: WsTicketData
    meta: SuccessMeta = SuccessMeta()


class EventHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = defaultdict(set)
        self._lock = Lock()

    def subscribe(self, device_id: str) -> asyncio.Queue:
        # ponytail: bounded live queue; add a replay log only if durable delivery is required.
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        with self._lock:
            self._subscribers[device_id].add((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, device_id: str, queue: asyncio.Queue) -> None:
        with self._lock:
            subscribers = self._subscribers.get(device_id)
            if subscribers is not None:
                subscribers.difference_update({entry for entry in subscribers if entry[1] is queue})
                if not subscribers:
                    self._subscribers.pop(device_id, None)

    def publish(self, device_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers.get(device_id, ()))
        for loop, queue in subscribers:
            def deliver(target: asyncio.Queue = queue) -> None:
                if target.full():
                    target.get_nowait()
                target.put_nowait(event)

            try:
                loop.call_soon_threadsafe(deliver)
            except RuntimeError:
                # An event may race with application shutdown.
                pass


def install_events(
    app: FastAPI, hub: EventHub, auth: AuthService, catalog: CatalogService,
    *, stream_path: str = "/api/v1/events", include_ticket: bool = True,
) -> None:
    def ws_ticket(
        payload: WsTicketPayload,
        user_id: Annotated[UUID, Depends(auth.require_user)],
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> WsTicketResponse:
        device = catalog.device_for_user(user_id, payload.device_id)
        if device is None:
            raise HTTPException(status_code=404, detail="DEVICE_NOT_FOUND")
        if not device["is_active"]:
            raise HTTPException(status_code=403, detail="FORBIDDEN")
        ticket, expires_at = auth.create_ws_ticket(credentials.credentials, UUID(str(device["id"])))
        return WsTicketResponse(data=WsTicketData(ticket=ticket, expires_at=expires_at))

    if include_ticket:
        app.add_api_route(
            "/api/v1/auth/ws-ticket", ws_ticket, methods=["POST"],
            response_model=WsTicketResponse, tags=["Auth"],
            responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 422)},
        )

    @app.websocket(stream_path)
    async def events(websocket: WebSocket) -> None:
        await websocket.accept()
        device_id = websocket.query_params.get("device_id", "")
        if (list(websocket.query_params.multi_items()) != [("device_id", device_id)]
                or DEVICE_ID_PATTERN.fullmatch(device_id) is None):
            await websocket.close(code=1008)
            return
        try:
            first_message = await asyncio.wait_for(websocket.receive(), timeout=5)
            if first_message["type"] == "websocket.disconnect":
                return
            first = first_message.get("text")
            if not isinstance(first, str) or len(first.encode("utf-8")) > 2048:
                await websocket.close(code=4401)
                return
            credentials = json.loads(first)
            ticket = credentials.get("ticket") if isinstance(credentials, dict) else None
            if (not isinstance(credentials, dict) or set(credentials) != {"ticket"}
                    or not isinstance(ticket, str) or not ticket):
                await websocket.close(code=4401)
                return
            principal = await asyncio.to_thread(auth.consume_ws_ticket, ticket, device_id)
            if principal is None:
                await websocket.close(code=4401)
                return
            user_id = principal.user_id
            device = await asyncio.to_thread(catalog.device_for_user, user_id, device_id)
            if (device is None or not device["is_active"]
                    or principal.role not in {"viewer", "operator", "admin"}):
                await websocket.close(code=4403)
                return

            queue = hub.subscribe(device_id)
            receive_task = asyncio.create_task(websocket.receive())
            queued = None
            try:
                while True:
                    queued = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait(
                        {queued, receive_task}, timeout=1, return_when=asyncio.FIRST_COMPLETED
                    )
                    if queued not in done:
                        queued.cancel()
                        with suppress(asyncio.CancelledError):
                            await queued
                    if receive_task in done:
                        message = receive_task.result()
                        if message["type"] != "websocket.disconnect":
                            await websocket.close(code=1008)
                        return
                    current_session = await asyncio.to_thread(auth.session_for_id, principal.session_id)
                    if current_session is None or current_session.user_id != user_id:
                        await websocket.close(code=4401)
                        return
                    current = await asyncio.to_thread(catalog.device_for_user, user_id, device_id)
                    if (current is None or not current["is_active"]
                            or current_session.role not in {"viewer", "operator", "admin"}):
                        await websocket.close(code=4403)
                        return
                    if queued in done:
                        await websocket.send_json(queued.result())
            finally:
                for task in (queued, receive_task):
                    if task is not None:
                        task.cancel()
                        with suppress(asyncio.CancelledError, WebSocketDisconnect):
                            await task
                hub.unsubscribe(device_id, queue)
        except (asyncio.TimeoutError, json.JSONDecodeError, RecursionError):
            await websocket.close(code=4401)
        except WebSocketDisconnect:
            pass
