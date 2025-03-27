import base64
import json
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from starlette.templating import Jinja2Templates

from app.audio.audio_utils import mulaw_to_pcm
from app.twilio.schemas import (
    ClearEventWS,
    CustomResultEvent,
    MarkData,
    MediaData,
    TwilioMarkEvent,
    TwilioMediaEvent,
    TwilioStartEvent,
)
from app.voice_agent.conversation.domain import ConversationEvent
from app.voice_agent.conversation_orchestrator import ConversationOrchestrator
from app.voice_agent.domain import RespondToHumanResult

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/twilio", tags=["twilio"])
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse("twilio.html", {"request": request})


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("Connection requested")
    await websocket.accept()
    logger.info("Connection accepted")

    sid = ""
    conversation_container: ConversationOrchestrator | None = None
    try:
        while True:
            try:
                message = await websocket.receive_text()

                data = json.loads(message)
                event_type = data["event"]

                if (
                    event_type != "connected" and event_type != "start"
                ) and conversation_container is None:
                    logger.error("Conversation not found")
                    raise ValueError("Conversation not found")

                if event_type == "connected":
                    logger.info(f"Connected Message received {message}")
                elif event_type == "start":
                    start_event = TwilioStartEvent(**data)
                    sid = start_event.start.streamSid

                    # initialize conversation container
                    async def conversation_events_handler(x: ConversationEvent):
                        await handle_conversation_event(x, websocket)

                    conversation_container = ConversationOrchestrator(
                        conversation_id=sid,
                        callback=conversation_events_handler,
                    )
                elif event_type == "media" and conversation_container:
                    media_event = TwilioMediaEvent(**data)
                    decoded_audio = base64.b64decode(media_event.media.payload)
                    pcm_audio = mulaw_to_pcm(decoded_audio)

                    conversation_container.audio_received(pcm_audio)
                elif event_type == "closed":
                    logger.info(f"Closed Message received {message}")
                    break
                elif event_type == "mark" and conversation_container:
                    mark_event = TwilioMarkEvent(**data)
                    chunk_idx = mark_event.mark.name.split("_")[-1]
                    speech_idx = mark_event.mark.name.split("_")[-2]
                    logger.debug(f"Mark Message received {message}")

                    conversation_container.agent_speech_marked(
                        speech_idx=int(speech_idx), chunk_idx=int(chunk_idx)
                    )
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                break
    finally:
        logger.info(f"Cleaning up for sid: {sid}")
        if conversation_container is None:
            raise ValueError("Conversation not found")
        conversation_container.end_conversation()

    logger.info("Connection closed.")


async def handle_conversation_event(event: ConversationEvent, websocket: WebSocket):
    logger.info(f"🎭 Callback received: {event.type}")
    match event.type:
        case "stop_speaking":
            await send_stop_speaking(websocket)

        case "media":
            await send_media(event.audio, websocket)

        case "mark":
            await send_mark(websocket, event.mark_id)

        case "result":
            await send_result(websocket, event.result)

        case _:
            # These events don't need to send anything to websocket
            logger.warning(f"Unknown event type: {event.type}")
            pass


async def send_media(bytez: bytes, websocket: WebSocket):
    media_base64 = base64.b64encode(bytez).decode("utf-8")
    event = TwilioMediaEvent(
        media=MediaData(payload=media_base64),
    )
    await websocket.send_text(event.model_dump_json())


async def send_mark(websocket: WebSocket, mark_id: str):
    event = TwilioMarkEvent(
        mark=MarkData(name=str(mark_id)),
    )
    await websocket.send_text(event.model_dump_json())


async def send_result(
    websocket: WebSocket,
    result: RespondToHumanResult,
):
    await websocket.send_text(CustomResultEvent(result=result).model_dump_json())


async def send_stop_speaking(websocket: WebSocket):
    event = ClearEventWS()
    await websocket.send_text(event.model_dump_json())
