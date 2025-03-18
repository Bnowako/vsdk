from app.config import create_app
from fastapi.templating import Jinja2Templates
from fastapi import Request
import asyncio
import base64
import json
from fastapi import WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from starlette.responses import StreamingResponse
from pydantic import BaseModel
from app.agents.agent_coordinator import agent
from app.agents.agent_coordinator import respond_to_human
from app.audio.audio_utils import mulaw_to_pcm
from app.conversation.conversation_processor import process, ConversationState
from app.conversation.models import Conversation
from app.sockets.twilio_client import (
    send_media,
    send_mark,
    send_stop_speaking,
    send_to_front,
)
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = create_app()

templates = Jinja2Templates(directory="templates")
conversations_cache = {}

@app.get("/status")
async def main():
    return {"status": "OK"}

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("main.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("Connection requested")
    await websocket.accept()
    logger.info("Connection accepted")

    sid = ""
    conversation = None
    try:
        while True:
            try:
                message = await websocket.receive_text()

                if message is None:
                    logger.info("No message received...")
                    continue
                data = json.loads(message)
                if data["event"] == "connected":
                    logger.info(f"Connected Message received {message}")
                elif data["event"] == "start":
                    sid = data["start"]["streamSid"]
                    conversation = Conversation(sid=sid)
                    conversations_cache[sid] = conversation

                    task = asyncio.create_task(
                        audio_interpreter_loop(conversation, websocket)
                    )
                    conversation.audio_interpreter_loop = task

                elif data["event"] == "media":
                    base64_payload = data["media"]["payload"]
                    decoded_audio = base64.b64decode(base64_payload)
                    pcm_audio = mulaw_to_pcm(decoded_audio)
                    conversation.audio_received(pcm_audio)
                elif data["event"] == "closed":
                    logger.info(f"Closed Message received {message}")
                    break
                elif data["event"] == "mark":
                    logger.debug(f"Mark Message received {message}")
                    chunk_idx = data["mark"]["name"].split("_")[-1]
                    speech_idx = data["mark"]["name"].split("_")[-2]
                    conversation.agent_speech_marked(
                        speech_idx=int(speech_idx), chunk_idx=int(chunk_idx)
                    )
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                break
    finally:
        logger.info(f"Cleaning up for sid: {sid}")
        conversation.end_conversation()
        if sid in conversations_cache:
            del conversations_cache[sid]  # todo make sure this is collected by GC
        else:
            logger.error(f"Conversation not found in cache: {sid}")
    logger.info("Connection closed.")


async def audio_interpreter_loop(conversation: Conversation, websocket: WebSocket):
    try:
        while True:
            if conversation.is_new_audio_ready_to_process():
                conversation_state = process(conversation)
                logger.debug(f"🖥️ Conversation state: {conversation_state}")

                match conversation_state:
                    case (
                        ConversationState.HUMAN_SILENT
                        | ConversationState.HUMAN_STARTED_SPEAKING
                    ):
                        pass

                    case ConversationState.BOTH_SPEAKING:
                        conversation.stop_speaking_agent()
                        await send_stop_speaking(websocket, conversation)

                    case ConversationState.SHORT_INTERRUPTION_DURING_AGENT_SPEAKING:
                        await restream_audio(
                            websocket, conversation
                        )  # todo should be done on another task?
                        conversation.clear_human_speech()  # todo this forgets what was the short interruption "tak" / "nie". For now it is ok

                    case (
                        ConversationState.LONG_INTERRUPTION_DURING_AGENT_SPEAKING
                        | ConversationState.SHORT_SPEECH
                        | ConversationState.LONG_SPEECH
                    ):
                        conversation.prepare_human_speech_for_interpretation()
                        conversation.add_agent_response_task(
                            task=asyncio.create_task(
                                handle_respond_to_human(conversation, websocket)
                            )
                        )

                    case _:
                        raise ValueError(f"Unknown state: {conversation_state}")

            await asyncio.sleep(0.01)
    except Exception as e:
        logger.error(f"Exception in audio_interpreter_loop: {e}")


async def handle_respond_to_human(conversation: Conversation, websocket: WebSocket):
    try:
        result = {}
        conversation.new_agent_speech_start()
        async for chunk in respond_to_human(
            conversation.human_speech_without_response,
            conversation.sid,
            lambda x: result.update(x),
        ):
            await send_media(chunk, websocket, conversation.sid)
            mark_id = conversation.agent_speech_sent(chunk)
            await send_mark(websocket, mark_id, conversation.sid)

        if LOCAL:
            await send_to_front(
                websocket=websocket,
                transcript=result["transcript"],
                stt_time=result["stt_time"],
                bytes_data=result["human_speech_wav"],
                llm_stats=result["llm_result"],
                tts_stats=result["tts_stats"],
            )
    except Exception as e:
        logger.error(f"Exception in handle_respond_to_human: {e}")


async def restream_audio(websocket, conversation: Conversation):
    try:
        logger.info(
            "Resending audio. All chunks: "  # todo add more logs
        )
        unspoken_chunks = conversation.get_unspoken_agent_speech()
        conversation.new_agent_speech_start()
        for agent_speech_chunk in unspoken_chunks:
            await send_media(agent_speech_chunk.audio, websocket, conversation.sid)
            mark_id = conversation.agent_speech_sent(agent_speech_chunk.audio)

            await send_mark(websocket, mark_id, conversation.sid)
    except Exception as e:
        logger.error(f"Exception in restream_audio: {e}")
