"""WebSocket endpoint that proxies iOS audio to Volcengine streaming ASR.

Protocol with iOS client:
  - iOS connects to /api/v1/speech/stream?token=<jwt>
  - Server verifies JWT, opens Volcengine session, relays in both directions.
  - iOS sends binary frames = raw PCM16 16kHz mono chunks (100-200ms each).
  - iOS sends text frame `{"type":"end"}` to mark end-of-speech.
  - Server sends text frames:
      {"type":"partial","text":"..."}      — interim result
      {"type":"final","text":"..."}        — last utterance
      {"type":"error","code":N,"message":""}
      {"type":"ready"}                     — upstream connected, safe to stream audio
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Optional

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from websockets.exceptions import ConnectionClosed

from app.config import settings
from app.debug.correlation import generate_correlation_id, set_correlation_id, set_user_id
from app.services.doubao_asr import DoubaoAsrSession

logger = logging.getLogger("cozypup.trace")

router = APIRouter()


def _authenticate(token: str) -> Optional[str]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None


@router.websocket("/api/v1/speech/stream")
async def speech_stream(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token") or ""
    user_id = _authenticate(token)
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    correlation_id = websocket.headers.get("X-Correlation-ID") or generate_correlation_id()
    set_correlation_id(correlation_id)
    set_user_id(user_id)

    await websocket.accept()
    logger.info(json.dumps({
        "event": "speech_stream_start",
        "correlation_id": correlation_id,
        "user_id": user_id,
    }))

    session = DoubaoAsrSession(user_id=user_id, correlation_id=correlation_id)

    try:
        await session.connect()
    except Exception as e:
        logger.exception("doubao_asr_connect_failed")
        await websocket.send_text(json.dumps({
            "type": "error",
            "code": -1,
            "message": f"upstream connect failed: {e}",
        }))
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    await websocket.send_text(json.dumps({"type": "ready", "logid": session.logid}))

    stop_event = asyncio.Event()

    async def pump_upstream() -> None:
        """Read ASR results from Volcengine and forward to iOS."""
        try:
            async for ev in session.events():
                if ev.kind == "error":
                    await websocket.send_text(json.dumps({
                        "type": "error", "code": ev.code, "message": ev.text,
                    }))
                    stop_event.set()
                    return
                if ev.kind in ("partial", "final"):
                    await websocket.send_text(json.dumps({
                        "type": ev.kind, "text": ev.text,
                    }))
                    if ev.kind == "final":
                        stop_event.set()
                        return
        except ConnectionClosed:
            stop_event.set()
        except Exception:
            logger.exception("pump_upstream_failed")
            stop_event.set()

    async def pump_downstream() -> None:
        """Read audio frames from iOS and forward to Volcengine."""
        try:
            while not stop_event.is_set():
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    await session.send_audio(b"", last=True)
                    return
                if "bytes" in msg and msg["bytes"] is not None:
                    await session.send_audio(msg["bytes"], last=False)
                elif "text" in msg and msg["text"]:
                    try:
                        obj = json.loads(msg["text"])
                    except Exception:
                        continue
                    if obj.get("type") == "end":
                        await session.send_audio(b"", last=True)
        except WebSocketDisconnect:
            try:
                await session.send_audio(b"", last=True)
            except Exception:
                pass
        except Exception:
            logger.exception("pump_downstream_failed")

    up_task = asyncio.create_task(pump_upstream())
    down_task = asyncio.create_task(pump_downstream())

    # Safety timeout — cap sessions at 60s to match iOS behavior.
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=60.0)
    except asyncio.TimeoutError:
        pass

    for t in (up_task, down_task):
        if not t.done():
            t.cancel()
    await asyncio.gather(up_task, down_task, return_exceptions=True)

    await session.close()
    try:
        await websocket.close()
    except Exception:
        pass

    logger.info(json.dumps({
        "event": "speech_stream_end",
        "correlation_id": correlation_id,
        "user_id": user_id,
        "logid": session.logid,
    }))
