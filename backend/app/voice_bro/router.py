import base64
import json
import logging
import uuid

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from starlette.templating import Jinja2Templates

from app.chat.CustomBroAgent import CustomBroAgent
from app.chat.playwright_tools import (
    browser_snapshot,
    click_element,
    navigate,
    type_text,
)
from vsdk.conversation.domain import (
    ConversationEvent,
    ConversationEvents,
    MarkEvent,
    MediaEvent,
)
from vsdk.conversation_orchestrator import ConversationOrchestrator
from vsdk.stt.GroqSTTProcessor import GroqSTTProcessor
from vsdk.tts.ElevenTTSProcessor import ElevenTTSProcessor
from vsdk.voice_agent import VoiceAgent

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/voicebro", tags=["voicebro"])
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse("voice_bro.html", {"request": request})


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("Connection requested")
    await websocket.accept()
    logger.info("Connection accepted")

    async def conversation_events_handler(x: ConversationEvent):
        await handle_conversation_event(x, websocket)

    agent = CustomBroAgent(tools=[browser_snapshot, click_element, type_text, navigate])
    conversation_orchestrator: ConversationOrchestrator = ConversationOrchestrator(
        conversation_id=str(uuid.uuid4()),
        callback=conversation_events_handler,
        voice_agent=VoiceAgent(
            tts=ElevenTTSProcessor(),
            stt=GroqSTTProcessor(),
            agent=agent,
        ),
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
                        conversation_orchestrator.audio_received(decoded_audio)
                    case "mark":
                        mark_event = MarkEvent(**data)
                        chunk_idx = mark_event.mark_id.split("_")[-1]
                        speech_idx = mark_event.mark_id.split("_")[-2]
                        logger.debug(f"Mark Message received {message}")

                        conversation_orchestrator.agent_speech_marked(
                            speech_idx=int(speech_idx), chunk_idx=int(chunk_idx)
                        )
                    case _:
                        logger.warning(f"Unknown event type: {event_type}")
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                break
    finally:
        logger.info(
            f"Cleaning up conversation {conversation_orchestrator.conversation.id}"
        )
        conversation_orchestrator.end_conversation()

    logger.info("Connection closed.")


async def handle_conversation_event(event: ConversationEvent, websocket: WebSocket):
    logger.info(f"🎭 Callback received: {event.type}")
    await websocket.send_text(event.model_dump_json())
