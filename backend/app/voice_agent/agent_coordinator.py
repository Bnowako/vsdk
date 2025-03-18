from typing import AsyncGenerator

import logging
from collections.abc import Callable
import time
from langchain_openai import ChatOpenAI

from app.voice_agent.domain import (
    LLMResult,
    RespondToHumanResult,
    TTSResult,
)
from app.voice_agent.language_agent import LLMAgent
from app.voice_agent.voice_agent import VoiceAgent
from app.config import Config

logger = logging.getLogger(__name__)

voice_assistant = VoiceAgent()
agent = LLMAgent(
    llm=ChatOpenAI(model="gpt-4o"),
    system_prompt="You are a helpful assistant that can answer questions and help with tasks.",
)


async def respond_to_human(
    pcm_audio_buffer: bytes, sid: str, callback: Callable[[RespondToHumanResult], None]
) -> AsyncGenerator[bytes, None]:
    logger.info(
        f"Human speach detected, triggering response flow. PCM buffer duration {len(pcm_audio_buffer) // Config.Audio.bytes_per_sample / Config.Audio.sample_rate}s"
    )

    stt_result = await voice_assistant.speech_to_text(pcm_audio_buffer)
    logger.info("STT results: %s", stt_result)

    llm_result = LLMResult.empty()
    output_llm_stream = agent.astream(
        stt_result,
        conversation_id=sid,
        callback=lambda x: llm_result.update(x),
    )

    voice_stream = voice_assistant.text_to_speech_streaming_ws(output_llm_stream)

    tts_result = TTSResult.empty()
    first_chunk = True
    try:
        async for chunk in voice_stream:
            if first_chunk:
                first_chunk = False
                tts_result.first_chunk_time = time.time()
            yield chunk
    except Exception as e:
        logger.error(f"Exception in agent response: {e}")
    tts_result.end_time = time.time()

    logger.info("LLM reulsts: %s", llm_result)
    logger.info("TTS results: %s", tts_result)

    callback(
        RespondToHumanResult(
            stt_result=stt_result,
            llm_result=llm_result,
            tts_result=tts_result,
        )
    )
