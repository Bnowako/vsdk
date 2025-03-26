import asyncio
import logging
import time
import wave
from pathlib import Path
from typing import Any, AsyncIterator, Generator
from unittest.mock import MagicMock, patch

import pytest
from app.voice_agent.conversation_orchestrator import ConversationOrchestrator
from app.voice_agent.domain import RespondToHumanResult
from app.voice_agent.stt.domain import STTResult
from app.voice_agent.tts.ElevenTTSProcessor import AudioChunk

logger = logging.getLogger(__name__)

# Constants for readability
WAV_HEADER_SIZE = 44
CHUNK_DURATION_MS = 20
SAMPLE_RATE_KHZ = 8  # in kHz
BYTES_PER_SAMPLE = 2
CHUNK_SIZE_BYTES = CHUNK_DURATION_MS * SAMPLE_RATE_KHZ * BYTES_PER_SAMPLE
TESTS_DIR = Path.cwd() / "tests" / "resources"


def read_wav_to_pcm(file_name: str) -> bytes:
    """
    Reads a WAV file and returns its PCM data (skipping the header).
    """
    file_path = TESTS_DIR / file_name
    try:
        with file_path.open("rb") as wav_file:
            wav_file.seek(WAV_HEADER_SIZE)
            return wav_file.read()
    except Exception as e:
        logger.error(f"Error reading WAV file {file_path}: {e}")
        raise


async def send_audio(
    audio: bytes, orchestrator: Any, delay_ms: int = CHUNK_DURATION_MS
) -> None:
    """
    Sends audio data in chunks to the given orchestrator.
    """
    for i in range(0, len(audio), CHUNK_SIZE_BYTES):
        chunk = audio[i : i + CHUNK_SIZE_BYTES]
        orchestrator.audio_received(chunk)
        logger.debug(f"Sent chunk {i} of {len(audio)}")
        await asyncio.sleep(delay_ms / 1000)  # Convert ms to seconds


@pytest.fixture
def mock_voice_agent() -> Generator[MagicMock, None, None]:
    """
    Sets up a mock for the VoiceAgent's respond_to_human method.
    """
    mock_agent = MagicMock()

    async def mock_respond_to_human(
        *args: Any, **kwargs: Any
    ) -> AsyncIterator[AudioChunk]:
        result = RespondToHumanResult.empty()
        result.stt_result = STTResult(
            stt_start_time=time.time(),
            stt_end_time=time.time(),
            transcript="test transcript",
            speech_file=b"mock_speech_file",
        )
        yield AudioChunk(
            audio=b"synthetic_audio_data",
            base64_audio="base64_encoded_audio",
            normalized_alignment=None,
        )
        kwargs["callback"](result)

    mock_agent.respond_to_human.side_effect = mock_respond_to_human

    # Patch the VoiceAgent so that all instantiations return our mock.
    with patch("app.voice_agent.voice_agent.VoiceAgent", return_value=mock_agent):
        yield mock_agent


@pytest.mark.asyncio
async def test_should_not_detect_speech_and_not_respond_to_human(
    mock_voice_agent: MagicMock,
):
    """
    When there is silence, the agent should not detect speech nor respond.
    """
    pcm_data = read_wav_to_pcm("silence.wav")

    orchestrator = ConversationOrchestrator(
        conversation_id="silence_id",
        callback=lambda x: asyncio.sleep(0),
        voice_agent=mock_voice_agent,
    )

    try:
        await send_audio(pcm_data, orchestrator)
        await asyncio.sleep(0.1)  # Allow time for potential (but unwanted) processing

        mock_voice_agent.respond_to_human.assert_not_called()
    finally:
        orchestrator.end_conversation()


@pytest.mark.asyncio
async def test_should_detect_speech_and_respond_to_human(mock_voice_agent: MagicMock):
    """
    When a human speaks, the agent should detect speech, transcribe it, and respond.
    """
    pcm_data = read_wav_to_pcm("single_speech.wav")
    pcm_data_expected = read_wav_to_pcm("single_speech_expected.wav")

    orchestrator = ConversationOrchestrator(
        conversation_id="speech_simple",
        callback=lambda x: asyncio.sleep(0),
        voice_agent=mock_voice_agent,
    )

    try:
        await send_audio(pcm_data, orchestrator)
        await asyncio.sleep(0.1)  # Give time for processing

        mock_voice_agent.respond_to_human.assert_called_once()
        transcribed_audio = mock_voice_agent.respond_to_human.call_args.kwargs[
            "pcm_audio_buffer"
        ]

        assert pcm_data_expected in transcribed_audio, (
            "Expected speech segment not found in transcribed audio."
        )

        allowable_diff = 200 * SAMPLE_RATE_KHZ * BYTES_PER_SAMPLE
        assert abs(len(transcribed_audio) - len(pcm_data_expected)) <= allowable_diff, (
            "Transcribed audio length difference exceeds allowed threshold."
        )
        logger.info(
            f"Transcribed audio length difference: {abs(len(transcribed_audio) - len(pcm_data_expected)) / (SAMPLE_RATE_KHZ * BYTES_PER_SAMPLE)} samples"
        )
    finally:
        orchestrator.end_conversation()


@pytest.mark.asyncio
async def test_should_detect_speech_and_respond_to_human_once_for_long_pause(
    mock_voice_agent: MagicMock,
):
    """
    When speech occurs with a long pause between segments, the agent should respond twice.
    """
    pcm_data = read_wav_to_pcm("long_pause.wav")
    pcm_data_expected = read_wav_to_pcm("long_pause_expected.wav")

    orchestrator = ConversationOrchestrator(
        conversation_id="long_pause_id",
        callback=lambda x: asyncio.sleep(0),
        voice_agent=mock_voice_agent,
    )

    async def mock_respond_to_human(
        *args: Any, **kwargs: Any
    ) -> AsyncIterator[AudioChunk]:
        logger.info("🧪 Mock respond to human called")
        result = RespondToHumanResult.empty()
        result.stt_result = STTResult(
            stt_start_time=time.time(),
            stt_end_time=time.time(),
            transcript="test transcript",
            speech_file=b"mock_speech_file",
        )
        logger.info("🧪 Sleeping longer than the pause interval")
        await asyncio.sleep(3)  # Ensure this delay is longer than the pause
        logger.info("🧪 Resuming after sleep")
        yield AudioChunk(
            audio=b"synthetic_audio_data",
            base64_audio="base64_encoded_audio",
            normalized_alignment=None,
        )
        kwargs["callback"](result)

    # Override the side effect for this test only.
    mock_voice_agent.respond_to_human.side_effect = mock_respond_to_human

    try:
        await send_audio(pcm_data, orchestrator)
        await asyncio.sleep(4)  # Allow time for both responses

        assert mock_voice_agent.respond_to_human.call_count == 2, (
            "Expected two calls to respond_to_human."
        )
        transcribed_audio = mock_voice_agent.respond_to_human.call_args_list[1].kwargs[
            "pcm_audio_buffer"
        ]
        assert pcm_data_expected in transcribed_audio, (
            "Expected speech segment not found in transcribed audio."
        )

        allowable_diff = 200 * SAMPLE_RATE_KHZ * BYTES_PER_SAMPLE
        assert abs(len(transcribed_audio) - len(pcm_data_expected)) <= allowable_diff, (
            "Transcribed audio length difference exceeds allowed threshold."
        )
        logger.info(
            f"Transcribed audio length difference: {abs(len(transcribed_audio) - len(pcm_data_expected)) / (SAMPLE_RATE_KHZ * BYTES_PER_SAMPLE)} samples"
        )
    finally:
        orchestrator.end_conversation()


def debug_write_wav(data: bytes, file_name: str):
    """
    Writes a WAV file for debugging purposes.
    """
    logger.info(f"Writing wav file to {file_name}, {len(data)} bytes")
    with wave.open(file_name, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE_KHZ * 1000)
        wav_file.writeframes(data)
