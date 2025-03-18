from typing import Generator

import logging
from collections.abc import Callable
import math
import time
from langchain_openai import ChatOpenAI

from app.agents.language_agent import LLMAgent
from app.agents.voice_agent import VoiceAgent
from app.config import Config

logger = logging.getLogger(__name__)

voice_assistant = VoiceAgent()
agent = LLMAgent(
    llm=ChatOpenAI(model="gpt-4o"),
    system_prompt="You are a helpful assistant that can answer questions and help with tasks.",
)

async def respond_to_human(
    pcm_audio_buffer: bytes, sid: str, callback: Callable
) -> Generator[bytes, None, None]:
    logger.info(
        f"Human speach detected, triggering response flow. PCM buffer duration {len(pcm_audio_buffer) // Config.Audio.bytes_per_sample / Config.Audio.sample_rate}s"
    )
    start_processing = time.time()

    stt_start = time.time()
    transcript, human_speech_wav = await voice_assistant.speech_to_text(
        pcm_audio_buffer
    )
    stt_end = time.time()
    logger.info(
        f"STT time: {(stt_end - stt_start) * 1000} Transcript: {transcript.text}"
    )
    llm_result = {}
    output_llm_stream = agent.astream(
        user_query=transcript.text, 
        conversation_id=sid, 
        callback=lambda x: llm_result.update(x)
    )
    # create mock output llm stream
   
    
    # logger.info(f"Output LLM stream: {output_llm_stream}")

    voice_stream = voice_assistant.text_to_speech_streaming_ws(output_llm_stream)

    start_tts = time.time()
    first_chunk = True
    try:
        async for chunk in voice_stream:
            if first_chunk:
                first_chunk = False
                first_chunk_time = time.time()
            yield chunk
    except Exception as e:
        logger.error(f"Exception in agent response: {e}")

    end_tts = time.time()
    tts_stats = {
        "tts": math.ceil((end_tts - start_tts) * 1000),
        "to_first_byte": math.ceil((first_chunk_time - start_tts) * 1000),
        "silence_to_first_audio_chunk": math.ceil(
            (first_chunk_time - start_processing) * 1000
        ),
    }
    logger.info("LLM reulsts: %s", llm_result)
    logger.info("TTS results: %s", tts_stats)

    callback(
        {
            "transcript": transcript,
            "stt_time": (stt_end - stt_start) * 1000,
            "human_speech_wav": human_speech_wav,
            "llm_result": llm_result,
            "tts_stats": tts_stats,
        }
    )
