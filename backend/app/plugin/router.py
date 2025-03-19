import base64
import json
import logging
import uuid

from app.audio.audio_utils import mulaw_to_pcm
from app.voice_agent.conversation.domain import (
    ConversationEvent,
    ConversationEvents,
    MarkEvent,
    MediaEvent,
)
from app.voice_agent.conversation_container import ConversationContainer
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.templating import Jinja2Templates

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/plugin", tags=["plugin"])
templates = Jinja2Templates(directory="templates")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("Connection requested")
    await websocket.accept()
    logger.info("Connection accepted")

    async def conversation_events_handler(x: ConversationEvent):
        await handle_conversation_event(x, websocket)

    conversation_container: ConversationContainer = ConversationContainer(
        conversation_id=str(uuid.uuid4()),
        callback=conversation_events_handler,
    )
    try:
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                event_type: ConversationEvents = data["type"]

                match event_type:
                    case "media":
                        media_event = MediaEvent(**data)
                        decoded_audio = base64.b64decode(media_event.audio)
                        pcm_audio = mulaw_to_pcm(decoded_audio)

                        conversation_container.audio_received(pcm_audio)
                    case "mark":
                        mark_event = MarkEvent(**data)
                        chunk_idx = mark_event.mark_id.split("_")[-1]
                        speech_idx = mark_event.mark_id.split("_")[-2]
                        logger.debug(f"Mark Message received {message}")

                        conversation_container.agent_speech_marked(
                            speech_idx=int(speech_idx), chunk_idx=int(chunk_idx)
                        )
                    case _:
                        logger.warning(f"Unknown event type: {event_type}")
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                break
    finally:
        logger.info(
            f"Cleaning up conversation {conversation_container.conversation.id}"
        )
        conversation_container.end_conversation()

    logger.info("Connection closed.")


async def handle_conversation_event(event: ConversationEvent, websocket: WebSocket):
    logger.info(f"🎭 Callback received: {event.type}")
    await websocket.send_text(event.model_dump_json())


@router.websocket("/chat/ws")
async def chat_endpoint(websocket: WebSocket):
    logger.info("Connection requested")
    await websocket.accept()
    logger.info("Connection accepted")

    try:
        while True:
            try:
                message = await websocket.receive_text()
                logger.info(f"Message received: {message}")
                await websocket.send_text(json.dumps({"content": "Hej"}))
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                break
    finally:
        logger.info("Connection closed.")
