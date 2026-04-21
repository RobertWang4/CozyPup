"""Volcengine (Doubao) big-model streaming ASR v3 client.

Binary frame layout (4-byte header):
  byte 0: protocol version (4 bits) | header size in 4-byte units (4 bits)
  byte 1: message type (4 bits) | message-type-specific flags (4 bits)
  byte 2: serialization (4 bits) | compression (4 bits)
  byte 3: reserved (0x00)

Client → server frames:
  full client request : [header][payload_size u32 BE][gzip(JSON)]
  audio only (middle) : [header][payload_size u32 BE][gzip(PCM)]
  audio only (final)  : same, with flags=0b0010 to mark last packet

Server → client frames (server always sets the sequence flag):
  full server response: [header][sequence i32 BE][payload_size u32 BE][gzip(JSON)]
  error response      : [header][error_code u32 BE][payload_size u32 BE][JSON or UTF8]
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import struct
import uuid
from dataclasses import dataclass
from typing import AsyncIterator

import websockets
from websockets.asyncio.client import ClientConnection

from app.config import settings

logger = logging.getLogger("cozypup.trace")

# Protocol constants
PROTOCOL_VERSION = 0b0001
HEADER_SIZE = 0b0001  # 1 * 4 bytes

MSG_TYPE_FULL_CLIENT = 0b0001
MSG_TYPE_AUDIO_ONLY = 0b0010
MSG_TYPE_FULL_SERVER = 0b1001
MSG_TYPE_SERVER_ACK = 0b1011
MSG_TYPE_ERROR = 0b1111

FLAG_NONE = 0b0000
FLAG_LAST_NO_SEQ = 0b0010  # last audio packet, no sequence

SERIALIZE_RAW = 0b0000
SERIALIZE_JSON = 0b0001

COMPRESS_NONE = 0b0000
COMPRESS_GZIP = 0b0001


def _build_header(msg_type: int, flags: int, serialization: int, compression: int) -> bytes:
    return bytes([
        (PROTOCOL_VERSION << 4) | HEADER_SIZE,
        (msg_type << 4) | flags,
        (serialization << 4) | compression,
        0x00,
    ])


def _encode_full_client_request(config: dict) -> bytes:
    payload = gzip.compress(json.dumps(config, ensure_ascii=False).encode("utf-8"))
    header = _build_header(MSG_TYPE_FULL_CLIENT, FLAG_NONE, SERIALIZE_JSON, COMPRESS_GZIP)
    return header + struct.pack(">I", len(payload)) + payload


def _encode_audio_request(pcm: bytes, *, last: bool) -> bytes:
    flags = FLAG_LAST_NO_SEQ if last else FLAG_NONE
    payload = gzip.compress(pcm) if pcm else b""
    header = _build_header(MSG_TYPE_AUDIO_ONLY, flags, SERIALIZE_RAW, COMPRESS_GZIP)
    return header + struct.pack(">I", len(payload)) + payload


@dataclass
class AsrEvent:
    kind: str  # "partial" | "final" | "error" | "ack"
    text: str = ""
    code: int = 0
    raw: dict | None = None


def _parse_server_frame(frame: bytes) -> AsrEvent:
    if len(frame) < 4:
        return AsrEvent(kind="error", code=-1, text="frame too short")

    b1 = frame[1]
    msg_type = (b1 >> 4) & 0x0F
    flags = b1 & 0x0F
    b2 = frame[2]
    compression = b2 & 0x0F

    offset = 4

    if msg_type == MSG_TYPE_ERROR:
        if len(frame) < offset + 8:
            return AsrEvent(kind="error", code=-1, text="short error frame")
        error_code = struct.unpack(">I", frame[offset:offset + 4])[0]
        offset += 4
        size = struct.unpack(">I", frame[offset:offset + 4])[0]
        offset += 4
        body = frame[offset:offset + size]
        if compression == COMPRESS_GZIP and body:
            try:
                body = gzip.decompress(body)
            except Exception:
                pass
        try:
            text = body.decode("utf-8", errors="replace")
        except Exception:
            text = repr(body)
        return AsrEvent(kind="error", code=error_code, text=text)

    # Full server response / ack — server sets sequence flag, so 4 bytes sequence
    # follow the header before payload size.
    has_sequence = bool(flags & 0b0001) or bool(flags & 0b0010) or bool(flags & 0b0011)
    if has_sequence:
        if len(frame) < offset + 4:
            return AsrEvent(kind="error", code=-1, text="missing sequence")
        offset += 4  # skip sequence number

    if len(frame) < offset + 4:
        return AsrEvent(kind="error", code=-1, text="missing payload size")
    size = struct.unpack(">I", frame[offset:offset + 4])[0]
    offset += 4
    body = frame[offset:offset + size]
    if compression == COMPRESS_GZIP and body:
        try:
            body = gzip.decompress(body)
        except Exception as e:
            return AsrEvent(kind="error", code=-2, text=f"gzip decode: {e}")

    if not body:
        return AsrEvent(kind="ack", raw={})

    try:
        obj = json.loads(body.decode("utf-8"))
    except Exception as e:
        return AsrEvent(kind="error", code=-3, text=f"json decode: {e}")

    text = ((obj or {}).get("result") or {}).get("text") or ""
    # Final packet: server sets specific flags 0b0010 or 0b0011 on last response.
    is_final = bool(flags & 0b0010)
    return AsrEvent(
        kind="final" if is_final else "partial",
        text=text,
        raw=obj,
    )


class DoubaoAsrSession:
    """One active ASR WebSocket connection to Volcengine."""

    def __init__(self, *, user_id: str, correlation_id: str | None = None):
        self.user_id = user_id
        self.correlation_id = correlation_id or uuid.uuid4().hex
        self.connect_id = str(uuid.uuid4())
        self._ws: ClientConnection | None = None
        self._logid: str | None = None

    async def connect(self) -> None:
        if not settings.doubao_app_id or not settings.doubao_access_token:
            raise RuntimeError("Doubao credentials not configured")

        headers = [
            ("X-Api-App-Key", settings.doubao_app_id),
            ("X-Api-Access-Key", settings.doubao_access_token),
            ("X-Api-Resource-Id", settings.doubao_resource_id),
            ("X-Api-Connect-Id", self.connect_id),
        ]
        logger.info(
            json.dumps({
                "event": "doubao_asr_connect",
                "correlation_id": self.correlation_id,
                "user_id": self.user_id,
                "connect_id": self.connect_id,
            })
        )
        self._ws = await websockets.connect(
            settings.doubao_ws_url,
            additional_headers=headers,
            max_size=16 * 1024 * 1024,
            open_timeout=10,
        )
        try:
            self._logid = self._ws.response.headers.get("X-Tt-Logid")
        except Exception:
            self._logid = None

        config = {
            "user": {"uid": self.user_id},
            "audio": {
                "format": "pcm",
                "codec": "raw",
                "rate": 16000,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_punc": True,
                "show_utterances": False,
                "result_type": "full",
                "end_window_size": 800,
            },
        }
        await self._ws.send(_encode_full_client_request(config))

    async def send_audio(self, pcm: bytes, *, last: bool = False) -> None:
        if self._ws is None:
            raise RuntimeError("not connected")
        await self._ws.send(_encode_audio_request(pcm, last=last))

    async def events(self) -> AsyncIterator[AsrEvent]:
        if self._ws is None:
            raise RuntimeError("not connected")
        async for msg in self._ws:
            if isinstance(msg, str):
                # Unexpected text frame — log and skip.
                logger.warning(
                    json.dumps({
                        "event": "doubao_asr_unexpected_text",
                        "correlation_id": self.correlation_id,
                        "logid": self._logid,
                    })
                )
                continue
            yield _parse_server_frame(msg)

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    @property
    def logid(self) -> str | None:
        return self._logid
