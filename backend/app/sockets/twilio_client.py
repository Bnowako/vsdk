import base64
import json

from fastapi import WebSocket

from app.conversation.models import Conversation
from app.voice_agent.domain import RespondToHumanResult


async def send_media(bytez: bytes, websocket: WebSocket, sid: str):
    media_base64 = base64.b64encode(bytez).decode("utf-8")
    msg = {"event": "media", "streamSid": sid, "media": {"payload": media_base64}}
    await websocket.send_text(json.dumps(msg))


async def send_mark(websocket: WebSocket, mark_id: str, sid: str):
    msg = {"event": "mark", "streamSid": sid, "mark": {"name": str(mark_id)}}
    await websocket.send_text(json.dumps(msg))


async def send_to_front(
    websocket: WebSocket,
    result: RespondToHumanResult,
):
    await websocket.send_text(
        json.dumps(
            {
                "event": "transcript",
                "data": result.stt_result.transcript,
                "elapsed_time": result.stt_result.stt_end_time
                - result.stt_result.stt_start_time,
                "file": base64.b64encode(result.stt_result.speech_file).decode("utf-8"),
            }
        )
    )
    await websocket.send_text(
        json.dumps({"event": "chat-response", "data": result.llm_result.response})
    )
    await websocket.send_text(
        json.dumps({"event": "tts-time", "data": result.tts_result.response})
    )


async def send_stop_speaking(websocket: WebSocket, client_data: Conversation):
    msg = {"event": "clear", "streamSid": client_data.sid}
    await websocket.send_text(json.dumps(msg))
