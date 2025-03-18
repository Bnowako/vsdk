import base64

from fastapi import WebSocket

from app.conversation.models import Conversation
from app.voice_agent.domain import RespondToHumanResult
from app.voice_agent.schemas import (
    ClearEvent,
    CycleResult,
    MarkData,
    MarkEvent,
    MediaData,
    MediaEvent,
    ResultEvent,
)


async def send_media(bytez: bytes, websocket: WebSocket, sid: str):
    media_base64 = base64.b64encode(bytez).decode("utf-8")
    event = MediaEvent(
        media=MediaData(payload=media_base64),
    )
    await websocket.send_text(event.model_dump_json())


async def send_mark(websocket: WebSocket, mark_id: str, sid: str):
    event = MarkEvent(
        mark=MarkData(name=str(mark_id)),
    )
    await websocket.send_text(event.model_dump_json())


async def send_result(
    websocket: WebSocket,
    result: RespondToHumanResult,
):
    await websocket.send_text(
        ResultEvent(
            result=CycleResult(
                stt_duration=result.stt_result.stt_end_time
                - result.stt_result.stt_start_time,
                llm_duration=result.llm_result.end_time - result.llm_result.start_time,
                tts_duration=result.tts_result.end_time - result.tts_result.start_time,
                total_duration=result.llm_result.end_time
                - result.stt_result.stt_start_time,
                first_chunk_time=result.llm_result.start_time
                - result.stt_result.stt_start_time,
                transcript=result.stt_result.transcript,
                response=result.llm_result.response,
            )
        ).model_dump_json()
    )


async def send_stop_speaking(websocket: WebSocket, client_data: Conversation):
    event = ClearEvent()
    await websocket.send_text(event.model_dump_json())
