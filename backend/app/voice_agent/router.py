import asyncio
import base64
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_openai import ChatOpenAI

from app.audio.audio_utils import mulaw_to_pcm
from app.voice_agent.conversation.conversation_manager import (
    audio_interpreter_loop,
)
from app.voice_agent.conversation.domain import ConversationEvent
from app.voice_agent.conversation.models import Conversation
from app.voice_agent.domain import RespondToHumanResult
from app.voice_agent.schemas import (
    ClearEventWS,
    CycleResult,
    MarkData,
    MarkEventWS,
    MediaData,
    MediaEventWS,
    ResultEventWS,
    StartEventWS,
)
from app.voice_agent.stt.GroqSTTProcessor import GroqSTTProcessor
from app.voice_agent.tts.ElevenTTSProcessor import ElevenTTSProcessor
from app.voice_agent.ttt.OpenAIAgent import OpenAIAgent
from app.voice_agent.voice_agent import VoiceAgent

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
conversations_cache = {}

router = APIRouter(tags=["voice_agent"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("Connection requested")
    await websocket.accept()
    logger.info("Connection accepted")

    sid = ""
    conversation: Conversation | None = None
    try:
        while True:
            try:
                message = await websocket.receive_text()

                data = json.loads(message)
                event_type = data["event"]

                if event_type == "connected":
                    logger.info(f"Connected Message received {message}")
                elif event_type == "start":
                    voice_agent = VoiceAgent(
                        tts=ElevenTTSProcessor(),
                        stt=GroqSTTProcessor(),
                        agent=OpenAIAgent(
                            llm=ChatOpenAI(model="gpt-4o"),
                            system_prompt="You are a helpful assistant that can answer questions and help with tasks.",
                        ),
                    )
                    start_event = StartEventWS(**data)

                    sid = start_event.start.streamSid
                    conversation = Conversation(sid=sid)
                    conversations_cache[sid] = conversation

                    async def conversation_events_handler(x: ConversationEvent):
                        await handle_conversation_event(x, websocket)

                    task = asyncio.create_task(
                        audio_interpreter_loop(
                            conversation=conversation,
                            voice_agent=voice_agent,
                            callback=conversation_events_handler,
                        )
                    )
                    conversation.audio_interpreter_loop = task

                elif event_type == "media":
                    if conversation is None:
                        logger.error("Conversation not found")
                        raise ValueError("Conversation not found")

                    media_event = MediaEventWS(**data)
                    decoded_audio = base64.b64decode(media_event.media.payload)
                    pcm_audio = mulaw_to_pcm(decoded_audio)
                    conversation.audio_received(pcm_audio)
                elif event_type == "closed":
                    logger.info(f"Closed Message received {message}")
                    break
                elif event_type == "mark":
                    if conversation is None:
                        logger.error("Conversation not found")
                        raise ValueError("Conversation not found")

                    mark_event = MarkEventWS(**data)
                    logger.debug(f"Mark Message received {message}")
                    chunk_idx = mark_event.mark.name.split("_")[-1]
                    speech_idx = mark_event.mark.name.split("_")[-2]
                    conversation.agent_speech_marked(
                        speech_idx=int(speech_idx), chunk_idx=int(chunk_idx)
                    )
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                break
    finally:
        logger.info(f"Cleaning up for sid: {sid}")
        if conversation is None:
            raise ValueError("Conversation not found")
        conversation.end_conversation()
        if sid in conversations_cache:
            del conversations_cache[sid]  # todo make sure this is collected by GC
        else:
            logger.error(f"Conversation not found in cache: {sid}")
    logger.info("Connection closed.")


async def handle_conversation_event(event: ConversationEvent, websocket: WebSocket):
    logger.info(f"🎭 Callback received: {event.type}")
    match event.type:
        case "stop_speaking":
            await send_stop_speaking(websocket)

        case "media":
            await send_media(event.audio, websocket, event.sid)

        case "mark":
            await send_mark(websocket, event.mark_id, event.sid)

        case "result":
            await send_result(websocket, event.result)

        case "start_restream" | "start_responding":
            # These events don't need to send anything to websocket
            pass


async def send_media(bytez: bytes, websocket: WebSocket, sid: str):
    media_base64 = base64.b64encode(bytez).decode("utf-8")
    event = MediaEventWS(
        media=MediaData(payload=media_base64),
    )
    await websocket.send_text(event.model_dump_json())


async def send_mark(websocket: WebSocket, mark_id: str, sid: str):
    event = MarkEventWS(
        mark=MarkData(name=str(mark_id)),
    )
    await websocket.send_text(event.model_dump_json())


async def send_result(
    websocket: WebSocket,
    result: RespondToHumanResult,
):
    await websocket.send_text(
        ResultEventWS(
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


async def send_stop_speaking(websocket: WebSocket):
    event = ClearEventWS()
    await websocket.send_text(event.model_dump_json())
