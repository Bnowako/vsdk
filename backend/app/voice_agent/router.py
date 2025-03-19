import asyncio
import base64
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_openai import ChatOpenAI

from app.audio.audio_utils import mulaw_to_pcm
from app.conversation.models import Conversation
from app.voice_agent.conversation_manager import audio_interpreter_loop
from app.voice_agent.schemas import (
    MarkEvent,
    MediaEvent,
    StartEvent,
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
                    start_event = StartEvent(**data)

                    sid = start_event.start.streamSid
                    conversation = Conversation(sid=sid)
                    conversations_cache[sid] = conversation

                    task = asyncio.create_task(
                        audio_interpreter_loop(conversation, websocket, voice_agent)
                    )
                    conversation.audio_interpreter_loop = task

                elif event_type == "media":
                    if conversation is None:
                        logger.error("Conversation not found")
                        raise ValueError("Conversation not found")

                    media_event = MediaEvent(**data)
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

                    mark_event = MarkEvent(**data)
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
