"""Owner-scoped WebSocket events bridged from MQTT's worker thread."""

import asyncio
import json
import re
from collections import defaultdict
from contextlib import suppress
from threading import Lock
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService


DEVICE_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")


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


def install_events(app: FastAPI, hub: EventHub, auth: AuthService, catalog: CatalogService) -> None:
    @app.websocket("/api/v1/events")
    async def events(websocket: WebSocket) -> None:
        await websocket.accept()
        device_id = websocket.query_params.get("device_id", "")
        if DEVICE_ID_PATTERN.fullmatch(device_id) is None:
            await websocket.close(code=1008)
            return
        try:
            first = await asyncio.wait_for(websocket.receive_text(), timeout=5)
            credentials = json.loads(first)
            token = credentials.get("token") if isinstance(credentials, dict) else None
            if not isinstance(token, str) or not token:
                await websocket.close(code=4401)
                return
            user_id = await asyncio.to_thread(auth.current_user, token)
            if user_id is None:
                await websocket.close(code=4401)
                return
            device = await asyncio.to_thread(catalog.device_for_user, user_id, device_id)
            if device is None or not device["is_active"]:
                await websocket.close(code=4403)
                return

            queue = hub.subscribe(device_id)
            receive_task = asyncio.create_task(websocket.receive_text())
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
                        await receive_task
                        await websocket.close(code=1008)
                        return
                    if await asyncio.to_thread(auth.current_user, token) != user_id:
                        await websocket.close(code=4401)
                        return
                    current = await asyncio.to_thread(catalog.device_for_user, user_id, device_id)
                    if current is None or not current["is_active"]:
                        await websocket.close(code=4403)
                        return
                    if queued in done:
                        await websocket.send_json(queued.result())
            finally:
                receive_task.cancel()
                with suppress(asyncio.CancelledError, WebSocketDisconnect):
                    await receive_task
                hub.unsubscribe(device_id, queue)
        except (asyncio.TimeoutError, json.JSONDecodeError):
            await websocket.close(code=4401)
        except WebSocketDisconnect:
            pass
