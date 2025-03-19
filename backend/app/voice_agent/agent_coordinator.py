import logging
import time
from collections.abc import Callable
from typing import AsyncGenerator

from langchain_openai import ChatOpenAI

from app.config import Config
from app.voice_agent.domain import (
    RespondToHumanResult,
    TTSResult,
)
from app.voice_agent.stt.GroqSTTProcessor import GroqSTTProcessor
from app.voice_agent.tts.ElevenTTSProcessor import ElevenTTSProcessor
from app.voice_agent.ttt.domain import LLMResult
from app.voice_agent.ttt.OpenAIAgent import OpenAIAgent

logger = logging.getLogger(__name__)

stt = GroqSTTProcessor()
agent = OpenAIAgent(
    llm=ChatOpenAI(model="gpt-4o"),
    system_prompt="You are a helpful assistant that can answer questions and help with tasks.",
)
tts = ElevenTTSProcessor()


async def respond_to_human(
    pcm_audio_buffer: bytes, sid: str, callback: Callable[[RespondToHumanResult], None]
) -> AsyncGenerator[bytes, None]:
    logger.info(
        f"Human speach detected, triggering response flow. PCM buffer duration {len(pcm_audio_buffer) // Config.Audio.bytes_per_sample / Config.Audio.sample_rate}s"
    )

    stt_result = await stt(pcm_audio_buffer)
    logger.info("STT results: %s", stt_result)

    llm_result = LLMResult.empty()
    output_llm_stream = agent(
        stt_result,
        conversation_id=sid,
        callback=lambda x: llm_result.update(x),
    )

    voice_stream = tts(output_llm_stream)

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
