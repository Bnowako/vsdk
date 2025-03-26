import asyncio
import logging
import os
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.voice_agent.stt.domain import STTResult
from app.voice_agent.tts.ElevenTTSProcessor import AudioChunk

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# write function that reads wav file and returns pcm data from resources folder
def read_wav_to_pcm(file_path: str) -> bytes:
    with open(file_path, "rb") as wav_file:
        wav_file.seek(44)
        return wav_file.read()


def send_audio(
    audio: bytes, orchestrator: Any
):  # cant import orchestrator due to patches
    chunk_size = 20 * 8
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i : i + chunk_size]
        orchestrator.audio_received(chunk)


@pytest.mark.asyncio  # Required for async test functions
async def test_agent_should_detect_speech_and_respond_to_human():
    """
    If human has said something while agent was not talking we should detect it and respond.

    The file contains an 8-second clip. Structure is the following
    00.00 - 01.18 silence
    01.18 - 03.90 speech 'chciałbym umówić się do lekarza rodzinnego'
    03.90 - 08.05 silence

    We expect the following:
    - speech_to_text was called with about 2.7s of speech
    - llm and tts were called
    - voice response was returned
    """
    # given
    audio_path = os.path.join(os.getcwd(), "tests", "resources", "single_speech.wav")
    pcm_data = read_wav_to_pcm(audio_path)
    patches, mock_stt, mock_ttt, mock_tts = patch_external()

    from app.voice_agent.conversation_orchestrator import ConversationOrchestrator

    orchestrator = ConversationOrchestrator(
        conversation_id="test_conversation",
        callback=lambda x: asyncio.sleep(0),
    )
    try:
        # when
        send_audio(pcm_data, orchestrator)
        await asyncio.sleep(0.1)

        # then
        # Verify STT was called with speech segment
        mock_stt.assert_called_once()
        transcribed_audio = mock_stt.call_args[0][0]

        # Check if the transcribed audio length is approximately 2.3s
        audio_duration = len(transcribed_audio) / 2 / 8 / 1000
        assert 2.3 <= audio_duration <= 2.5, (
            f"Expected ~2.3s of audio, got {audio_duration}s"
        )

        # Verify TTT and TTS were called
        mock_ttt.assert_called_once()
        mock_tts.assert_called_once()

    finally:
        # Clean up patches
        orchestrator.end_conversation()
        for p in patches:
            p.stop()


def patch_external():
    mock_stt = MagicMock()

    async def mock_stt_async(*args, **kwargs):
        return STTResult(
            stt_start_time=time.time(),
            stt_end_time=time.time(),
            transcript="test transcript",
            speech_file=b"mock_speech_file",
        )

    mock_stt.side_effect = mock_stt_async

    mock_ttt = MagicMock()

    async def mock_astream(*args, **kwargs):
        yield "Ok, pomogę ci umówić wizytę."

    mock_ttt.return_value = mock_astream()

    mock_tts = MagicMock()

    async def mock_tts_stream(input_generator):
        async for text in input_generator:
            yield AudioChunk(
                audio=b"synthetic_audio_data",
                base64_audio="base64_encoded_audio",
                normalized_alignment=None,
            )

    mock_tts.side_effect = mock_tts_stream

    # Setup patches
    patches = [
        patch(
            "app.voice_agent.stt.GroqSTTProcessor.GroqSTTProcessor",
            return_value=mock_stt,
        ),
        patch("app.voice_agent.ttt.OpenAIAgent.OpenAIAgent", return_value=mock_ttt),
        patch(
            "app.voice_agent.tts.ElevenTTSProcessor.ElevenTTSProcessor",
            return_value=mock_tts,
        ),
    ]
    for p in patches:
        p.start()
    return patches, mock_stt, mock_ttt, mock_tts
