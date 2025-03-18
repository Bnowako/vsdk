import base64
import json

from fastapi import WebSocket

from app.conversation.models import Conversation


async def send_media(bytez: bytes, websocket: WebSocket, sid: str):
    media_base64 = base64.b64encode(bytez).decode("utf-8")
    msg = {"event": "media", "streamSid": sid, "media": {"payload": media_base64}}
    await websocket.send_text(json.dumps(msg))


async def send_mark(websocket: WebSocket, mark_id: str, sid: str):
    msg = {"event": "mark", "streamSid": sid, "mark": {"name": str(mark_id)}}
    await websocket.send_text(json.dumps(msg))


async def send_to_front(
    websocket: WebSocket,
    transcript: str,
    stt_time: float,
    bytes_data: bytes,
    llm_stats: str,
    tts_stats: str,
):
    await websocket.send_text(
        json.dumps(
            {
                "event": "transcript",
                "data": transcript,
                "elapsed_time": stt_time,
                "file": base64.b64encode(bytes_data).decode("utf-8"),
            }
        )
    )
    await websocket.send_text(json.dumps({"event": "chat-response", "data": llm_stats}))
    await websocket.send_text(json.dumps({"event": "tts-time", "data": tts_stats}))


async def send_stop_speaking(websocket: WebSocket, client_data: Conversation):
    msg = {"event": "clear", "streamSid": client_data.sid}
    await websocket.send_text(json.dumps(msg))
